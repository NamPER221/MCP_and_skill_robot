---
name: motor-control
description: >-
  Diagnostic and control methodology for robot actuators: BLDC/DC motors, ZLAC8015D dual servo drivers,
  encoders, PID loops, PWM, velocity/acceleration/current limits, and kinematics conversion.
  Use when debugging motor non-response, runaway, oscillation, odometry scaling errors, or fault trips.
---

# Motor Control & Actuator Debugging Skill

Follow this structured workflow when analyzing or controlling robot drive systems (differential drive, mecanum, ackermann) and motor controllers (ZLAC8015D, CiA 402 drives, STM32 PWM/FOC drivers).

## 1. Safety Rules Before Any Motion Command
- Never send unbounded velocity commands. Always use `ros2_publish_cmd_vel_safe` with `confirm=True`, velocity clamping, and automatic stop timeout, or keep `ros2_emergency_stop` ready.
- When testing on hardware for the first time, recommend lifting drive wheels off the ground (bench test).

## 2. Diagnostic Checklist for "Motor Does Not Move"
1. **Command Layer (ROS2)**:
   - Is `/cmd_vel` being published? Check `ros2_topic_inspect("/cmd_vel")`.
   - Is `twist_mux` or safety lock overriding `/cmd_vel` with zero twist?
2. **Kinematics & Driver Node**:
   - Check wheel radius $R$, wheel separation $L$, and gear ratio $G$:
     $$v_L = v_x - \frac{\omega_z \cdot L}{2}, \quad v_R = v_x + \frac{\omega_z \cdot L}{2}$$
     $$\text{RPM} = \frac{v}{2 \pi R} \times 60 \times G$$
   - Check left/right motor polarity inversion (on differential drive, one side is physically mirrored and often requires sign inversion).
3. **Bus Layer (CAN / CANopen / RS485)**:
   - Run `can_interface_diagnostics("can0")` and `canopen_read_sdo` on `0x6041` (Statusword) & `0x603F` (Error Code).
   - Verify CiA 402 state machine reached `OPERATION_ENABLED` (`Statusword & 0x006F == 0x0027`), not stuck in `SWITCH_ON_DISABLED` (`0x0040`) or `FAULT` (`Bit 3 = 1`).
   - Verify `0x6060` (Modes of Operation) matches control mode (`3` = Profile Velocity, `1` = Profile Position, `-3` = ZLAC Velocity mode).
4. **Power & Hardware Protection**:
   - Check Emergency Stop (E-Stop) contactor, BMS discharge FET state, under-voltage/over-current fault bits, and Hall/Encoder cable continuity.

## 3. Diagnostic Checklist for Oscillation / Poor Tracking
- Compare target velocity (`0x60FF`) vs actual velocity (`0x606C`).
- Check Acceleration (`0x6083`) and Deceleration (`0x6084`) ramps: overly aggressive ramps cause overcurrent trips (`0x2300` / `0xFF04`) or wheel slip.
- Verify encoder resolution (PPR / CPR $\times 4$ quadrature) configured in the driver matches the physical encoder.
