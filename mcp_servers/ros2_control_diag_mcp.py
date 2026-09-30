#!/usr/bin/env python3
"""
ROS2 Control & Diagnostics MCP Server.
Provides native ROS2 introspection, sensor pipeline fault analysis, TF & QoS verification,
and safety-clamped robot control tools with human-in-the-loop confirmation.
"""

import json
import math
import os
import shlex
import subprocess
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ros2-control-diag")

DEFAULT_ROS_SETUP = "/opt/ros/humble/setup.bash"
ALLOWED_WORKSPACES = [
    "/home/namnc/ros2_ws",
    "/home/namnc/base_kit",
    "/home/namnc/vehichi-dc",
    "/home/namnc/Zlac_test",
    "/home/namnc/V-SLam",
]


def _build_ros_env_cmd(cmd: str, workspace_path: Optional[str] = None, domain_id: Optional[int] = None) -> str:
    """Builds a bash command with ROS2 Humble and optional workspace sourced."""
    sources = []
    if os.path.exists(DEFAULT_ROS_SETUP):
        sources.append(f"source {shlex.quote(DEFAULT_ROS_SETUP)}")

    if workspace_path:
        ws_setup = os.path.join(os.path.expanduser(workspace_path), "install", "setup.bash")
        if os.path.exists(ws_setup):
            sources.append(f"source {shlex.quote(ws_setup)}")
    else:
        for ws in ALLOWED_WORKSPACES:
            ws_setup = os.path.join(ws, "install", "setup.bash")
            if os.path.exists(ws_setup):
                sources.append(f"source {shlex.quote(ws_setup)}")
                break

    env_prefix = ""
    if domain_id is not None:
        env_prefix = f"export ROS_DOMAIN_ID={int(domain_id)}; "

    source_chain = " && ".join(sources)
    if source_chain:
        return f"{env_prefix}{source_chain} && {cmd}"
    return f"{env_prefix}{cmd}"


def _run_ros_cmd(
    cmd: str,
    timeout_sec: float = 8.0,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Executes a ROS2 command safely with timeout and structured output."""
    full_cmd = _build_ros_env_cmd(cmd, workspace_path=workspace_path, domain_id=domain_id)
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
            "command": cmd,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": f"Command timed out after {timeout_sec}s",
            "command": cmd,
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": -2,
            "stdout": "",
            "stderr": str(exc),
            "command": cmd,
        }


@mcp.tool()
def ros2_graph_overview(
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[READ] Inspect the active ROS2 computation graph: nodes, topics (with types), services, and actions."""
    nodes_res = _run_ros_cmd("ros2 node list", workspace_path=workspace_path, domain_id=domain_id)
    topics_res = _run_ros_cmd("ros2 topic list -t", workspace_path=workspace_path, domain_id=domain_id)
    services_res = _run_ros_cmd("ros2 service list -t", workspace_path=workspace_path, domain_id=domain_id)
    actions_res = _run_ros_cmd("ros2 action list -t", workspace_path=workspace_path, domain_id=domain_id)

    report = {
        "nodes": nodes_res["stdout"].splitlines() if nodes_res["stdout"] else [],
        "topics": topics_res["stdout"].splitlines() if topics_res["stdout"] else [],
        "services": services_res["stdout"].splitlines() if services_res["stdout"] else [],
        "actions": actions_res["stdout"].splitlines() if actions_res["stdout"] else [],
        "errors": [
            r["stderr"]
            for r in (nodes_res, topics_res, services_res, actions_res)
            if not r["ok"] and r["stderr"]
        ],
    }
    return json.dumps(report, indent=2, ensure_ascii=False)


@mcp.tool()
def ros2_node_inspect(
    node_name: str,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[READ] Inspect a specific ROS2 node: subscribers, publishers, services, actions, and parameters."""
    safe_node = shlex.quote(node_name)
    info_res = _run_ros_cmd(f"ros2 node info {safe_node}", workspace_path=workspace_path, domain_id=domain_id)
    param_res = _run_ros_cmd(f"ros2 param list {safe_node}", workspace_path=workspace_path, domain_id=domain_id)

    return json.dumps(
        {
            "node": node_name,
            "ok": info_res["ok"],
            "node_info": info_res["stdout"],
            "parameters": param_res["stdout"].splitlines() if param_res["stdout"] else [],
            "stderr": info_res["stderr"] or param_res["stderr"],
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def ros2_topic_inspect(
    topic_name: str,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[READ] Inspect a ROS2 topic in verbose mode (`ros2 topic info -v`) and detect QoS mismatches."""
    safe_topic = shlex.quote(topic_name)
    res = _run_ros_cmd(f"ros2 topic info -v {safe_topic}", workspace_path=workspace_path, domain_id=domain_id)

    qos_warnings: List[str] = []
    stdout = res["stdout"]
    if "Reliability: BEST_EFFORT" in stdout and "Reliability: RELIABLE" in stdout:
        qos_warnings.append(
            "Potential QoS mismatch: topic has both BEST_EFFORT and RELIABLE endpoints. "
            "A BEST_EFFORT publisher cannot deliver messages to a RELIABLE subscriber."
        )
    if "Durability: VOLATILE" in stdout and "Durability: TRANSIENT_LOCAL" in stdout:
        qos_warnings.append(
            "Potential QoS Durability mismatch: topic has both VOLATILE and TRANSIENT_LOCAL endpoints."
        )

    return json.dumps(
        {
            "topic": topic_name,
            "ok": res["ok"],
            "verbose_info": stdout,
            "qos_warnings": qos_warnings,
            "stderr": res["stderr"],
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def ros2_topic_echo_once(
    topic_name: str,
    timeout_sec: float = 5.0,
    qos_reliability: str = "system_default",
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[READ] Echo a single message (`--once`) from a ROS2 topic with bounded timeout."""
    safe_topic = shlex.quote(topic_name)
    qos_flag = ""
    if qos_reliability in ("best_effort", "reliable", "system_default"):
        qos_flag = f"--qos-reliability {qos_reliability}"

    res = _run_ros_cmd(
        f"ros2 topic echo {safe_topic} --once {qos_flag} --truncate-length 256",
        timeout_sec=max(1.0, min(timeout_sec, 15.0)),
        workspace_path=workspace_path,
        domain_id=domain_id,
    )
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def ros2_topic_hz_check(
    topic_name: str,
    window_size: int = 20,
    duration_sec: float = 4.0,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[READ] Measure the publishing frequency (Hz) of a ROS2 topic over `duration_sec`."""
    safe_topic = shlex.quote(topic_name)
    w = max(2, min(int(window_size), 500))
    dur = max(1.5, min(float(duration_sec), 10.0))
    res = _run_ros_cmd(
        f"timeout {dur}s ros2 topic hz {safe_topic} -w {w}",
        timeout_sec=dur + 2.0,
        workspace_path=workspace_path,
        domain_id=domain_id,
    )
    return json.dumps(
        {
            "topic": topic_name,
            "duration_sec": dur,
            "hz_output": res["stdout"],
            "stderr": res["stderr"],
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def ros2_param_get(
    node_name: str,
    param_name: Optional[str] = None,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[READ] Read a specific parameter or dump all parameters of a ROS2 node."""
    safe_node = shlex.quote(node_name)
    if param_name:
        safe_param = shlex.quote(param_name)
        res = _run_ros_cmd(
            f"ros2 param get {safe_node} {safe_param}",
            workspace_path=workspace_path,
            domain_id=domain_id,
        )
    else:
        res = _run_ros_cmd(
            f"ros2 param dump {safe_node}",
            workspace_path=workspace_path,
            domain_id=domain_id,
        )
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def ros2_tf_diagnostics(
    source_frame: Optional[str] = None,
    target_frame: Optional[str] = None,
    timeout_sec: float = 3.0,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[READ] Diagnose the ROS2 TF tree (`/tf`, `/tf_static`, and optional `tf2_echo` between frames)."""
    tf_info = _run_ros_cmd("ros2 topic info -v /tf", workspace_path=workspace_path, domain_id=domain_id)
    tf_static_info = _run_ros_cmd("ros2 topic info -v /tf_static", workspace_path=workspace_path, domain_id=domain_id)

    transform_sample = None
    if source_frame and target_frame:
        dur = max(1.0, min(float(timeout_sec), 8.0))
        echo_res = _run_ros_cmd(
            f"timeout {dur}s ros2 run tf2_ros tf2_echo {shlex.quote(source_frame)} {shlex.quote(target_frame)}",
            timeout_sec=dur + 2.0,
            workspace_path=workspace_path,
            domain_id=domain_id,
        )
        transform_sample = {
            "source_frame": source_frame,
            "target_frame": target_frame,
            "output": echo_res["stdout"],
            "stderr": echo_res["stderr"],
        }

    return json.dumps(
        {
            "tf_topic_info": tf_info["stdout"],
            "tf_static_topic_info": tf_static_info["stdout"],
            "transform_lookup": transform_sample,
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def ros2_diagnose_sensor_pipeline(
    topic_name: str,
    expected_frame_id: Optional[str] = None,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[READ] Automated multi-step fault analysis for a sensor or odometry topic."""
    safe_topic = shlex.quote(topic_name)
    findings: List[str] = []

    info_res = _run_ros_cmd(f"ros2 topic info -v {safe_topic}", workspace_path=workspace_path, domain_id=domain_id)
    if not info_res["ok"] or not info_res["stdout"]:
        return json.dumps(
            {
                "topic": topic_name,
                "status": "FAULT_TOPIC_NOT_FOUND",
                "findings": [f"Topic {topic_name} does not exist or ROS2 daemon cannot see it."],
                "stderr": info_res["stderr"],
            },
            indent=2,
            ensure_ascii=False,
        )

    info_text = info_res["stdout"]
    if "Publisher count: 0" in info_text:
        findings.append("CRITICAL: Publisher count is 0. Sensor driver node is not publishing or crashed.")

    if "Reliability: BEST_EFFORT" in info_text and "Reliability: RELIABLE" in info_text:
        findings.append("WARNING: Mixed BEST_EFFORT and RELIABLE endpoints detected on this topic.")

    echo_res = _run_ros_cmd(
        f"ros2 topic echo {safe_topic} --once --qos-reliability best_effort --truncate-length 64",
        timeout_sec=4.0,
        workspace_path=workspace_path,
        domain_id=domain_id,
    )

    msg_received = echo_res["ok"] and bool(echo_res["stdout"])
    if not msg_received:
        findings.append("CRITICAL: Publisher exists, but no message was received within 4.0 seconds.")
    else:
        findings.append("OK: Message received successfully from topic.")
        if expected_frame_id:
            if f"frame_id: {expected_frame_id}" not in echo_res["stdout"] and expected_frame_id not in echo_res["stdout"]:
                findings.append(f"WARNING: Expected frame_id '{expected_frame_id}' not found in message header.")
            else:
                findings.append(f"OK: Expected frame_id '{expected_frame_id}' verified in message.")

    hz_output = ""
    if msg_received:
        hz_res = _run_ros_cmd(
            f"timeout 2.5s ros2 topic hz {safe_topic} -w 10",
            timeout_sec=4.0,
            workspace_path=workspace_path,
            domain_id=domain_id,
        )
        hz_output = hz_res["stdout"]

    return json.dumps(
        {
            "topic": topic_name,
            "message_received": msg_received,
            "findings": findings,
            "topic_info": info_text,
            "sample_message": echo_res["stdout"][:1500] if echo_res["stdout"] else "",
            "hz_measurement": hz_output,
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def ros2_emergency_stop(
    cmd_vel_topic: str = "/cmd_vel",
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[SAFETY OVERRIDE] Immediately publish zero velocity (`geometry_msgs/msg/Twist` all zeros) to stop the robot."""
    safe_topic = shlex.quote(cmd_vel_topic)
    zero_msg = "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
    res = _run_ros_cmd(
        f"ros2 topic pub --once {safe_topic} geometry_msgs/msg/Twist {shlex.quote(zero_msg)}",
        timeout_sec=4.0,
        workspace_path=workspace_path,
        domain_id=domain_id,
    )
    return json.dumps(
        {
            "action": "EMERGENCY_STOP",
            "topic": cmd_vel_topic,
            "ok": res["ok"],
            "stdout": res["stdout"],
            "stderr": res["stderr"],
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def ros2_publish_cmd_vel_safe(
    linear_x: float,
    angular_z: float,
    duration_sec: float = 2.0,
    max_linear_limit: float = 0.5,
    max_angular_limit: float = 1.0,
    cmd_vel_topic: str = "/cmd_vel",
    confirm: bool = False,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[DANGEROUS - CONFIRMATION REQUIRED] Publish velocity commands with velocity clamping and auto-stop."""
    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": "Publishing to /cmd_vel requires user confirmation (confirm=True).",
                "requested": {
                    "topic": cmd_vel_topic,
                    "linear_x": linear_x,
                    "angular_z": angular_z,
                    "duration_sec": duration_sec,
                },
            },
            indent=2,
            ensure_ascii=False,
        )

    hard_max_lin = min(abs(max_linear_limit), 1.5)
    hard_max_ang = min(abs(max_angular_limit), 2.5)
    clamped_vx = max(-hard_max_lin, min(float(linear_x), hard_max_lin))
    clamped_wz = max(-hard_max_ang, min(float(angular_z), hard_max_ang))
    clamped_dur = max(0.2, min(float(duration_sec), 10.0))

    if math.isnan(clamped_vx) or math.isnan(clamped_wz):
        return json.dumps({"ok": False, "error": "NaN velocity is forbidden."})

    safe_topic = shlex.quote(cmd_vel_topic)
    twist_msg = (
        f"{{linear: {{x: {clamped_vx:.4f}, y: 0.0, z: 0.0}}, "
        f"angular: {{x: 0.0, y: 0.0, z: {clamped_wz:.4f}}}}}"
    )
    zero_msg = "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

    cmd = (
        f"timeout {clamped_dur}s ros2 topic pub -r 10 {safe_topic} "
        f"geometry_msgs/msg/Twist {shlex.quote(twist_msg)} ; "
        f"ros2 topic pub --once {safe_topic} geometry_msgs/msg/Twist {shlex.quote(zero_msg)}"
    )
    res = _run_ros_cmd(
        cmd,
        timeout_sec=clamped_dur + 4.0,
        workspace_path=workspace_path,
        domain_id=domain_id,
    )
    return json.dumps(
        {
            "ok": True,
            "topic": cmd_vel_topic,
            "requested_velocity": {"linear_x": linear_x, "angular_z": angular_z},
            "clamped_velocity": {"linear_x": clamped_vx, "angular_z": clamped_wz},
            "duration_sec": clamped_dur,
            "auto_stopped": True,
            "stdout": res["stdout"],
            "stderr": res["stderr"],
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def ros2_param_set_safe(
    node_name: str,
    param_name: str,
    value: str,
    confirm: bool = False,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[WRITE - CONFIRMATION REQUIRED] Set a runtime parameter on a ROS2 node."""
    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Setting parameter '{param_name}' on '{node_name}' to '{value}' requires confirm=True.",
            },
            indent=2,
            ensure_ascii=False,
        )

    res = _run_ros_cmd(
        f"ros2 param set {shlex.quote(node_name)} {shlex.quote(param_name)} {shlex.quote(value)}",
        workspace_path=workspace_path,
        domain_id=domain_id,
    )
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def ros2_service_call_safe(
    service_name: str,
    service_type: str,
    request_yaml: str = "{}",
    confirm: bool = False,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """[WRITE/DANGEROUS - CONFIRMATION REQUIRED] Call a ROS2 service."""
    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Calling service '{service_name}' ({service_type}) requires confirm=True.",
            },
            indent=2,
            ensure_ascii=False,
        )

    res = _run_ros_cmd(
        f"ros2 service call {shlex.quote(service_name)} {shlex.quote(service_type)} {shlex.quote(request_yaml)}",
        timeout_sec=10.0,
        workspace_path=workspace_path,
        domain_id=domain_id,
    )
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def ros2_lifecycle_control(
    node_name: str,
    transition: Optional[str] = None,
    confirm: bool = False,
    workspace_path: Optional[str] = None,
    domain_id: Optional[int] = None,
) -> str:
    """Inspect or transition a ROS2 Lifecycle node."""
    safe_node = shlex.quote(node_name)
    if not transition:
        state_res = _run_ros_cmd(f"ros2 lifecycle get {safe_node}", workspace_path=workspace_path, domain_id=domain_id)
        list_res = _run_ros_cmd(f"ros2 lifecycle list {safe_node}", workspace_path=workspace_path, domain_id=domain_id)
        return json.dumps(
            {
                "node": node_name,
                "current_state": state_res["stdout"],
                "available_transitions": list_res["stdout"],
                "stderr": state_res["stderr"] or list_res["stderr"],
            },
            indent=2,
            ensure_ascii=False,
        )

    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Lifecycle transition '{transition}' on '{node_name}' requires confirm=True.",
            },
            indent=2,
            ensure_ascii=False,
        )

    res = _run_ros_cmd(
        f"ros2 lifecycle set {safe_node} {shlex.quote(transition)}",
        workspace_path=workspace_path,
        domain_id=domain_id,
    )
    return json.dumps(res, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
