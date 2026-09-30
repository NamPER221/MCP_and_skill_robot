---
name: canopen-debugging
description: >-
  Structured CANopen CiA 301 & CiA 402 diagnostic methodology following the
  NMT -> Node State -> SDO -> PDO -> SYNC -> Heartbeat -> Emergency (EMCY) hierarchy.
  Use when debugging CANopen motor drives (ZLAC8015D, Elmo, Kinco), encoders, or BMS.
---

# CANopen Debugging Skill (CiA 301 / CiA 402)

Always verify the lower SocketCAN layer (`socketcan-debugging`) is `ERROR-ACTIVE` before debugging the CANopen protocol layer. Follow the 7-layer CANopen diagnostic sequence below:

## 7-Layer CANopen Diagnostic Sequence

```text
1. NMT State -> 2. Heartbeat/Boot-up -> 3. Emergency (EMCY) -> 4. SDO Access -> 5. CiA 402 State Machine -> 6. PDO Mapping -> 7. SYNC Timing
```

### 1. NMT & Heartbeat Inspection (`canopen_scan_nodes`)
- Listen on `0x700 + NodeID`:
  - `0x00`: Boot-up
  - `0x04`: Stopped (PDOs disabled, SDO disabled)
  - `0x05`: Operational (PDOs and SDOs active)
  - `0x7F`: Pre-operational (SDOs active, PDOs disabled — node needs NMT `Start` `[0x01, NodeID]` on COB-ID `0x000` to process PDOs).

### 2. Emergency (EMCY) & Fault Register Check (`0x080 + NodeID`, `0x603F`, `0x1001`)
- Read `0x1001:00` (Error Register) and `0x603F:00` (Error Code) via `canopen_read_sdo`.
- Decode using `canopen_decode_error_code`. Never clear a fault before logging and explaining its root cause!

### 3. CiA 402 Drive State Machine (`0x6040` Controlword & `0x6041` Statusword)
- Read `0x6041:00` via `canopen_read_sdo` and decode with `canopen_decode_cia402_statusword`.
- Standard Enable Sequence (`0x6040` Controlword):
  1. `0x0006` (Shutdown) $\rightarrow$ State becomes `READY_TO_SWITCH_ON` (`0x0021`)
  2. `0x0007` (Switch On) $\rightarrow$ State becomes `SWITCHED_ON` (`0x0023`)
  3. `0x000F` (Enable Operation) $\rightarrow$ State becomes `OPERATION_ENABLED` (`0x0027`)
- Fault Recovery Sequence:
  - Rising edge on Bit 7 of Controlword: write `0x0080` to `0x6040:00`, then repeat `0x0006 -> 0x0007 -> 0x000F`.

### 4. Object Dictionary & Mode Verification
- Check `0x6060:00` (Modes of Operation) and `0x6061:00` (Modes of Operation Display).
- Check `0x606C` (Velocity Actual Value), `0x6064` (Position Actual Value), `0x60FF` (Target Velocity), `0x607A` (Target Position).

### 5. PDO & SYNC Verification
- Verify RPDO (`0x200/0x300/0x400/0x500 + NodeID`) and TPDO (`0x180/0x280/0x380/0x480 + NodeID`) communication parameters (`0x1400..0x1403`, `0x1800..0x1803`) and mapping objects (`0x1600..0x1603`, `0x1A00..0x1A03`).
- If transmission type is synchronous (`1..240`), verify a SYNC master is transmitting `COB-ID 0x080` at a steady period.
