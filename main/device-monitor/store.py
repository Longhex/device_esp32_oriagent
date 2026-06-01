"""Lưu trữ trạng thái thiết bị cho device-monitor.

Write-through: luôn giữ bản in-memory (nguồn đọc nhanh cho HTTP API) và,
nếu Redis khả dụng, mirror sang Redis để manager-api/web đọc state chung +
bền vững qua restart. Không có Redis -> tự fallback in-memory, không lỗi.

Key Redis:
  device-monitor:device:{client}  -> JSON trạng thái thiết bị (string)
  device-monitor:devices          -> SET các client_id đã biết
"""
import json
import threading

KEY_PREFIX = "device-monitor:device:"
KEY_INDEX = "device-monitor:devices"


class DeviceStore:
    def __init__(self, logger=print):
        self._mem = {}
        self._lock = threading.Lock()
        self._redis = None
        self._log = logger
        self._init_redis()

    def _init_redis(self):
        from redis_client import get_redis
        self._redis = get_redis(self._log)

    @property
    def redis_enabled(self):
        return self._redis is not None

    def update(self, client_id, patch: dict):
        """Gộp patch vào trạng thái thiết bị, mirror sang Redis nếu có."""
        with self._lock:
            entry = self._mem.setdefault(client_id, {})
            entry.update(patch)
            snapshot = dict(entry)
        if self._redis is not None:
            try:
                self._redis.set(KEY_PREFIX + client_id, json.dumps(snapshot, ensure_ascii=False))
                self._redis.sadd(KEY_INDEX, client_id)
            except Exception as e:
                self._log(f"[store] ghi Redis lỗi: {e}")
        return snapshot

    def get(self, client_id):
        with self._lock:
            return dict(self._mem.get(client_id, {})) if client_id in self._mem else None

    def all(self):
        with self._lock:
            return {k: dict(v) for k, v in self._mem.items()}

    def remove(self, client_id):
        with self._lock:
            self._mem.pop(client_id, None)
        if self._redis is not None:
            try:
                self._redis.delete(KEY_PREFIX + client_id)
                self._redis.srem(KEY_INDEX, client_id)
            except Exception as e:
                self._log(f"[store] xóa Redis lỗi: {e}")
