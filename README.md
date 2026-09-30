# Robotics MCP & Skills Suite for Antigravity (Ubuntu 22.04 + ROS2 Humble)

Bộ công cụ **MCP Servers + Skills + Safety Rules** chuyên dụng cho lập trình, điều khiển và chẩn đoán lỗi hệ thống Robot trên Linux (`Ubuntu 22.04`, `ROS2 Humble`, `SocketCAN`, `CANopen CiA 301/402`, `ZLAC8015D`, `RS485/Modbus RTU`, `STM32`, `Gazebo`, `KiCad BLDC`).

---

## 1. Kiến trúc Tổng thể

```text
                       ┌──────────────────────┐
                       │   AI Coding Agent    │
                       └──────────┬───────────┘
                                  │
             ┌────────────────────┴────────────────────┐
             ▼                                         ▼
   ┌───────────────────┐                     ┌───────────────────┐
   │   9 Methodology   │                     │   4 Custom MCP    │
   │      Skills       │                     │  Servers (36 Tools)│
   └─────────┬─────────┘                     └─────────┬─────────┘
             │                                         │
             ├─ ros2-debugging                         ├─ ros2-control-diag
             ├─ sensor-debugging                       ├─ can-canopen-diag
             ├─ motor-control                          ├─ hw-linux-serial-diag
             ├─ socketcan-debugging                    └─ gazebo-sim-control
             ├─ canopen-debugging
             ├─ embedded-debugging
             ├─ robot-navigation
             ├─ linux-debugging
             └─ kicad-hardware-design
```

### Phân tầng An toàn (`rules/AGENTS.md`)
- **Tier 1 — `READ` (Tự động):** Thu thập bằng chứng từ ROS2 graph, `candump`, `ip -details link`, SDO upload, Modbus read, `dmesg`, SSH diagnostics.
- **Tier 2 — `WRITE` (Giới hạn Workspace):** Chỉ cho phép chỉnh sửa/build trong các workspace được cấp phép; cấm sửa `/etc`, `/root`, `/boot`, `/usr`.
- **Tier 3 — `DANGEROUS` (Bắt buộc xác nhận `confirm=True`):** Mọi lệnh tác động lên cơ cấu chấp hành (`cmd_vel`, `cansend`, `canopen_write_sdo`, `canopen_nmt`, `modbus_write`, `gazebo_spawn/set_state`) đều khóa cứng `confirm=True` trong code và áp dụng **Velocity Clamping + Auto-Stop Timeout**. Riêng `ros2_emergency_stop` được phép kích hoạt ngay lập tức.

---

## 2. Danh mục 4 MCP Servers (36 Tools)

| MCP Server | File | Số Tools | Chức năng chính |
| :--- | :--- | :---: | :--- |
| **`ros2-control-diag`** | `mcp_servers/ros2_control_diag_mcp.py` | **13** | Kiểm tra Graph, Node, Topic, phát hiện lệch QoS (`BEST_EFFORT` vs `RELIABLE`), đo tần số `hz`, kiểm tra cây TF, chẩn đoán tự động pipeline cảm biến, phát `cmd_vel` có giới hạn tốc độ & phanh tự động, gọi Service & Lifecycle. |
| **`can-canopen-diag`** | `mcp_servers/can_canopen_mcp.py` | **11** | Phân tích trạng thái SocketCAN (`ERROR-ACTIVE`, `ERROR-PASSIVE`, `BUS-OFF`, `berr-counter tx/rx`), bắt gói CAN, tính % tải bus, quét mạng CANopen, đọc/ghi SDO (`0x600`/`0x580`), gửi NMT (`0x000`), giải mã `Statusword (0x6041)` & `Error Code (0x603F)` chuẩn CiA 402 và ZLAC8015D. |
| **`hw-linux-serial-diag`** | `mcp_servers/hw_linux_serial_mcp.py` | **7** | Liệt kê chi tiết cổng Serial/USB (`VID:PID`, `/dev/serial/by-id`, nhóm `dialout`), đọc/ghi/quét slave **Modbus RTU** (kèm kiểm tra CRC-16), chẩn đoán lỗi phần cứng Linux (nhiễu EMI rớt USB trong `dmesg`, `systemd`, `network`) và chẩn đoán robot từ xa qua SSH. |
| **`gazebo-sim-control`** | `mcp_servers/gazebo_sim_mcp.py` | **5** | Kiểm tra trạng thái Gazebo & `/clock`, tạm dừng/tiếp tục/reset physics, spawn/xóa model URDF/SDF và đặt pose/velocity cho robot trong mô phỏng. |

---

## 3. Danh mục 9 Skills Chuyên sâu

1. **`ros2-debugging`**: Quy trình 10 bước kiểm tra Graph $\rightarrow$ Topic $\rightarrow$ Publisher/Subscriber $\rightarrow$ QoS $\rightarrow$ Data/Hz $\rightarrow$ TF $\rightarrow$ Timestamp $\rightarrow$ Parameters $\rightarrow$ Lifecycle.
2. **`sensor-debugging`**: Chẩn đoán chuỗi `Hardware -> Driver -> ROS Topic -> Timestamp -> Frame -> QoS -> Consumer` cho LiDAR, IMU, Camera, Depth, Encoder.
3. **`motor-control`**: Phân tích động học vi sai, PID, giới hạn vận tốc/gia tốc/dòng điện, ZLAC8015D & BLDC driver.
4. **`socketcan-debugging`**: Kiểm tra bắt buộc `ip -details -statistics link`, bitrate, sample-point, bộ đếm lỗi `tx/rx`, trở đầu cuối $120\,\Omega$ ($60\,\Omega$ tổng trở) và ACK.
5. **`canopen-debugging`**: Quy trình 7 tầng `NMT -> Heartbeat -> EMCY -> SDO -> CiA 402 State Machine -> PDO -> SYNC`.
6. **`embedded-debugging`**: Debug STM32/ESP32 (Clock tree `HSE_VALUE`, RS485 `TC` flag, STM32 bxCAN filter bank, Timer Encoder 16-bit overflow, PWM `MOE`/Dead-time, DMA/Cache).
7. **`robot-navigation`**: Chẩn đoán lệch `/odometry/filtered`, cấu hình `robot_localization` EKF, quy ước trục REP-103 (ENU), ma trận hiệp phương sai, SLAM và Nav2.
8. **`linux-debugging`**: Chẩn đoán nhiễu EMI làm rớt USB, quy tắc `udev` cố định cổng thiết bị, quyền `dialout`/`plugdev`, mạng DDS multicast và `systemd`.
9. **`kicad-hardware-design`**: Quy trình 12 bước kiểm tra thiết kế mạch công suất BLDC 3 pha 24V/48V (Bootstrap diode/cap, Gate resistor, Miller effect, Dead-time, Shunt Kelvin sense, Op-amp common-mode, TVS, tách mass `PGND`/`AGND`).

---

## 4. Hướng dẫn Cài đặt

### 4.1. Yêu cầu Hệ thống (Prerequisites)
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-serial can-utils iproute2 openssh-client
# Cấp quyền truy cập cổng Serial/USB (đăng xuất & đăng nhập lại sau khi chạy):
sudo usermod -aG dialout,plugdev "$USER"
```

### 4.2. Cài đặt Tự động (Khuyên dùng)
Clone repository về máy và chạy script `install.sh`:
```bash
git clone <URL_REPO_CUA_BAN> ~/.gemini/config/plugins/robotics
cd ~/.gemini/config/plugins/robotics
chmod +x install.sh
./install.sh
```
Script `install.sh` sẽ tự động:
1. Tạo môi trường ảo `.venv` với cờ `--system-site-packages` (kế thừa `rclpy` từ `/opt/ros/humble`).
2. Cài đặt `mcp`, `python-can`, `pyserial` từ `requirements.txt`.
3. Tự động cập nhật đường dẫn tuyệt đối vào `mcp_config.json`.
4. Kích hoạt `"robotics": {"enabled": true}` trong `~/.gemini/config/config.json`.

### 4.3. Kiểm tra Hoạt động (Verification)
Chạy lệnh sau để xác nhận cả 4 MCP servers đăng ký đủ 36 tools:
```bash
~/.gemini/config/plugins/robotics/.venv/bin/python3 -c "
import asyncio, sys
sys.path.insert(0, '$HOME/.gemini/config/plugins/robotics/mcp_servers')
import ros2_control_diag_mcp as r, can_canopen_mcp as c, hw_linux_serial_mcp as h, gazebo_sim_mcp as g
async def main():
    for name, srv in [('ros2', r.mcp), ('can', c.mcp), ('hw_linux', h.mcp), ('gazebo', g.mcp)]:
        print(name, len(await srv.list_tools()), 'tools OK')
asyncio.run(main())
"
```

### 4.4. Thiết lập nhanh giao diện SocketCAN (Thực tế & Mô phỏng `vcan0`)
- **Với phần cứng USB-CAN / SocketCAN thực tế (`can0`, 500 kbps):**
  ```bash
  sudo ip link set can0 down 2>/dev/null || true
  sudo ip link set can0 type can bitrate 500000 restart-ms 100
  sudo ip link set can0 up
  ```
- **Với bus CAN ảo (`vcan0`) để test khi chưa cắm phần cứng:**
  ```bash
  sudo modprobe vcan
  sudo ip link add dev vcan0 type vcan
  sudo ip link set up vcan0
  ```
