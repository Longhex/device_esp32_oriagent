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
EMQX_DASHBOARD_PASSWORD = os.getenv("EMQX_DASHBOARD_PASSWORD", "")

# --- Tài khoản backend (consumer) ---
BACKEND_USERNAME = os.getenv("MQTT_BACKEND_USER", "oriagent-monitor")
BACKEND_PASSWORD = os.getenv("MQTT_BACKEND_PASS", "")


def validate_runtime_secrets(require_dashboard=False):
    missing = []
    if not BACKEND_PASSWORD:
        missing.append("MQTT_BACKEND_PASS")
    if require_dashboard and not EMQX_DASHBOARD_PASSWORD:
        missing.append("EMQX_DASHBOARD_PASSWORD")
    if missing:
        raise RuntimeError("Missing required secret environment variables: " + ", ".join(missing))

# --- Lưu trữ trạng thái ---
# REDIS_HOST rỗng = TẮT Redis (opt-in): tránh đấu nhầm redis lạ khi chạy tay.
# Container trong stack sẽ set REDIS_HOST=xiaozhi-esp32-server-redis.
REDIS_HOST = os.getenv("REDIS_HOST", "").strip()
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "") or None

# Compatibility bridge for the current HK firmware. Keep this feature-flagged
# so the canonical devices/{serial}/... contract remains the long-term API.
ENABLE_HK_LEGACY_BRIDGE = os.getenv(
    "ENABLE_HK_LEGACY_BRIDGE", "false"
).strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str) -> frozenset[str]:
    return frozenset(
        value.strip()
        for value in os.getenv(name, "").split(",")
        if value.strip()
    )


# Temporary firmware compatibility credentials. Keep the serial list empty in
# normal production. Authorization remains restricted per MQTT client ID.
MQTT_SHARED_TEST_SERIALS = _csv_env("MQTT_SHARED_TEST_SERIALS")
MQTT_SHARED_TEST_USERNAME = os.getenv("MQTT_SHARED_TEST_USERNAME", "").strip()
MQTT_SHARED_TEST_PASSWORD = os.getenv("MQTT_SHARED_TEST_PASSWORD", "")


def shared_test_credentials(serial: str):
    if str(serial or "").strip() not in MQTT_SHARED_TEST_SERIALS:
        return None
    if not MQTT_SHARED_TEST_USERNAME or not MQTT_SHARED_TEST_PASSWORD:
        raise RuntimeError(
            "MQTT shared test serial is configured but username/password is empty"
        )
    return MQTT_SHARED_TEST_USERNAME, MQTT_SHARED_TEST_PASSWORD

# Topic contract returned to HK firmware by OTA.  Keep the suffixes configurable
# so every backend service can use the same rollout contract without embedding a
# particular device serial in source code.
def _topic_suffix(env_name, default):
    suffix = os.getenv(env_name, default).strip().strip("/")
    if not suffix or any(char in suffix for char in "/+#"):
        raise ValueError(f"Invalid MQTT topic suffix configured in {env_name}")
    return suffix


HK_MQTT_UPLINK_SUFFIX = _topic_suffix(
    "HK_MQTT_UPLINK_SUFFIX", "AI_MONITOR"
)
HK_MQTT_DOWNLINK_SUFFIX = _topic_suffix(
    "HK_MQTT_DOWNLINK_SUFFIX", "AI_REMOTE"
)


# --- Quy ước topic ---
# {client} = ĐỊNH DANH THIẾT BỊ = Serial-Number (vd "HKHT2606010011"), khai báo
# trên server trước khi kích hoạt. Dùng verbatim làm topic + MQTT username để thống
# nhất 1 khóa xuyên suốt DB <-> MQTT <-> web. Xem memory serial-number-activation.
TOPIC_PREFIX = "devices"
LEGACY_MONITOR_TOPIC = "HAKAT_AI_MONITOR_ALL"


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


def legacy_command_topic(client: str) -> str:
    return f"{normalize_client(client)}/MONITOR"


def hk_device_publish_topic(client: str) -> str:
    """Topic firmware publishes signaling/state/ACK messages to."""
    return f"{normalize_client(client)}/{HK_MQTT_UPLINK_SUFFIX}"


def hk_device_subscribe_topic(client: str) -> str:
    """Topic firmware subscribes for signaling responses and commands."""
    return f"{normalize_client(client)}/{HK_MQTT_DOWNLINK_SUFFIX}"


# Topic wildcard cho backend subscribe toàn bộ thiết bị
SUB_ALL_STATUS = f"{TOPIC_PREFIX}/+/status"
SUB_ALL_TELEMETRY = f"{TOPIC_PREFIX}/+/telemetry"
SUB_ALL_ACK = f"{TOPIC_PREFIX}/+/command/ack"
SUB_ALL_HK_UPLINK = f"+/{HK_MQTT_UPLINK_SUFFIX}"
