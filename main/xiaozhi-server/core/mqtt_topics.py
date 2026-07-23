import os
import re


HK_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
HK_MAC_ADDRESS_RE = re.compile(r"^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$")


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


def normalize_hk_topic_identity(device_id: str) -> str:
    """Return the HK topic segment for a serial or a MAC fallback identity.

    MQTT credentials retain the original serial, while HK topics use a safe
    single-level segment.  This must match device-monitor's
    ``normalize_client`` contract so that the topic advertised by OTA is also
    the topic authorized by EMQX.
    """
    # MQTT permits ':' in a topic level.  Preserve the provisioned identity so
    # the OTA response, EMQX ACL and firmware publish topic cannot diverge.
    return validate_hk_device_id(device_id)


def hk_legacy_monitor_topic(device_id: str) -> str:
    """Downlink topic implemented by the currently deployed HAKAT firmware.

    Firmware derives this topic from its MAC formatter: lowercase, colons
    preserved, and the ``MONITOR`` suffix.  This is deliberately separate from
    canonical topic normalization because MQTT topics are case-sensitive.
    """
    identity = validate_hk_device_id(device_id)
    if HK_MAC_ADDRESS_RE.fullmatch(identity):
        identity = identity.lower()
    return f"{identity}/MONITOR"


def hk_device_publish_topic(device_id: str) -> str:
    return f"{normalize_hk_topic_identity(device_id)}/{HK_MQTT_UPLINK_SUFFIX}"


def hk_device_subscribe_topic(device_id: str) -> str:
    # Do not advertise AI_REMOTE until firmware consumes OTA subscribe_topic.
    return hk_legacy_monitor_topic(device_id)


def hk_uplink_subscription() -> str:
    return f"+/{HK_MQTT_UPLINK_SUFFIX}"


def parse_hk_uplink_topic(topic: str):
    """Return (device_id, downlink_topic) for new and legacy HK uplinks."""
    parts = str(topic or "").split("/")
    if len(parts) == 1:
        device_id = validate_hk_device_id(parts[0])
        return device_id, hk_legacy_monitor_topic(device_id)
    if len(parts) == 2 and parts[1] == HK_MQTT_UPLINK_SUFFIX:
        device_id = validate_hk_device_id(parts[0])
        return device_id, hk_legacy_monitor_topic(device_id)
    raise ValueError("Topic does not match the HK MQTT uplink contract")
