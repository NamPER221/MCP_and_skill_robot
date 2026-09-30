---
name: robot-navigation
description: >-
  Systematic diagnostic methodology for robot localization, sensor fusion, and autonomous navigation:
  Wheel Odometry, robot_localization EKF, TF tree, SLAM (slam_toolbox / Cartographer), AMCL,
  and Nav2 planners, controllers, and costmaps.
---

# Robot Navigation, EKF & SLAM Debugging Skill

Use this skill when diagnosing `/odometry/filtered` drift, TF jumps, SLAM map distortion, or Nav2 navigation failures.

## 1. Diagnosing Odometry & EKF Drift (`/odometry/filtered`)

Follow this exact sequence using `ros2-control-diag`:

1. **Inspect Raw Inputs Independently**:
   - Echo `/wheel/odom` (or `/odom`) and `/imu/data`:
     - Verify `header.frame_id` and `child_frame_id` on each message.
     - Verify `header.stamp` synchronization: if timestamps between IMU and Wheel Odom differ by $> 0.1\,\text{s}$, EKF filter updates will lag or reject measurements.
2. **Audit Coordinate Convention (REP-103 / ENU)**:
   - Forward motion $\rightarrow +v_x$
   - Leftward motion $\rightarrow +v_y$
   - Counter-clockwise rotation (viewed from top) $\rightarrow +\omega_z$ and increasing $+\text{yaw}$.
   - **Common Bug**: IMU mounted upside-down or using NED convention ($+Z$ down, clockwise yaw positive) while wheel odom uses ENU ($+Z$ up, CCW yaw positive). Fusing opposing yaw signs causes violent EKF divergence!
3. **Audit `robot_localization` EKF Config (`ekf.yaml`)**:
   - Do **NOT** fuse both absolute pose $(X, Y)$ from wheel odom AND velocity $(\dot{X}, \dot{Y})$ from the same wheel odom source. Standard 2D mobile robot practice:
     - `odom0` (Wheel Odometry): fuse **only velocities** $v_x, v_y, \omega_z$ (`[false, false, false, false, false, false, true, true, false, false, false, true, false, false, false]`) or fuse $(X, Y)$ with `differential: true`.
     - `imu0` (IMU): fuse $\text{yaw}$ (or $\omega_z$) and optionally $a_x$ (`remove_gravitational_acceleration: true`).
   - Verify `publish_tf: true` is enabled ONLY in `ekf_filter_node`, and **disabled** (`publish_tf: false`) in the raw wheel odometry node so they do not fight over `odom -> base_link`!
4. **Audit Covariance Matrices**:
   - Zero diagonal values (`0.0`) in raw sensor `pose_covariance` or `twist_covariance` cause numerical instability in the Kalman gain calculation. Ensure realistic non-zero variances (e.g., $10^{-3}$ to $10^{-1}$).

## 2. Diagnosing SLAM & Nav2 Failures
1. **TF Chain Integrity (`ros2_tf_diagnostics`)**:
   - Confirm unbroken chain: `map -> odom -> base_link -> laser_frame`.
2. **Lifecycle States (`ros2_lifecycle_control`)**:
   - Check `bt_navigator`, `controller_server`, `planner_server`, `recoveries_server`/`behavior_server`, `amcl`/`slam_toolbox` are all in `active [3]`.
3. **Costmap & Footprint**:
   - Verify `robot_radius` or `footprint` polygon in `local_costmap` and `global_costmap` does not intersect the robot's own LiDAR mounting frame (causing self-obstacle clearing failure).
