"""Kho Serial-Number cho luồng kích hoạt thiết bị.

Mô hình: serial được KHAI BÁO trên server trước (status=declared); thiết bị boot
lần đầu gọi /activate -> đối chiếu serial đã khai báo -> cấp MQTT credential
(status=activated). Chỉ serial đã khai báo mới activate được.

Lưu trong Redis (fallback in-memory nếu không có Redis):
  device-monitor:serial:{sn}  -> JSON {serial,status,password,mac,declared_at,activated_at,batch}
  device-monitor:serials      -> SET các serial đã khai báo

Lưu ý bảo mật: lưu password (plaintext) để có thể trả lại khi re-activate/debug.
Production nên cân nhắc chỉ lưu hash hoặc không lưu (EMQX đã giữ bản hash).
"""
import json
import secrets
import threading

KEY_PREFIX = "device-monitor:serial:"
KEY_INDEX = "device-monitor:serials"

STATUS_DECLARED = "declared"
STATUS_ACTIVATED = "activated"


def gen_password(nbytes=18):
    # URL-safe, không ký tự gây rối cho MQTT/header
    return secrets.token_urlsafe(nbytes)


class SerialStore:
    def __init__(self, now_fn, logger=print):
        self._mem = {}
        self._lock = threading.Lock()
        self._now = now_fn
        self._log = logger
        from redis_client import get_redis
        self._redis = get_redis(logger)

    @property
    def redis_enabled(self):
        return self._redis is not None

    # ---------- internal ----------
    def _load(self, serial):
        if self._redis is not None:
            raw = self._redis.get(KEY_PREFIX + serial)
            return json.loads(raw) if raw else None
        return self._mem.get(serial)

    def _save(self, serial, rec):
        if self._redis is not None:
            self._redis.set(KEY_PREFIX + serial, json.dumps(rec, ensure_ascii=False))
            self._redis.sadd(KEY_INDEX, serial)
        else:
            self._mem[serial] = rec

    # ---------- public ----------
    def declare(self, serial, batch=None):
        """Khai báo serial. Idempotent: nếu đã có thì trả bản hiện tại."""
        with self._lock:
            existing = self._load(serial)
            if existing:
                return existing, False
            rec = {
                "serial": serial,
                "status": STATUS_DECLARED,
                "password": None,
                "mac": None,
                "batch": batch,
                "declared_at": self._now(),
                "activated_at": None,
            }
            self._save(serial, rec)
            return rec, True

    def activate(self, serial, mac=None, rotate=False):
        """Activate idempotently; rotate only when explicitly requested."""
        with self._lock:
            rec = self._load(serial)
            if not rec:
                return None, "serial chưa được khai báo trên server"
            if rotate or not rec.get("password"):
                rec["password"] = gen_password()
            rec["status"] = STATUS_ACTIVATED
            rec["mac"] = mac or rec.get("mac")
            rec["activated_at"] = rec.get("activated_at") or self._now()
            self._save(serial, rec)
            return rec, None

    def get(self, serial):
        with self._lock:
            return self._load(serial)

    def all(self):
        with self._lock:
            if self._redis is not None:
                serials = self._redis.smembers(KEY_INDEX)
                return [self._load(s) for s in serials]
            return list(self._mem.values())

    def find_by_mac(self, mac):
        """Return the serial record bound to a MAC address, if any."""
        if not mac:
            return None
        wanted = str(mac).strip().lower().replace("-", ":")
        for rec in self.all():
            if not rec or not rec.get("mac"):
                continue
            candidate = str(rec["mac"]).strip().lower().replace("-", ":")
            if candidate == wanted:
                return rec
        return None

    def remove(self, serial):
        with self._lock:
            if self._redis is not None:
                self._redis.delete(KEY_PREFIX + serial)
                self._redis.srem(KEY_INDEX, serial)
            else:
                self._mem.pop(serial, None)
