"""Cấu hình & helper dùng chung cho device-monitor (mặt phẳng quản lý MQTT/EMQX).

Tách biệt hoàn toàn với luồng audio xiaozhi. Mọi tham số đọc từ biến môi trường
để khớp phong cách deploy của dự án (.env).
"""
import os

# --- Kết nối broker ---
EMQX_HOST = os.getenv("EMQX_HOST", "127.0.0.1")
EMQX_MQTT_PORT = int(os.getenv("EMQX_MQTT_PORT", "1883"))

# Endpoint MQTT PUBLIC mà thiết bị dùng để kết nối (trả về khi activate).
# Trong container EMQX_HOST=emqx (nội bộ) nên phải set riêng cho thiết bị ngoài.
MQTT_PUBLIC_ENDPOINT = os.getenv("MQTT_PUBLIC_ENDPOINT", f"{EMQX_HOST}:{EMQX_MQTT_PORT}")

# REST API quản trị (dùng để provision authn/authz)
EMQX_API_BASE = os.getenv("EMQX_API_BASE", "http://127.0.0.1:18083/api/v5")
EMQX_DASHBOARD_USER = os.getenv("EMQX_DASHBOARD_USER", "admin")
EMQX_DASHBOARD_PASSWORD = os.getenv("EMQX_DASHBOARD_PASSWORD", "oriagent_emqx_admin_2024")

# --- Tài khoản backend (consumer) ---
BACKEND_USERNAME = os.getenv("MQTT_BACKEND_USER", "oriagent-monitor")
BACKEND_PASSWORD = os.getenv("MQTT_BACKEND_PASS", "oriagent_monitor_pass_2024")

# --- Lưu trữ trạng thái ---
# REDIS_HOST rỗng = TẮT Redis (opt-in): tránh đấu nhầm redis lạ khi chạy tay.
# Container trong stack sẽ set REDIS_HOST=xiaozhi-esp32-server-redis.
REDIS_HOST = os.getenv("REDIS_HOST", "").strip()
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "") or None


# --- Quy ước topic ---
# {client} = ĐỊNH DANH THIẾT BỊ = Serial-Number (vd "HKHT2606010011"), khai báo
# trên server trước khi kích hoạt. Dùng verbatim làm topic + MQTT username để thống
# nhất 1 khóa xuyên suốt DB <-> MQTT <-> web. Xem memory serial-number-activation.
TOPIC_PREFIX = "devices"


def normalize_client(value: str) -> str:
    """Làm sạch định danh để an toàn cho topic MQTT (không có '/', '+', '#', space).
    Serial-Number hợp lệ sẽ giữ nguyên; MAC (nếu còn dùng) đổi ':' -> '_'.
    Giữ nguyên hoa/thường vì topic & username MQTT phân biệt hoa thường.
    """
    return value.replace(":", "_").replace("/", "_").replace(" ", "_")


def topic_status(client: str) -> str:
    return f"{TOPIC_PREFIX}/{client}/status"


def topic_telemetry(client: str) -> str:
    return f"{TOPIC_PREFIX}/{client}/telemetry"


def topic_command(client: str) -> str:
    return f"{TOPIC_PREFIX}/{client}/command"


def topic_command_ack(client: str) -> str:
    return f"{TOPIC_PREFIX}/{client}/command/ack"


# Topic wildcard cho backend subscribe toàn bộ thiết bị
SUB_ALL_STATUS = f"{TOPIC_PREFIX}/+/status"
SUB_ALL_TELEMETRY = f"{TOPIC_PREFIX}/+/telemetry"
SUB_ALL_ACK = f"{TOPIC_PREFIX}/+/command/ack"
