"""device-monitor consumer — mặt phẳng quản lý/giám sát thiết bị qua EMQX.

Nhiệm vụ:
- Subscribe presence (devices/+/status), telemetry (devices/+/telemetry), ack lệnh.
- Giữ trạng thái mới nhất của từng thiết bị (DeviceStore: in-memory + write-through Redis).
- Expose HTTP API mini (stdlib) cho web/app đọc trạng thái & gửi lệnh.

Trạng thái mirror sang Redis (nếu có) để manager-api/web đọc chung & bền qua restart;
không có Redis thì tự fallback in-memory. Khi tích hợp thật: đưa HTTP API này vào
manager-api. Không đụng tới luồng audio xiaozhi.

Chạy:  python consumer.py
Env:   EMQX_HOST, EMQX_MQTT_PORT, MQTT_BACKEND_USER/PASS, MONITOR_HTTP_PORT
"""
import os
import sys
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import paho.mqtt.client as mqtt

import common
from store import DeviceStore
from serial_store import SerialStore
from emqx_admin import EmqxAdmin, EmqxError

HTTP_PORT = int(os.getenv("MONITOR_HTTP_PORT", "8090"))
TAG = "[consumer]"


def _now():
    return int(time.time())


# Lưu trữ trạng thái: in-memory + write-through Redis (nếu có)
_log = lambda m: print(m, flush=True)
store = DeviceStore(logger=_log)
serials = SerialStore(now_fn=_now, logger=_log)
_client_ref = {"mqtt": None}


def activate_serial(serial, mac=None):
    """Kích hoạt serial đã khai báo: sinh password, cấp credential EMQX, trả MQTT config.
    Trả (config_dict, error_str)."""
    rec, err = serials.activate(serial, mac=mac)
    if err:
        return None, err
    try:
        emqx = EmqxAdmin(logger=_log).login()
        emqx.provision_device(serial, rec["password"])
    except EmqxError as e:
        return None, f"EMQX provision lỗi: {e}"
    return {
        "serial": serial,
        "status": rec["status"],
        "mqtt": {
            "endpoint": common.MQTT_PUBLIC_ENDPOINT,
            "client_id": serial,
            "username": serial,
            "password": rec["password"],
            "topics": {
                "status": common.topic_status(serial),
                "telemetry": common.topic_telemetry(serial),
                "command": common.topic_command(serial),
                "command_ack": common.topic_command_ack(serial),
            },
        },
    }, None


# ---------------- MQTT ----------------
def on_connect(client, userdata, flags, reason_code, properties):
    print(f"{TAG} connected rc={reason_code}", flush=True)
    client.subscribe([(common.SUB_ALL_STATUS, 1),
                      (common.SUB_ALL_TELEMETRY, 1),
                      (common.SUB_ALL_ACK, 1)])


def _client_from_topic(topic):
    # devices/<client>/<...>
    parts = topic.split("/")
    return parts[1] if len(parts) >= 2 else None


def on_message(client, userdata, msg):
    client_id = _client_from_topic(msg.topic)
    if not client_id:
        return
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        payload = {"raw": msg.payload.decode(errors="replace")}

    if msg.topic.endswith("/status"):
        online = bool(payload.get("online"))
        store.update(client_id, {"online": online, "last_status_ts": _now(), "status_payload": payload})
        print(f"{TAG} presence {client_id} -> {'ONLINE' if online else 'OFFLINE'}", flush=True)
    elif msg.topic.endswith("/telemetry"):
        store.update(client_id, {"telemetry": payload, "last_telemetry_ts": _now()})
        print(f"{TAG} telemetry {client_id} -> {payload}", flush=True)
    elif msg.topic.endswith("/command/ack"):
        store.update(client_id, {"last_ack": payload, "last_ack_ts": _now()})
        print(f"{TAG} ack {client_id} -> {payload}", flush=True)


def deactivate_serial(serial):
    """Gỡ thiết bị: xóa credential EMQX + clear retained status + xóa Redis.
    Triển khai đúng lưu ý vận hành (retained 'sống lại' nếu không clear)."""
    try:
        EmqxAdmin(logger=_log).login().delete_user(serial)
    except EmqxError as e:
        _log(f"[deactivate] EMQX lỗi (bỏ qua): {e}")
    # clear retained: publish payload rỗng retain=true vào topic status
    mqttc = _client_ref["mqtt"]
    if mqttc is not None:
        mqttc.publish(common.topic_status(serial), payload=None, qos=1, retain=True)
    serials.remove(serial)
    store.remove(serial)


def send_command(client_id, action, params=None):
    cmd_id = f"cmd-{_now()}-{int(time.time()*1000) % 1000}"
    payload = {"id": cmd_id, "action": action, "params": params or {}}
    _client_ref["mqtt"].publish(common.topic_command(client_id), json.dumps(payload), qos=1)
    print(f"{TAG} -> command {client_id}: {payload}", flush=True)
    return cmd_id


# ---------------- HTTP API ----------------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass  # tắt log mặc định

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw)

    @staticmethod
    def _redact(rec):
        if not rec:
            return rec
        r = dict(rec)
        r.pop("password", None)  # password chỉ trả 1 lần lúc activate
        return r

    def do_GET(self):
        if self.path == "/healthz":
            return self._send(200, {"status": "ok", "redis": store.redis_enabled})
        if self.path == "/devices":
            devices = store.all()
            return self._send(200, {"devices": devices, "count": len(devices)})
        if self.path.startswith("/devices/"):
            cid = self.path.split("/")[2]
            entry = store.get(cid)
            if entry is not None:
                return self._send(200, {"client": cid, **entry})
            return self._send(404, {"error": "not found"})
        if self.path == "/serials":
            items = [self._redact(s) for s in serials.all() if s]
            return self._send(200, {"serials": items, "count": len(items)})
        if self.path.startswith("/serials/"):
            sn = self.path.split("/")[2]
            rec = serials.get(sn)
            return self._send(200, self._redact(rec)) if rec else self._send(404, {"error": "not found"})
        return self._send(404, {"error": "unknown path"})

    def do_POST(self):
        parts = self.path.strip("/").split("/")
        try:
            body = self._body()
        except Exception:
            return self._send(400, {"error": "invalid json"})

        # POST /serials  {serial, batch?}  -> khai báo serial
        if self.path == "/serials":
            serial = (body.get("serial") or "").strip()
            if not serial:
                return self._send(400, {"error": "serial required"})
            rec, created = serials.declare(serial, batch=body.get("batch"))
            return self._send(201 if created else 200, self._redact(rec))

        # POST /activate  {serial, mac?}  -> kích hoạt + cấp MQTT credential
        if self.path == "/activate":
            serial = (body.get("serial") or "").strip()
            if not serial:
                return self._send(400, {"error": "serial required"})
            config, err = activate_serial(serial, mac=body.get("mac"))
            if err:
                # serial chưa khai báo -> 403; lỗi EMQX -> 502
                code = 403 if "khai báo" in err else 502
                return self._send(code, {"error": err})
            return self._send(200, config)

        # POST /devices/<client>/command  {action, params}
        if len(parts) == 3 and parts[0] == "devices" and parts[2] == "command":
            cmd_id = send_command(parts[1], body.get("action", "noop"), body.get("params"))
            return self._send(202, {"command_id": cmd_id})

        return self._send(404, {"error": "unknown path"})

    def do_DELETE(self):
        # DELETE /serials/<sn>  -> gỡ thiết bị (unbind): EMQX + retained + Redis
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "serials":
            deactivate_serial(parts[1])
            return self._send(200, {"deactivated": parts[1]})
        return self._send(404, {"error": "unknown path"})


def start_http():
    srv = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    print(f"{TAG} HTTP API on :{HTTP_PORT} "
          f"(GET /devices, /serials | POST /serials, /activate, /devices/<id>/command)", flush=True)
    srv.serve_forever()


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="oriagent-monitor-consumer")
    client.username_pw_set(common.BACKEND_USERNAME, common.BACKEND_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    _client_ref["mqtt"] = client

    client.connect(common.EMQX_HOST, common.EMQX_MQTT_PORT, keepalive=30)
    threading.Thread(target=start_http, daemon=True).start()
    client.loop_forever()


if __name__ == "__main__":
    main()
