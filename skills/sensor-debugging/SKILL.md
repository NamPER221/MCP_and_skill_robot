---
name: sensor-debugging
description: >-
  End-to-end sensor debugging methodology for LiDAR (2D/3D), IMU, RGB/Depth Cameras (RealSense/Orbbec),
  and Wheel Encoders. Follows the strict Hardware -> Driver -> ROS Topic -> Timestamp -> Frame -> QoS -> Consumer chain.
---

# Sensor Debugging Skill (Hardware-to-Consumer Chain)

Use this skill when diagnosing issues with LiDAR (`/scan`, `/points`), IMU (`/imu/data`), Cameras, or Wheel Encoders. Follow the bottom-up pipeline strictly:

## Pipeline Verification Sequence

```text
1. Hardware Physical/Bus -> 2. Linux Kernel/Driver -> 3. ROS2 Driver Node -> 4. ROS2 Topic -> 5. Timestamp/Clock -> 6. TF Frame -> 7. Downstream Consumer
```

### Step 1: Physical & Interface Layer (`hw-linux-serial-diag`)
- **USB / Serial Sensors (IMU, 2D LiDAR, Depth Camera)**:
  - Run `linux_hardware_fault_diagnose(subsystem="usb")` and `serial_list_ports_detailed()`.
  - Check `dmesg` for EMI resets (`usb X-Y: USB disconnect`, `ch341-uart`, `cp210x`, `ftdi_sio` disconnects, or USB power brownouts).
  - Verify user is in `dialout`/`plugdev` and `/dev/ttyUSB*` or `/dev/serial/by-id/*` exists.
- **Ethernet LiDARs (C200, Sick, Velodyne, Ouster, Livox)**:
  - Check interface IP/subnet (`ip -br addr`), link carrier state (`UP`), ping sensor IP, and inspect UDP port reception.

### Step 2: Automated ROS2 Sensor Pipeline Check (`ros2_diagnose_sensor_pipeline`)
- Run `ros2_diagnose_sensor_pipeline(topic_name, expected_frame_id)` from `ros2-control-diag`.
- Verify:
  - **LiDAR (`/scan`)**: `range_min`, `range_max`, `ranges` array not all `inf`/`NaN`, publishing rate stable (e.g., 10–40 Hz).
  - **IMU (`/imu/data` or `/imu`)**:
    - Check linear acceleration (`z ≈ +9.81 m/s²` when flat).
    - Check angular velocity bias at rest (`≈ 0 rad/s`).
    - Check `orientation_covariance[0]`, `angular_velocity_covariance[0]`, `linear_acceleration_covariance[0]`: must NOT be `-1` if used by EKF, and must not be all `0.0` (singular covariance matrix in EKF).
  - **Wheel Encoder / Odometry (`/wheel/odom`)**:
    - Check encoder tick sign conventions: forward motion must yield `+linear.x`, counter-clockwise rotation (REP-103: +X forward, +Y left, +Z up) must yield `+angular.z`.

### Step 3: Frame & Extrinsic Alignment (`ros2_tf_diagnostics`)
- Confirm `header.frame_id` in sensor message exists in `/tf` or `/tf_static`.
- Check static transform orientation (e.g. LiDAR mounted upside-down or rotated 180 deg yaw without matching URDF `rpy`).
