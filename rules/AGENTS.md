# ROBOTICS & HARDWARE SAFETY RULES (READ / WRITE / DANGEROUS TIERS)

## 1. Phân tầng quyền thực thi (3-Tier Execution Policy)

Mọi thao tác với hệ thống Linux, ROS2, CAN/CANopen, Serial/Modbus và Robot phải tuân thủ 3 mức:

### Tier 1: READ (Được phép chạy tự động để thu thập bằng chứng)
- `ros2 node list`, `ros2 topic list`, `ros2 topic info -v`, `ros2 topic echo --once`, `ros2 topic hz`
- `can_list_interfaces`, `can_interface_diagnostics` (`ip -details -statistics link show`), `can_dump_capture`, `canopen_scan_nodes`, `canopen_read_sdo`
- `serial_list_ports_detailed`, `modbus_rtu_read_registers`, `linux_hardware_fault_diagnose`, `ssh_remote_diagnose`
- `git status`, `git diff`, `git log`, `cat`, `grep`, `find`

### Tier 2: WRITE (Kiểm soát phạm vi Workspace)
- Chỉ được phép chỉnh sửa mã nguồn và build (`colcon build`) trong các thư mục dự án được phép:
  - `/home/namnc/base_kit`
  - `/home/namnc/ros2_ws`
  - `/home/namnc/vehichi-dc`
  - `/home/namnc/Zlac_test`
  - `/home/namnc/V-SLam`
  - `/home/namnc/.gemini/`
- **Tuyệt đối cấm** sửa đổi: `/etc`, `/root`, `/boot`, `/usr` khi chưa được người dùng yêu cầu và xác nhận rõ ràng.

### Tier 3: DANGEROUS (Bắt buộc Human-in-the-Loop Confirmation)
- Mọi thao tác làm chuyển động cơ cấu chấp hành hoặc thay đổi trạng thái phần cứng/hệ thống bắt buộc phải hỏi xác nhận người dùng trước khi truyền `confirm=True`:
  - `ros2_publish_cmd_vel_safe` (luôn áp dụng Velocity Clamping và tự động dừng sau `duration_sec`)
  - `can_send_frame_safe`, `canopen_write_sdo_safe`, `canopen_nmt_command_safe`
  - `modbus_rtu_write_register_safe`
  - `sudo`, `systemctl restart/stop`, `reboot`, `shutdown`, `git push`
- Ngoại lệ duy nhất: Lệnh dừng khẩn cấp `ros2_emergency_stop` được phép gọi ngay lập tức để đảm bảo an toàn.
