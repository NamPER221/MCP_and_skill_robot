#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_CONFIG_DIR="${HOME}/.gemini/config"
TARGET_PLUGIN_DIR="${TARGET_CONFIG_DIR}/plugins/robotics"

echo "=== [1/4] Kiểm tra thư mục cài đặt ==="
mkdir -p "${TARGET_CONFIG_DIR}/plugins"
if [ "${PLUGIN_DIR}" != "${TARGET_PLUGIN_DIR}" ]; then
    echo "Sao chép plugin tới ${TARGET_PLUGIN_DIR}..."
    rm -rf "${TARGET_PLUGIN_DIR}"
    cp -r "${PLUGIN_DIR}" "${TARGET_PLUGIN_DIR}"
fi

echo "=== [2/4] Khởi tạo Python Virtualenv (--system-site-packages cho ROS2) ==="
python3 -m venv --system-site-packages "${TARGET_PLUGIN_DIR}/.venv"
"${TARGET_PLUGIN_DIR}/.venv/bin/pip" install --upgrade pip
"${TARGET_PLUGIN_DIR}/.venv/bin/pip" install -r "${TARGET_PLUGIN_DIR}/requirements.txt"
chmod +x "${TARGET_PLUGIN_DIR}/mcp_servers/"*.py

echo "=== [3/4] Tạo cấu hình mcp_config.json theo đường dẫn máy hiện tại ==="
cat > "${TARGET_PLUGIN_DIR}/mcp_config.json" <<EOF
{
  "mcpServers": {
    "ros2-control-diag": {
      "command": "${TARGET_PLUGIN_DIR}/.venv/bin/python3",
      "args": [
        "${TARGET_PLUGIN_DIR}/mcp_servers/ros2_control_diag_mcp.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    },
    "can-canopen-diag": {
      "command": "${TARGET_PLUGIN_DIR}/.venv/bin/python3",
      "args": [
        "${TARGET_PLUGIN_DIR}/mcp_servers/can_canopen_mcp.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    },
    "hw-linux-serial-diag": {
      "command": "${TARGET_PLUGIN_DIR}/.venv/bin/python3",
      "args": [
        "${TARGET_PLUGIN_DIR}/mcp_servers/hw_linux_serial_mcp.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    },
    "gazebo-sim-control": {
      "command": "${TARGET_PLUGIN_DIR}/.venv/bin/python3",
      "args": [
        "${TARGET_PLUGIN_DIR}/mcp_servers/gazebo_sim_mcp.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
EOF

echo "=== [4/4] Kích hoạt plugin 'robotics' trong ~/.gemini/config/config.json ==="
python3 - <<PYEOF
import json, os
cfg_path = os.path.expanduser("~/.gemini/config/config.json")
data = {}
if os.path.exists(cfg_path) and os.path.getsize(cfg_path) > 0:
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = json.load(f)
data.setdefault("plugins", {})["robotics"] = {"enabled": True}
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("Đã bật plugin 'robotics' trong", cfg_path)
PYEOF

echo "=== Hoàn tất cài đặt Robotics MCP & Skills Suite! ==="
