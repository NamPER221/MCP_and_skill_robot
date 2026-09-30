#!/usr/bin/env python3
"""
Hardware Serial / RS485 / Modbus RTU, Linux Diagnostics, and SSH Remote Robot MCP Server.
Provides structured hardware discovery, Modbus RTU read/write/scan with CRC16 validation,
Linux kernel/USB/systemd/network diagnostics, and safe SSH remote inspection.
"""

import grp
import json
import os
import pwd
import shlex
import subprocess
import time
from typing import Any, Dict, Optional

import serial
from serial.tools import list_ports

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hw-linux-serial-diag")


def _run_cmd(cmd: str, timeout_sec: float = 6.0) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd],
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


def _modbus_crc16(data: bytes) -> int:
    """Computes standard Modbus RTU CRC-16 (polynomial 0xA001, init 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


@mcp.tool()
def serial_list_ports_detailed() -> str:
    """[READ] List all Serial/UART/RS485/USB-CDC ports with VID:PID, symlinks, and dialout group check."""
    ports_info = []
    for p in list_ports.comports():
        ports_info.append(
            {
                "device": p.device,
                "name": p.name,
                "description": p.description,
                "hwid": p.hwid,
                "vid_pid": f"{p.vid:04X}:{p.pid:04X}" if (p.vid is not None and p.pid is not None) else None,
                "manufacturer": p.manufacturer,
                "product": p.product,
                "serial_number": p.serial_number,
                "readable_writable": os.access(p.device, os.R_OK | os.W_OK),
            }
        )

    by_id_res = _run_cmd("ls -l /dev/serial/by-id/ 2>/dev/null || true")
    user = pwd.getpwuid(os.getuid()).pw_name
    groups = [g.gr_name for g in grp.getgrall() if user in g.gr_mem]

    return json.dumps(
        {
            "current_user": user,
            "in_dialout_group": "dialout" in groups,
            "ports_count": len(ports_info),
            "ports": ports_info,
            "by_id_symlinks": by_id_res["stdout"].splitlines() if by_id_res["stdout"] else [],
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def serial_read_sample(
    port: str,
    baudrate: int = 115200,
    duration_sec: float = 2.0,
    max_bytes: int = 512,
) -> str:
    """[READ] Read raw bytes / ASCII lines from a serial port (`port`, `baudrate`) for `duration_sec`."""
    dur = max(0.2, min(float(duration_sec), 8.0))
    limit = max(16, min(int(max_bytes), 4096))
    buf = bytearray()

    try:
        with serial.Serial(port=port, baudrate=baudrate, timeout=0.2) as ser:
            deadline = time.monotonic() + dur
            while time.monotonic() < deadline and len(buf) < limit:
                chunk = ser.read(min(128, limit - len(buf)))
                if chunk:
                    buf.extend(chunk)
        return json.dumps(
            {
                "ok": True,
                "port": port,
                "baudrate": baudrate,
                "bytes_read": len(buf),
                "hex": bytes(buf).hex(" ").upper(),
                "ascii_preview": bytes(buf).decode("utf-8", errors="replace"),
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "port": port, "error": str(exc)}, indent=2)


@mcp.tool()
def modbus_rtu_read_registers(
    port: str,
    baudrate: int,
    slave_id: int,
    function_code: int = 3,
    start_address: int = 0,
    count: int = 1,
    parity: str = "N",
    stopbits: int = 1,
    timeout_sec: float = 0.5,
) -> str:
    """[READ] Read Holding (`function_code=3`) or Input (`function_code=4`) Registers over RS485/Modbus RTU."""
    if function_code not in (3, 4):
        return json.dumps({"ok": False, "error": "function_code must be 3 (Holding) or 4 (Input)."})
    if not (1 <= count <= 64):
        return json.dumps({"ok": False, "error": "count must be between 1 and 64."})

    pdu = bytes(
        [
            slave_id & 0xFF,
            function_code & 0xFF,
            (start_address >> 8) & 0xFF,
            start_address & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
        ]
    )
    crc = _modbus_crc16(pdu)
    frame = pdu + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    expected_len = 5 + 2 * count

    try:
        with serial.Serial(
            port=port,
            baudrate=baudrate,
            parity=parity.upper(),
            stopbits=stopbits,
            bytesize=8,
            timeout=max(0.1, min(float(timeout_sec), 3.0)),
        ) as ser:
            ser.reset_input_buffer()
            ser.write(frame)
            ser.flush()
            rx = ser.read(expected_len)

        if len(rx) == 0:
            return json.dumps(
                {
                    "ok": False,
                    "status": "TIMEOUT_NO_RESPONSE",
                    "tx_hex": frame.hex(" ").upper(),
                    "diagnosis": "Check RS485 A/B polarity, baudrate/parity, slave_id, and device power.",
                },
                indent=2,
            )

        if len(rx) >= 5 and (rx[1] & 0x80):
            exc_code = rx[2]
            return json.dumps(
                {
                    "ok": False,
                    "status": "MODBUS_EXCEPTION",
                    "exception_code": f"0x{exc_code:02X}",
                    "rx_hex": rx.hex(" ").upper(),
                },
                indent=2,
            )

        if len(rx) < expected_len:
            return json.dumps(
                {
                    "ok": False,
                    "status": "INCOMPLETE_FRAME",
                    "expected_bytes": expected_len,
                    "received_bytes": len(rx),
                    "rx_hex": rx.hex(" ").upper(),
                },
                indent=2,
            )

        rx_crc = rx[-2] | (rx[-1] << 8)
        calc_crc = _modbus_crc16(rx[:-2])
        if rx_crc != calc_crc:
            return json.dumps(
                {
                    "ok": False,
                    "status": "CRC_MISMATCH",
                    "received_crc": f"0x{rx_crc:04X}",
                    "calculated_crc": f"0x{calc_crc:04X}",
                    "rx_hex": rx.hex(" ").upper(),
                },
                indent=2,
            )

        registers = []
        payload = rx[3:-2]
        for i in range(count):
            u16 = (payload[2 * i] << 8) | payload[2 * i + 1]
            s16 = u16 - 0x10000 if u16 >= 0x8000 else u16
            registers.append(
                {
                    "address": start_address + i,
                    "address_hex": f"0x{start_address + i:04X}",
                    "uint16": u16,
                    "int16": s16,
                    "hex": f"0x{u16:04X}",
                }
            )

        return json.dumps(
            {
                "ok": True,
                "slave_id": slave_id,
                "function_code": function_code,
                "tx_hex": frame.hex(" ").upper(),
                "rx_hex": rx.hex(" ").upper(),
                "registers": registers,
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def modbus_rtu_scan_slaves(
    port: str,
    baudrate: int = 9600,
    start_id: int = 1,
    end_id: int = 16,
    register_address: int = 0,
    timeout_sec: float = 0.08,
) -> str:
    """[READ] Scan a range of Modbus RTU slave IDs (`start_id..end_id`, max 32 IDs per call)."""
    s_id = max(1, min(int(start_id), 247))
    e_id = max(s_id, min(int(end_id), min(247, s_id + 31)))
    found = []

    try:
        with serial.Serial(port=port, baudrate=baudrate, timeout=max(0.03, min(float(timeout_sec), 0.5))) as ser:
            for sid in range(s_id, e_id + 1):
                pdu = bytes([sid, 0x03, (register_address >> 8) & 0xFF, register_address & 0xFF, 0x00, 0x01])
                crc = _modbus_crc16(pdu)
                frame = pdu + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
                ser.reset_input_buffer()
                ser.write(frame)
                ser.flush()
                rx = ser.read(7)
                if len(rx) >= 5 and rx[0] == sid:
                    found.append({"slave_id": sid, "response_hex": rx.hex(" ").upper()})
        return json.dumps(
            {
                "ok": True,
                "port": port,
                "baudrate": baudrate,
                "scanned_range": f"{s_id}..{e_id}",
                "devices_found": found,
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def modbus_rtu_write_register_safe(
    port: str,
    baudrate: int,
    slave_id: int,
    register_address: int,
    value_uint16: int,
    parity: str = "N",
    stopbits: int = 1,
    confirm: bool = False,
) -> str:
    """[DANGEROUS - CONFIRMATION REQUIRED] Write a Single Holding Register (`FC=0x06`) over Modbus RTU."""
    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Writing Modbus register 0x{register_address:04X}={value_uint16} to slave {slave_id} on {port} requires confirm=True.",
            },
            indent=2,
        )

    pdu = bytes(
        [
            slave_id & 0xFF,
            0x06,
            (register_address >> 8) & 0xFF,
            register_address & 0xFF,
            (value_uint16 >> 8) & 0xFF,
            value_uint16 & 0xFF,
        ]
    )
    crc = _modbus_crc16(pdu)
    frame = pdu + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    try:
        with serial.Serial(port=port, baudrate=baudrate, parity=parity.upper(), stopbits=stopbits, timeout=0.5) as ser:
            ser.reset_input_buffer()
            ser.write(frame)
            ser.flush()
            rx = ser.read(8)
        return json.dumps(
            {
                "ok": rx == frame,
                "tx_hex": frame.hex(" ").upper(),
                "rx_hex": rx.hex(" ").upper(),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def linux_hardware_fault_diagnose(subsystem: str = "all") -> str:
    """[READ] Structured Linux diagnostics for robotics hardware (`all`, `usb`, `network`, `systemd`, `kernel_EMI`, `resources`)."""
    report: Dict[str, Any] = {}

    if subsystem in ("all", "usb"):
        report["lsusb"] = _run_cmd("lsusb")["stdout"].splitlines()

    if subsystem in ("all", "kernel_EMI"):
        dmesg_res = _run_cmd(
            "dmesg -T 2>/dev/null | grep -iE 'usb|tty|can|over-current|disconnect|reset|error|fault' | tail -n 35"
        )
        report["kernel_hardware_events"] = dmesg_res["stdout"].splitlines() if dmesg_res["stdout"] else []

    if subsystem in ("all", "network"):
        report["ip_brief_addr"] = _run_cmd("ip -br addr")["stdout"].splitlines()
        report["ip_route"] = _run_cmd("ip route")["stdout"].splitlines()

    if subsystem in ("all", "systemd"):
        report["failed_services"] = _run_cmd("systemctl --failed --no-pager")["stdout"].splitlines()

    if subsystem in ("all", "resources"):
        report["uptime_load"] = _run_cmd("uptime")["stdout"]
        report["memory_free"] = _run_cmd("free -h")["stdout"].splitlines()
        report["disk_df"] = _run_cmd("df -h / /home")["stdout"].splitlines()

    return json.dumps(report, indent=2, ensure_ascii=False)


@mcp.tool()
def ssh_remote_diagnose(
    host: str,
    user: str = "robotics",
    port: int = 22,
    check_profile: str = "overview",
) -> str:
    """[READ] Non-interactive SSH diagnostics on a remote robot computer (`overview`, `ros2`, `can`, `usb_serial`)."""
    profile_cmds = {
        "overview": "hostname && uptime && ip -br addr && free -h",
        "ros2": "source /opt/ros/humble/setup.bash 2>/dev/null; ros2 node list && echo '---' && ros2 topic list",
        "can": "ip -details -statistics link show type can",
        "usb_serial": "lsusb && ls -l /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* 2>/dev/null || true",
    }
    if check_profile not in profile_cmds:
        return json.dumps({"ok": False, "error": f"Invalid check_profile. Choose from {list(profile_cmds.keys())}"})

    remote_cmd = profile_cmds[check_profile]
    ssh_cmd = (
        f"ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "
        f"-p {int(port)} {shlex.quote(user)}@{shlex.quote(host)} {shlex.quote(remote_cmd)}"
    )
    res = _run_cmd(ssh_cmd, timeout_sec=10.0)
    return json.dumps(
        {
            "host": host,
            "user": user,
            "check_profile": check_profile,
            "ok": res["ok"],
            "stdout": res["stdout"],
            "stderr": res["stderr"],
        },
        indent=2,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    mcp.run()
