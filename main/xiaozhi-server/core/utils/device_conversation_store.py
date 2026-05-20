import json
import os
import threading

_STORE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "device_conversations.json"
)
_STORE_PATH = os.path.normpath(_STORE_PATH)
_lock = threading.Lock()


def _read() -> dict:
    try:
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(data: dict) -> None:
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    tmp = _STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _STORE_PATH)


def load_conversation_id(device_id: str) -> str:
    if not device_id:
        return ""
    with _lock:
        return _read().get(device_id, "")


def save_conversation_id(device_id: str, conversation_id: str) -> None:
    if not device_id or not conversation_id:
        return
    with _lock:
        data = _read()
        if data.get(device_id) != conversation_id:
            data[device_id] = conversation_id
            _write(data)
