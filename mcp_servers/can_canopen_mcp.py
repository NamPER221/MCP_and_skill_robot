#!/usr/bin/env python3
"""
SocketCAN & CANopen Control and Fault Analysis MCP Server.
Supports diverse CAN hardware (SocketCAN, PCAN, USB-CAN, vcan) and CANopen CiA 301 / CiA 402
motor controllers & BMS (including ZLAC8015D dual motor drivers, VARTA battery, standard CiA 402 drives).
"""

import json
import re
import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional

import can

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

mcp = FastMCP("can-canopen-diag")

CIA402_COMMON_OD = {
    0x1000: "Device Type",
    0x1001: "Error Register",
    0x1017: "Producer Heartbeat Time (ms)",
    0x603F: "Error Code (Last Fault)",
    0x6040: "Controlword",
    0x6041: "Statusword",
    0x605A: "Quick Stop Option Code",
    0x6060: "Modes of Operation",
    0x6061: "Modes of Operation Display",
    0x6064: "Position Actual Value",
    0x606C: "Velocity Actual Value",
    0x6077: "Torque/Current Actual Value",
    0x607A: "Target Position",
    0x6081: "Profile Velocity",
    0x6083: "Profile Acceleration",
    0x6084: "Profile Deceleration",
    0x60FF: "Target Velocity",
}

ERROR_CODE_TABLE = {
    0x0000: "No Error / Normal",
    0x1000: "Generic Error",
    0x2300: "Current on device output side too high (Overcurrent)",
    0x2310: "Continuous overcurrent",
    0x2320: "Short circuit / Earth leakage at motor phase",
    0x3100: "Mains / Supply voltage fault",
    0x3210: "DC Link Overvoltage",
    0x3220: "DC Link Undervoltage",
    0x4210: "Excess temperature device / heatsink (Overtemperature)",
    0x4310: "Excess temperature motor",
    0x5441: "Motor / Driver disabled by limit or emergency input",
    0x6100: "Internal software / firmware fault",
    0x7300: "Sensor / Encoder fault (Hall or ABZ encoder error)",
    0x7305: "Incremental encoder 1 fault (ABZ signal loss / broken wire)",
    0x8110: "CAN Overrun (Objects lost - check bus load)",
    0x8120: "CAN in Error Passive Mode (Check termination 120R / wiring / baudrate)",
    0x8130: "Life Guard Error or Heartbeat Error (Communication timeout)",
    0x8140: "Recovered from Bus-Off",
    0x8611: "Following Error (Motor cannot track target velocity/position)",
    0xFF01: "ZLAC/Vendor Overvoltage fault",
    0xFF02: "ZLAC/Vendor Undervoltage fault",
    0xFF04: "ZLAC/Vendor Overcurrent fault",
    0xFF08: "ZLAC/Vendor Overload fault",
    0xFF10: "ZLAC/Vendor Current out of tolerance",
    0xFF20: "ZLAC/Vendor Encoder out of tolerance",
    0xFF40: "ZLAC/Vendor Velocity out of tolerance",
    0xFF80: "ZLAC/Vendor Reference voltage error",
}


def _run_cmd(cmd: str, timeout_sec: float = 5.0) -> Dict[str, Any]:
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


@mcp.tool()
def can_list_interfaces() -> str:
    """[READ] List all SocketCAN and virtual CAN interfaces (`can*`, `vcan*`, `slcan*`)."""
    res = _run_cmd("ip -br link show type can ; ip -br link show type vcan")
    lines = [line.strip() for line in res["stdout"].splitlines() if line.strip()]
    return json.dumps(
        {
            "interfaces_found": len(lines),
            "interfaces": lines,
            "hint": "If no interface is found, check USB-CAN adapter with hw_linux_serial_mcp or load kernel modules (can, can_raw, gs_usb, mttcan).",
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def can_interface_diagnostics(interface: str = "can0") -> str:
    """[READ] Deep hardware & kernel-level fault analysis of a SocketCAN interface."""
    safe_if = shlex.quote(interface)
    res = _run_cmd(f"ip -details -statistics link show {safe_if}")
    if not res["ok"]:
        return json.dumps(
            {
                "interface": interface,
                "ok": False,
                "error": res["stderr"] or f"Interface {interface} not found.",
            },
            indent=2,
            ensure_ascii=False,
        )

    raw = res["stdout"]
    bitrate_match = re.search(r"bitrate\s+(\d+)", raw)
    sample_match = re.search(r"sample-point\s+([\d.]+)", raw)
    state_match = re.search(r"can state\s+([A-Z\-]+)", raw)
    berr_match = re.search(r"berr-counter\s+tx\s+(\d+)\s+rx\s+(\d+)", raw)
    restart_match = re.search(r"restart-ms\s+(\d+)", raw)

    bitrate = int(bitrate_match.group(1)) if bitrate_match else None
    sample_point = float(sample_match.group(1)) if sample_match else None
    can_state = state_match.group(1) if state_match else "UNKNOWN (possibly vcan or DOWN)"
    tx_err = int(berr_match.group(1)) if berr_match else 0
    rx_err = int(berr_match.group(2)) if berr_match else 0
    restart_ms = int(restart_match.group(1)) if restart_match else 0

    is_up = "UP" in raw.splitlines()[0] if raw else False

    diagnoses: List[str] = []
    if not is_up:
        diagnoses.append(f"CRITICAL: Interface {interface} is DOWN. Bring it up before communicating.")
    if can_state == "BUS-OFF":
        diagnoses.append(
            "CRITICAL (BUS-OFF): TX Error Counter exceeded 255. Causes: CAN_H/CAN_L shorted or swapped, "
            "wrong bitrate vs other nodes, or no other active CAN node sending ACK."
        )
        if restart_ms == 0:
            diagnoses.append("WARNING: restart-ms is 0; interface will not auto-recover from BUS-OFF.")
    elif can_state == "ERROR-PASSIVE":
        if tx_err >= 128 and rx_err == 0:
            diagnoses.append(
                "CRITICAL (ERROR-PASSIVE, TX=128+, RX=0): Classical 'No ACK' symptom. "
                "Check: (1) Target device powered on? (2) 120-Ohm termination resistors at both ends? "
                "(3) CAN_H/CAN_L continuity? (4) Matching bitrate?"
            )
        else:
            diagnoses.append(
                f"CRITICAL (ERROR-PASSIVE, TX_err={tx_err}, RX_err={rx_err}): Severe signal integrity or bitrate mismatch. "
                "Check termination resistors (measure ~60 Ohm between CAN_H and CAN_L with power off), stub lengths, and EMI."
            )
    elif can_state == "ERROR-WARNING":
        diagnoses.append(
            f"WARNING (ERROR-WARNING, TX_err={tx_err}, RX_err={rx_err}): Intermittent bit/stuff/CRC errors on bus."
        )
    elif can_state == "ERROR-ACTIVE" and tx_err == 0 and rx_err == 0:
        diagnoses.append("OK: CAN controller is ERROR-ACTIVE with zero bus errors.")

    return json.dumps(
        {
            "interface": interface,
            "is_up": is_up,
            "can_state": can_state,
            "bitrate": bitrate,
            "sample_point": sample_point,
            "tx_error_counter": tx_err,
            "rx_error_counter": rx_err,
            "restart_ms": restart_ms,
            "automated_diagnosis": diagnoses,
            "raw_ip_link": raw,
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def can_dump_capture(
    interface: str = "can0",
    duration_sec: float = 2.0,
    can_id_filter_hex: Optional[str] = None,
    max_frames: int = 100,
) -> str:
    """[READ] Capture live CAN frames from `interface` for `duration_sec` (max 10s)."""
    dur = max(0.2, min(float(duration_sec), 10.0))
    limit = max(1, min(int(max_frames), 500))

    filter_id: Optional[int] = None
    if can_id_filter_hex:
        filter_id = int(can_id_filter_hex.strip(), 16)

    frames: List[Dict[str, Any]] = []
    try:
        can_filters = [{"can_id": filter_id, "can_mask": 0x7FF}] if filter_id is not None else None
        with can.Bus(interface="socketcan", channel=interface, can_filters=can_filters) as bus:
            deadline = time.monotonic() + dur
            while time.monotonic() < deadline and len(frames) < limit:
                remaining = max(0.01, deadline - time.monotonic())
                msg = bus.recv(timeout=min(0.2, remaining))
                if msg is not None:
                    frames.append(
                        {
                            "timestamp": round(msg.timestamp, 6),
                            "can_id": f"0x{msg.arbitration_id:03X}",
                            "dlc": msg.dlc,
                            "data_hex": msg.data.hex(" ").upper(),
                            "is_error_frame": msg.is_error_frame,
                            "is_remote_frame": msg.is_remote_frame,
                        }
                    )
        return json.dumps(
            {
                "interface": interface,
                "duration_sec": dur,
                "frames_captured": len(frames),
                "frames": frames,
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"interface": interface, "ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def can_bus_load_estimate(
    interface: str = "can0",
    duration_sec: float = 2.0,
    nominal_bitrate: int = 500000,
) -> str:
    """[READ] Measure CAN frame rate and estimate bus load percentage over `duration_sec`."""
    dur = max(0.5, min(float(duration_sec), 10.0))
    total_bits = 0
    total_frames = 0
    id_counts: Dict[str, int] = {}

    try:
        with can.Bus(interface="socketcan", channel=interface) as bus:
            deadline = time.monotonic() + dur
            while time.monotonic() < deadline:
                msg = bus.recv(timeout=0.1)
                if msg is not None:
                    total_frames += 1
                    overhead = 67 if msg.is_extended_id else 47
                    total_bits += overhead + 8 * msg.dlc
                    cid = f"0x{msg.arbitration_id:03X}"
                    id_counts[cid] = id_counts.get(cid, 0) + 1

        bits_per_sec = total_bits / dur
        bus_load_pct = (bits_per_sec / max(1, nominal_bitrate)) * 100.0
        status = "OK"
        if bus_load_pct > 80.0:
            status = "CRITICAL: Bus load > 80% — high risk of frame drop / latency jitter."
        elif bus_load_pct > 50.0:
            status = "WARNING: Bus load > 50% — monitor PDO/SYNC intervals."

        return json.dumps(
            {
                "interface": interface,
                "duration_sec": dur,
                "nominal_bitrate": nominal_bitrate,
                "total_frames": total_frames,
                "frames_per_sec": round(total_frames / dur, 2),
                "estimated_bus_load_percent": round(bus_load_pct, 2),
                "status": status,
                "top_cob_ids": dict(sorted(id_counts.items(), key=lambda x: x[1], reverse=True)[:15]),
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"interface": interface, "ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def canopen_scan_nodes(interface: str = "can0", duration_sec: float = 3.0) -> str:
    """[READ] Scan a CANopen bus for Heartbeats (`0x700+ID`), EMCY (`0x080+ID`), TPDOs, and SDOs."""
    dur = max(0.5, min(float(duration_sec), 10.0))
    nmt_states = {
        0x00: "BOOT_UP",
        0x04: "STOPPED",
        0x05: "OPERATIONAL",
        0x7F: "PRE_OPERATIONAL",
    }
    discovered_nodes: Dict[int, Dict[str, Any]] = {}

    def _ensure_node(nid: int) -> Dict[str, Any]:
        if nid not in discovered_nodes:
            discovered_nodes[nid] = {
                "node_id": nid,
                "nmt_state": "UNKNOWN",
                "heartbeat_count": 0,
                "tpdo_seen": [],
                "emcy_frames": [],
                "sdo_seen": False,
            }
        return discovered_nodes[nid]

    try:
        with can.Bus(interface="socketcan", channel=interface) as bus:
            deadline = time.monotonic() + dur
            while time.monotonic() < deadline:
                msg = bus.recv(timeout=0.1)
                if msg is None or msg.is_extended_id:
                    continue
                cob_id = msg.arbitration_id
                func_code = cob_id & 0x780
                node_id = cob_id & 0x07F
                if node_id == 0:
                    continue

                if func_code == 0x700 and msg.dlc >= 1:
                    info = _ensure_node(node_id)
                    state_byte = msg.data[0] & 0x7F
                    info["nmt_state"] = nmt_states.get(state_byte, f"RAW_0x{state_byte:02X}")
                    info["heartbeat_count"] += 1
                elif func_code == 0x080 and msg.dlc >= 4:
                    info = _ensure_node(node_id)
                    err_code = int.from_bytes(msg.data[0:2], "little")
                    err_reg = msg.data[2]
                    info["emcy_frames"].append(
                        {
                            "error_code": f"0x{err_code:04X}",
                            "meaning": ERROR_CODE_TABLE.get(err_code, "Vendor-specific"),
                            "error_register": f"0x{err_reg:02X}",
                            "raw_hex": msg.data.hex(" ").upper(),
                        }
                    )
                elif func_code in (0x180, 0x280, 0x380, 0x480):
                    info = _ensure_node(node_id)
                    pdo_num = (func_code >> 8)
                    label = f"TPDO{pdo_num} (0x{cob_id:03X})"
                    if label not in info["tpdo_seen"]:
                        info["tpdo_seen"].append(label)
                elif func_code == 0x580:
                    info = _ensure_node(node_id)
                    info["sdo_seen"] = True

        return json.dumps(
            {
                "interface": interface,
                "duration_sec": dur,
                "nodes_discovered": len(discovered_nodes),
                "nodes": list(discovered_nodes.values()),
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"interface": interface, "ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def canopen_decode_cia402_statusword(statusword_hex_or_int: str) -> str:
    """[READ] Decode a 16-bit CiA 402 Statusword (`0x6041`) value."""
    raw_str = statusword_hex_or_int.strip()
    val = int(raw_str, 16) if raw_str.lower().startswith("0x") else int(raw_str, 0)

    if (val & 0x004F) == 0x0000:
        state = "NOT_READY_TO_SWITCH_ON"
        next_step = "Wait for drive initialization."
    elif (val & 0x004F) == 0x0040:
        state = "SWITCH_ON_DISABLED"
        next_step = "Send Controlword 0x0006 (Shutdown) to transition to READY_TO_SWITCH_ON."
    elif (val & 0x006F) == 0x0021:
        state = "READY_TO_SWITCH_ON"
        next_step = "Send Controlword 0x0007 (Switch On) to transition to SWITCHED_ON."
    elif (val & 0x006F) == 0x0023:
        state = "SWITCHED_ON"
        next_step = "Send Controlword 0x000F (Enable Operation) to enable motor torque/motion."
    elif (val & 0x006F) == 0x0027:
        state = "OPERATION_ENABLED"
        next_step = "Drive is active and ready to execute velocity/position targets."
    elif (val & 0x006F) == 0x0007:
        state = "QUICK_STOP_ACTIVE"
        next_step = "Quick stop is active. Send 0x0006 or 0x000F to recover."
    elif (val & 0x004F) == 0x000F:
        state = "FAULT_REACTION_ACTIVE"
        next_step = "Drive is stopping due to a fault. Read 0x603F Error Code."
    elif (val & 0x004F) == 0x0008:
        state = "FAULT"
        next_step = "Read Error Code (0x603F) first! Once resolved, send Controlword 0x0080 (Fault Reset)."
    else:
        state = "UNKNOWN_OR_VENDOR_SPECIFIC"
        next_step = "Inspect individual bits below."

    bits = {
        "bit0_ready_to_switch_on": bool(val & (1 << 0)),
        "bit1_switched_on": bool(val & (1 << 1)),
        "bit2_operation_enabled": bool(val & (1 << 2)),
        "bit3_fault": bool(val & (1 << 3)),
        "bit4_voltage_enabled": bool(val & (1 << 4)),
        "bit5_quick_stop_inactive": bool(val & (1 << 5)),
        "bit6_switch_on_disabled": bool(val & (1 << 6)),
        "bit7_warning": bool(val & (1 << 7)),
        "bit8_halt_or_manufacturer": bool(val & (1 << 8)),
        "bit9_remote_control_enabled": bool(val & (1 << 9)),
        "bit10_target_reached": bool(val & (1 << 10)),
        "bit11_internal_limit_active": bool(val & (1 << 11)),
        "bit12_setpoint_ack_or_speed_zero": bool(val & (1 << 12)),
        "bit13_following_error": bool(val & (1 << 13)),
    }

    return json.dumps(
        {
            "statusword_hex": f"0x{val:04X}",
            "statusword_int": val,
            "cia402_state": state,
            "recommended_action": next_step,
            "flags": bits,
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def canopen_decode_error_code(error_code_hex_or_int: str) -> str:
    """[READ] Decode a CiA 301 / CiA 402 / ZLAC8015D Error Code (`0x603F` or EMCY bytes 0..1)."""
    raw_str = error_code_hex_or_int.strip()
    code = int(raw_str, 16) if raw_str.lower().startswith("0x") else int(raw_str, 0)

    exact = ERROR_CODE_TABLE.get(code)
    zlac_flags = []
    if code != 0:
        zlac_bit_map = {
            0x0001: "Overvoltage",
            0x0002: "Undervoltage",
            0x0004: "Overcurrent",
            0x0008: "Overload",
            0x0010: "Current out of tolerance",
            0x0020: "Encoder out of tolerance",
            0x0040: "Velocity out of tolerance",
            0x0080: "Reference voltage error",
        }
        for bit, desc in zlac_bit_map.items():
            if code & bit:
                zlac_flags.append(desc)

    return json.dumps(
        {
            "error_code_hex": f"0x{code:04X}",
            "cia402_meaning": exact or "Unknown / Vendor-specific code",
            "zlac8015d_bitmask_interpretation": zlac_flags,
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def canopen_read_sdo(
    interface: str,
    node_id: int,
    index_hex: str,
    subindex_hex: str = "0x00",
    signed: bool = False,
    timeout_sec: float = 1.0,
) -> str:
    """[READ] Perform an expedited CANopen SDO Upload (Read) from `node_id` on `interface`."""
    if not (1 <= node_id <= 127):
        return json.dumps({"ok": False, "error": "node_id must be in 1..127"})

    idx = int(index_hex.strip(), 16) if index_hex.strip().lower().startswith("0x") else int(index_hex.strip(), 0)
    sub = int(subindex_hex.strip(), 16) if subindex_hex.strip().lower().startswith("0x") else int(subindex_hex.strip(), 0)

    req_cob = 0x600 + node_id
    resp_cob = 0x580 + node_id
    req_data = bytes([0x40, idx & 0xFF, (idx >> 8) & 0xFF, sub & 0xFF, 0, 0, 0, 0])

    try:
        can_filters = [{"can_id": resp_cob, "can_mask": 0x7FF}]
        with can.Bus(interface="socketcan", channel=interface, can_filters=can_filters) as bus:
            msg_out = can.Message(arbitration_id=req_cob, data=req_data, is_extended_id=False)
            bus.send(msg_out)

            deadline = time.monotonic() + max(0.1, min(float(timeout_sec), 5.0))
            while time.monotonic() < deadline:
                rx = bus.recv(timeout=0.1)
                if rx is None or rx.arbitration_id != resp_cob or rx.dlc < 8:
                    continue
                rx_idx = rx.data[1] | (rx.data[2] << 8)
                rx_sub = rx.data[3]
                if rx_idx != idx or rx_sub != sub:
                    continue

                scs = rx.data[0]
                if scs == 0x80:
                    abort_code = int.from_bytes(rx.data[4:8], "little")
                    return json.dumps(
                        {
                            "ok": False,
                            "node_id": node_id,
                            "index": f"0x{idx:04X}",
                            "subindex": f"0x{sub:02X}",
                            "status": "SDO_ABORT",
                            "abort_code": f"0x{abort_code:08X}",
                        },
                        indent=2,
                    )

                n_unused = (scs >> 2) & 0x03 if (scs & 0x01) else 0
                size = 4 - n_unused
                raw_bytes = rx.data[4 : 4 + size]
                val_int = int.from_bytes(raw_bytes, byteorder="little", signed=signed)

                result: Dict[str, Any] = {
                    "ok": True,
                    "node_id": node_id,
                    "index": f"0x{idx:04X}",
                    "object_name": CIA402_COMMON_OD.get(idx, "Custom/Vendor Object"),
                    "subindex": f"0x{sub:02X}",
                    "size_bytes": size,
                    "value_int": val_int,
                    "value_hex": f"0x{int.from_bytes(raw_bytes, 'little'):0{size*2}X}",
                    "raw_response": rx.data.hex(" ").upper(),
                }
                if idx == 0x6041:
                    result["decoded_statusword"] = json.loads(canopen_decode_cia402_statusword(hex(val_int)))
                elif idx == 0x603F:
                    result["decoded_error"] = json.loads(canopen_decode_error_code(hex(val_int)))
                return json.dumps(result, indent=2, ensure_ascii=False)

        return json.dumps(
            {
                "ok": False,
                "node_id": node_id,
                "index": f"0x{idx:04X}",
                "subindex": f"0x{sub:02X}",
                "error": f"SDO read timeout ({timeout_sec}s): No response on 0x{resp_cob:03X}.",
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def can_send_frame_safe(
    interface: str,
    arbitration_id_hex: str,
    data_hex: str,
    is_extended_id: bool = False,
    confirm: bool = False,
) -> str:
    """[DANGEROUS - CONFIRMATION REQUIRED] Send a single CAN frame on `interface`."""
    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Sending CAN frame to {interface} (ID={arbitration_id_hex}, Data={data_hex}) requires confirm=True.",
            },
            indent=2,
        )

    arb_id = int(arbitration_id_hex.strip(), 16)
    clean_hex = data_hex.replace(" ", "").replace("0x", "")
    payload = bytes.fromhex(clean_hex)
    if len(payload) > 8:
        return json.dumps({"ok": False, "error": "Standard CAN frame payload cannot exceed 8 bytes."})

    try:
        with can.Bus(interface="socketcan", channel=interface) as bus:
            msg = can.Message(arbitration_id=arb_id, data=payload, is_extended_id=is_extended_id)
            bus.send(msg)
        return json.dumps(
            {
                "ok": True,
                "interface": interface,
                "arbitration_id": f"0x{arb_id:03X}",
                "dlc": len(payload),
                "data_hex": payload.hex(" ").upper(),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def canopen_write_sdo_safe(
    interface: str,
    node_id: int,
    index_hex: str,
    subindex_hex: str,
    value_int: int,
    size_bytes: int = 2,
    signed: bool = False,
    timeout_sec: float = 1.0,
    confirm: bool = False,
) -> str:
    """[DANGEROUS - CONFIRMATION REQUIRED] Perform an expedited CANopen SDO Download (Write)."""
    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Writing SDO to Node {node_id} (Index={index_hex}, Sub={subindex_hex}, Value={value_int}) requires confirm=True.",
            },
            indent=2,
        )

    if size_bytes not in (1, 2, 4):
        return json.dumps({"ok": False, "error": "size_bytes must be 1, 2, or 4."})

    idx = int(index_hex.strip(), 16) if index_hex.strip().lower().startswith("0x") else int(index_hex.strip(), 0)
    sub = int(subindex_hex.strip(), 16) if subindex_hex.strip().lower().startswith("0x") else int(subindex_hex.strip(), 0)
    ccs_map = {1: 0x2F, 2: 0x2B, 4: 0x23}
    ccs = ccs_map[size_bytes]

    val_bytes = int(value_int).to_bytes(size_bytes, byteorder="little", signed=signed).ljust(4, b"\x00")
    req_data = bytes([ccs, idx & 0xFF, (idx >> 8) & 0xFF, sub & 0xFF]) + val_bytes

    req_cob = 0x600 + node_id
    resp_cob = 0x580 + node_id

    try:
        can_filters = [{"can_id": resp_cob, "can_mask": 0x7FF}]
        with can.Bus(interface="socketcan", channel=interface, can_filters=can_filters) as bus:
            bus.send(can.Message(arbitration_id=req_cob, data=req_data, is_extended_id=False))
            deadline = time.monotonic() + max(0.1, min(float(timeout_sec), 5.0))
            while time.monotonic() < deadline:
                rx = bus.recv(timeout=0.1)
                if rx is None or rx.arbitration_id != resp_cob or rx.dlc < 8:
                    continue
                rx_idx = rx.data[1] | (rx.data[2] << 8)
                rx_sub = rx.data[3]
                if rx_idx != idx or rx_sub != sub:
                    continue
                if rx.data[0] == 0x60:
                    return json.dumps(
                        {
                            "ok": True,
                            "node_id": node_id,
                            "index": f"0x{idx:04X}",
                            "subindex": f"0x{sub:02X}",
                            "written_value": value_int,
                            "status": "SDO_WRITE_ACK",
                        },
                        indent=2,
                    )
                if rx.data[0] == 0x80:
                    abort_code = int.from_bytes(rx.data[4:8], "little")
                    return json.dumps(
                        {
                            "ok": False,
                            "status": "SDO_ABORT",
                            "abort_code": f"0x{abort_code:08X}",
                        },
                        indent=2,
                    )
        return json.dumps({"ok": False, "error": "SDO write response timeout"}, indent=2)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)


@mcp.tool()
def canopen_nmt_command_safe(
    interface: str,
    node_id: int,
    command: str,
    confirm: bool = False,
) -> str:
    """[DANGEROUS - CONFIRMATION REQUIRED] Send a CANopen NMT network management command (`COB-ID 0x000`)."""
    cmd_map = {
        "start": 0x01,
        "stop": 0x02,
        "pre-op": 0x80,
        "reset-node": 0x81,
        "reset-comm": 0x82,
    }
    if command not in cmd_map:
        return json.dumps({"ok": False, "error": f"Invalid NMT command. Choose from {list(cmd_map.keys())}"})

    if not confirm:
        return json.dumps(
            {
                "ok": False,
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Sending NMT '{command}' to node_id={node_id} on {interface} requires confirm=True.",
            },
            indent=2,
        )

    try:
        with can.Bus(interface="socketcan", channel=interface) as bus:
            bus.send(can.Message(arbitration_id=0x000, data=bytes([cmd_map[command], node_id & 0x7F]), is_extended_id=False))
        return json.dumps(
            {
                "ok": True,
                "interface": interface,
                "node_id": node_id,
                "nmt_command": command,
                "cs_byte": f"0x{cmd_map[command]:02X}",
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)


if __name__ == "__main__":
    mcp.run()
