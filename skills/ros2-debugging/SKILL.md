---
name: ros2-debugging
description: >-
  Systematic 10-step ROS2 Humble debugging methodology for nodes, topics, publishers,
  subscribers, QoS compatibility, TF tree, timestamps, parameters, launch files, and lifecycle nodes.
  Use whenever diagnosing missing topics, broken transforms, QoS mismatches, or ROS2 node failures.
---

# ROS2 Debugging Skill (Evidence-Based 10-Step Protocol)

Never guess or modify source code before completing the evidence collection sequence below using the `ros2-control-diag` MCP tools.

## Mandatory 10-Step Diagnostic Workflow

1. **Inspect Computation Graph (`ros2_graph_overview`)**:
   - Verify whether the target node is actually running and whether its namespace matches expectations.
   - Check `ROS_DOMAIN_ID` and `RMW_IMPLEMENTATION` consistency between terminals/hosts.

2. **Inspect Target Topic (`ros2_topic_inspect`)**:
   - Verify exact topic name and message type (`sensor_msgs/msg/LaserScan`, `nav_msgs/msg/Odometry`, etc.).

3. **Verify Publisher Count & Endpoints**:
   - If `Publisher count == 0`, the upstream driver/node crashed, failed lifecycle activation, or remapped the topic name.

4. **Verify Subscriber Count & Endpoints**:
   - If `Subscriber count == 0`, the downstream consumer is listening on a different topic name or namespace.

5. **Audit QoS Compatibility (`ros2 topic info -v`)**:
   - Compare Publisher vs Subscriber QoS:
     - **Reliability**: `BEST_EFFORT` publisher **cannot** connect to a `RELIABLE` subscriber.
     - **Durability**: `VOLATILE` publisher **cannot** satisfy a `TRANSIENT_LOCAL` subscriber (common on `/map` and `/robot_description`).

6. **Verify Data Reception & Frequency (`ros2_topic_echo_once`, `ros2_topic_hz_check`)**:
   - Confirm messages actually flow and measure whether frequency (Hz) matches specification without large standard deviation.

7. **Audit TF Tree (`ros2_tf_diagnostics`)**:
   - Verify continuous transform chain: `map -> odom -> base_footprint / base_link -> sensor_frame`.
   - Ensure no multiple publishers are fighting over the same child `frame_id` (e.g. both wheel odom node and `ekf_filter_node` publishing `odom -> base_link`).

8. **Verify Header Timestamp & `frame_id`**:
   - Check `header.stamp` against current ROS clock (`/clock` if `use_sim_time: true`, system clock if `false`).
   - Mixed `use_sim_time` settings cause TF extrapolation into the past/future errors.

9. **Inspect Runtime Parameters (`ros2_param_get`)**:
   - Dump node parameters to verify YAML config was actually loaded (watch out for mismatched node names in YAML headers vs Launch `name=`).

10. **Inspect Node Logs & Lifecycle State (`ros2_lifecycle_control`)**:
    - For Lifecycle nodes (Nav2, slam_toolbox, drivers), verify state is `active [3]`, not stuck in `unconfigured [1]` or `inactive [2]`.
    - Only propose code/config fixes after pinpointing the exact failing step above.
