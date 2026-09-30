---
name: socketcan-debugging
description: >-
  Mandatory SocketCAN hardware and kernel-level diagnostic protocol.
  Requires checking ip link details, bitrate, controller state (ERROR-ACTIVE, ERROR-PASSIVE, BUS-OFF),
  TX/RX error counters, bus load, termination resistors, and ACK before drawing any conclusion.
---

# SocketCAN Debugging Skill

Never guess why a CAN bus is failing. You MUST execute the `can-canopen-diag` MCP tools in the exact order below before proposing fixes.

## Mandatory Inspection Sequence

1. **Interface Presence (`can_list_interfaces`)**:
   - Confirm `can0` / `can1` exists. If missing, check `dmesg` and `lsusb` via `hw-linux-serial-diag` (`gs_usb`, `peak_usb`, `mttcan`, `slcan`).

2. **Controller State & Error Counters (`can_interface_diagnostics`)**:
   - Inspect `ip -details -statistics link show can0`:
     - **`ERROR-ACTIVE`** (`tx_err < 96`, `rx_err < 96`): Bus physical layer is healthy.
     - **`ERROR-WARNING`** (`96 <= err < 128`): Signal degradation, EMI from motor phases, or ground loop.
     - **`ERROR-PASSIVE`** (`tx_err >= 128`, `rx_err == 0`): Classic **No ACK** error. No other node on the bus acknowledged the transmitted frame.
     - **`ERROR-PASSIVE`** (`rx_err >= 128`): Bitrate mismatch, excessive stub length, or missing termination resistor.
     - **`BUS-OFF`** (`tx_err > 255`): Controller isolated itself from the bus due to CAN_H/CAN_L short, inverted CAN_H/CAN_L, or severe baudrate mismatch. Check `restart-ms` setting (recommend `restart-ms 100`).

3. **Bitrate & Sample Point Verification**:
   - Standard robotics bitrates: `500000` (500 kbps) or `250000` (250 kbps) or `1000000` (1 Mbps).
   - Every node on the bus MUST use the exact same bitrate. Sample point should typically be around `0.750` – `0.875` (CiA 301 recommends `87.5%`).

4. **Live Frame Capture & Bus Load (`can_dump_capture`, `can_bus_load_estimate`)**:
   - Verify whether periodic frames (Heartbeats `0x700+NodeID`, TPDOs) are present.
   - Check bus load percentage: keep below `50%` for deterministic real-time control.

5. **Physical Layer Checklist**:
   - With all devices powered OFF, measure resistance between `CAN_H` and `CAN_L`:
     - Must be $\approx 60\,\Omega$ (two $120\,\Omega$ termination resistors in parallel at the two physical ends of the bus).
     - If $\approx 120\,\Omega$: one termination resistor is missing.
     - If $\infty$ (open): both termination resistors are missing or cable is broken.
     - If $< 40\,\Omega$: too many devices have onboard $120\,\Omega$ switches enabled.
