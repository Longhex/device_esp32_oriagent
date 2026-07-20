import os
import re


HK_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _topic_suffix(env_name: str, default: str) -> str:
    suffix = os.environ.get(env_name, default).strip().strip("/")
    if not suffix or any(char in suffix for char in "/+#"):
        raise ValueError(f"Invalid MQTT topic suffix configured in {env_name}")
    return suffix


HK_MQTT_UPLINK_SUFFIX = _topic_suffix(
    "HK_MQTT_UPLINK_SUFFIX", "AI_MONITOR"
)
HK_MQTT_DOWNLINK_SUFFIX = _topic_suffix(
    "HK_MQTT_DOWNLINK_SUFFIX", "AI_REMOTE"
)


def validate_hk_device_id(device_id: str) -> str:
    value = str(device_id or "").strip()
    if not HK_DEVICE_ID_RE.fullmatch(value):
        raise ValueError("Invalid MQTT client_id for HK topic contract")
    return value


def hk_device_publish_topic(device_id: str) -> str:
    return f"{validate_hk_device_id(device_id)}/{HK_MQTT_UPLINK_SUFFIX}"


def hk_device_subscribe_topic(device_id: str) -> str:
    return f"{validate_hk_device_id(device_id)}/{HK_MQTT_DOWNLINK_SUFFIX}"


def hk_uplink_subscription() -> str:
    return f"+/{HK_MQTT_UPLINK_SUFFIX}"


def parse_hk_uplink_topic(topic: str):
    """Return (device_id, downlink_topic) for new and legacy HK uplinks."""
    parts = str(topic or "").split("/")
    if len(parts) == 1:
        device_id = validate_hk_device_id(parts[0])
        return device_id, f"{device_id}/MONITOR"
    if len(parts) == 2 and parts[1] == HK_MQTT_UPLINK_SUFFIX:
        device_id = validate_hk_device_id(parts[0])
        return device_id, hk_device_subscribe_topic(device_id)
    raise ValueError("Topic does not match the HK MQTT uplink contract")
