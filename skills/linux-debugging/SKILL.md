---
name: linux-debugging
description: >-
  Systematic Ubuntu 22.04 / Linux diagnostic methodology for robotics systems:
  systemd services, journalctl, udev rules, USB/EMI disconnects, Ethernet/DDS networking,
  kernel drivers, permissions (dialout/plugdev), and CPU/Memory/Real-Time performance.
---

# Linux System Debugging Skill for Robotics

Use this skill alongside `hw-linux-serial-diag` when diagnosing OS-level issues on the development PC or onboard robot computer (IPC, DLAP-411, Jetson Orin).

## 1. USB / Serial / CAN Device Disappearance & EMI Resets
1. Run `linux_hardware_fault_diagnose(subsystem="kernel_EMI")` and `serial_list_ports_detailed()`.
2. Look for `usb X-Y: USB disconnect, device number N` or `emi` / `over-current` in `dmesg`:
   - If disconnects happen when motors spin up: **Ground loop or EMI coupling** from motor power cables to USB cables. Recommend shielded USB cables with ferrite cores, USB isolators (ADuM3160/4160), and star grounding.
3. Verify persistent `udev` symlinks (`/etc/udev/rules.d/99-robot-devices.rules`):
   - Never hardcode `/dev/ttyUSB0` or `/dev/ttyUSB1` in ROS2 launch files because enumeration order changes across reboots. Match by `ATTRS{idVendor}`, `ATTRS{idProduct}`, `ATTRS{serial}`, or `KERNELS` port path.
4. Check group permissions: user must belong to `dialout` and `plugdev`.

## 2. Multi-Machine ROS2 DDS & Ethernet Networking
1. Check `ip -br addr` and `ip route`:
   - Verify Ethernet interface linked to LiDAR/Robot is `UP` with correct static IP / netmask.
2. When ROS2 topics are not visible across PC $\leftrightarrow$ Robot SSH:
   - Verify matching `ROS_DOMAIN_ID` and `RMW_IMPLEMENTATION` (`rmw_cyclonedds_cpp` vs `rmw_fastrtps_cpp`).
   - Check firewall (`ufw status`) and multicast routing (`ip link show` must include `MULTICAST`).

## 3. Systemd Startup Services & Resource Contention
1. Inspect failed background services: `systemctl --failed` and `journalctl -u <service_name> -n 100 --no-pager`.
2. Check CPU throttling, RAM swap thrashing (`free -h`), and disk full (`df -h` — ROS2 bag files or `~/.ros/log` filling `/` or `/home` will prevent nodes from starting!).
