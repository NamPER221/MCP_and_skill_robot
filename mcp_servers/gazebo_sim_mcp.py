#!/usr/bin/env python3
"""
Gazebo Simulation Control & Diagnostics MCP Server.
Supports Gazebo Classic (gazebo_ros_pkgs) and Gazebo Sim / Ignition via ROS2 services & topics.
"""

import json
import math
import os
import shlex
import subprocess
from typing import Any, Dict

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gazebo-sim-control")

DEFAULT_ROS_SETUP = "/opt/ros/humble/setup.bash"


def _run_ros_cmd(cmd: str, timeout_sec: float = 8.0) -> Dict[str, Any]:
    full_cmd = f"source {shlex.quote(DEFAULT_ROS_SETUP)} && {cmd}" if os.path.exists(DEFAULT_ROS_SETUP) else cmd
    try:
        proc = subprocess.run(
            ["bash", "-c", full_cmd],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": f"Timed out after {timeout_sec}s"}
    except Exception as exc:
        return {"ok": False, "returncode": -2, "stdout": "", "stderr": str(exc)}


@mcp.tool()
def gazebo_world_and_models_status() -> str:
    """[READ] Inspect running Gazebo processes, simulation clock (`/clock`), and Gazebo ROS2 services."""
    ps_res = _run_ros_cmd("ps aux | grep -iE 'gzserver|gzclient|ign|gz sim' | grep -v grep || true")
    srv_res = _run_ros_cmd("ros2 service list | grep -iE 'gazebo|spawn|delete|physics|world|entity' || true")
    clock_res = _run_ros_cmd("ros2 topic echo /clock --once", timeout_sec=3.0)

    return json.dumps(
        {
            "gazebo_processes": ps_res["stdout"].splitlines() if ps_res["stdout"] else [],
            "simulation_services": srv_res["stdout"].splitlines() if srv_res["stdout"] else [],
            "clock_active": clock_res["ok"] and bool(clock_res["stdout"]),
            "clock_sample": clock_res["stdout"],
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def gazebo_physics_control(action: str, confirm: bool = False) -> str:
    """[WRITE - CONFIRMATION REQUIRED] Control Gazebo physics (`pause`, `unpause`, `reset_simulation`, `reset_world`)."""
    srv_map = {
        "pause": "/pause_physics",
        "unpause": "/unpause_physics",
        "reset_simulation": "/reset_simulation",
        "reset_world": "/reset_world",
    }
    if action not in srv_map:
        return json.dumps({"ok": False, "error": f"Invalid action. Choose from {list(srv_map.keys())}"})

    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Gazebo physics action '{action}' requires confirm=True.",
            },
            indent=2,
        )

    res = _run_ros_cmd(f"ros2 service call {srv_map[action]} std_srvs/srv/Empty '{{}}'")
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def gazebo_spawn_entity_safe(
    entity_name: str,
    file_path: str,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.1,
    yaw: float = 0.0,
    confirm: bool = False,
) -> str:
    """[WRITE - CONFIRMATION REQUIRED] Spawn a URDF or SDF model file into Gazebo."""
    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Spawning entity '{entity_name}' from '{file_path}' requires confirm=True.",
            },
            indent=2,
        )

    expanded = os.path.expanduser(file_path)
    if not os.path.isfile(expanded):
        return json.dumps({"ok": False, "error": f"Model file not found: {expanded}"})

    cmd = (
        f"ros2 run gazebo_ros spawn_entity.py -entity {shlex.quote(entity_name)} "
        f"-file {shlex.quote(expanded)} -x {float(x)} -y {float(y)} -z {float(z)} -Y {float(yaw)}"
    )
    res = _run_ros_cmd(cmd, timeout_sec=15.0)
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def gazebo_set_entity_state_safe(
    entity_name: str,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    yaw: float = 0.0,
    vx: float = 0.0,
    vy: float = 0.0,
    wz: float = 0.0,
    reference_frame: str = "world",
    confirm: bool = False,
) -> str:
    """[WRITE - CONFIRMATION REQUIRED] Set pose and twist of an entity in Gazebo."""
    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Setting state of '{entity_name}' in Gazebo requires confirm=True.",
            },
            indent=2,
        )

    qz = math.sin(yaw * 0.5)
    qw = math.cos(yaw * 0.5)
    req = (
        f"{{state: {{name: '{entity_name}', "
        f"pose: {{position: {{x: {x}, y: {y}, z: {z}}}, orientation: {{x: 0.0, y: 0.0, z: {qz:.6f}, w: {qw:.6f}}}}}, "
        f"twist: {{linear: {{x: {vx}, y: {vy}, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: {wz}}}}}, "
        f"reference_frame: '{reference_frame}'}}}}"
    )
    res = _run_ros_cmd(f"ros2 service call /set_entity_state gazebo_msgs/srv/SetEntityState {shlex.quote(req)}")
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def gazebo_delete_entity_safe(entity_name: str, confirm: bool = False) -> str:
    """[WRITE - CONFIRMATION REQUIRED] Delete an entity from Gazebo via `/delete_entity`."""
    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Deleting entity '{entity_name}' from Gazebo requires confirm=True.",
            },
            indent=2,
        )

    req = f"{{name: '{entity_name}'}}"
    res = _run_ros_cmd(f"ros2 service call /delete_entity gazebo_msgs/srv/DeleteEntity {shlex.quote(req)}")
    return json.dumps(res, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
