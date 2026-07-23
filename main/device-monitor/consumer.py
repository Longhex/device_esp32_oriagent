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
COMMAND_TIMEOUT_SECONDS = int(os.getenv("MONITOR_COMMAND_TIMEOUT", "30"))
TAG = "[consumer]"


def _now():
    return int(time.time())


# Lưu trữ trạng thái: in-memory + write-through Redis (nếu có)
_log = lambda m: print(m, flush=True)
store = DeviceStore(logger=_log)
serials = SerialStore(now_fn=_now, logger=_log)
_client_ref = {"mqtt": None}
_pending_commands = {}
_pending_lock = threading.Lock()


def _legacy_command_payload(action, params=None):
    """Translate the canonical management command into current HK firmware JSON."""
    params = params or {}
    aliases = {
        "ota": "fota",
        "mic_gain": "set_mic",
    }
    command = aliases.get(action, action)
    supported = {
        "music_search", "music_control", "volume", "set_mic", "chat",
        "set_server", "reboot", "set_city", "set_profile", "set_wake",
        "set_wakegain", "wakeup", "fota", "get_state",
    }
    if command not in supported:
        raise ValueError(f"unsupported_by_current_firmware:{action}")

    payload = {"cmd": command}
    if command == "fota":
        payload["url"] = params.get("url", "")
        if not payload["url"]:
            raise ValueError("missing_required_param:url")
    elif command in {"volume", "set_mic", "set_server", "set_city", "set_wake", "set_wakegain"}:
        if "value" not in params:
            raise ValueError("missing_required_param:value")
        payload["value"] = params["value"]
    elif command == "set_profile":
        payload["profile"] = params.get("profile", "")
        if not payload["profile"]:
            raise ValueError("missing_required_param:profile")
    elif command == "chat":
        payload["msg"] = params.get("msg", "")
        if not payload["msg"]:
            raise ValueError("missing_required_param:msg")
    elif command == "music_control":
        payload["action"] = params.get("action", "")
        if not payload["action"]:
            raise ValueError("missing_required_param:action")
    elif command == "music_search":
        payload.update({
            "song": params.get("song", ""),
            "artist": params.get("artist", ""),
            "source": params.get("source", ""),
        })
    return payload


def _expire_pending_commands(now=None):
    now = now or _now()
    expired = []
    with _pending_lock:
        for key, pending in list(_pending_commands.items()):
            if now - pending["sent_at"] >= COMMAND_TIMEOUT_SECONDS:
                expired.append((key, _pending_commands.pop(key)))
    for (serial, command), pending in expired:
        store.update(serial, {
            "last_ack": {
                "id": pending["id"],
                "cmd": command,
                "status": "timeout",
            },
            "last_ack_ts": now,
        })


def activate_serial(serial, mac=None, rotate=False):
    """Kích hoạt serial đã khai báo: sinh password, cấp credential EMQX, trả MQTT config.
    Trả (config_dict, error_str)."""
    rec, err = serials.activate(serial, mac=mac, rotate=rotate)
    if err:
        return None, err
    topic_identity = common.hk_topic_identity(serial, mac)
    try:
        emqx = EmqxAdmin(logger=_log).login()
        shared_test = common.shared_test_credentials(serial)
        if shared_test:
            username, password = shared_test
            emqx.upsert_user(username, password)
            emqx.set_hk_client_acl(serial, topic_identity=topic_identity)
        else:
            emqx.provision_device(
                serial, rec["password"], topic_identity=topic_identity
            )
    except (EmqxError, RuntimeError) as e:
        return None, f"EMQX provision lỗi: {e}"
    username, password = shared_test or (serial, rec["password"])
    return {
        "serial": serial,
        "status": rec["status"],
        "mqtt": {
            "endpoint": common.MQTT_PUBLIC_ENDPOINT,
            "client_id": serial,
            "username": username,
            "password": password,
            "publish_topic": common.hk_device_publish_topic(topic_identity),
            "subscribe_topic": common.hk_device_subscribe_topic(topic_identity),
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
    subscriptions = [(common.SUB_ALL_STATUS, 1),
                     (common.SUB_ALL_TELEMETRY, 1),
                     (common.SUB_ALL_ACK, 1)]
    if common.ENABLE_HK_LEGACY_BRIDGE:
        subscriptions.append((common.LEGACY_MONITOR_TOPIC, 1))
        subscriptions.append((common.SUB_ALL_HK_UPLINK, 1))
    client.subscribe(subscriptions)


def _client_from_topic(topic):
    # devices/<client>/<...>
    parts = topic.split("/")
    return parts[1] if len(parts) >= 2 else None


def _handle_hk_monitor_payload(payload, client_id, protocol):
    if not client_id:
        print(f"{TAG} drop HK payload without serial mapping", flush=True)
        return

    now = _now()
    if payload.get("type") == "response" and payload.get("cmd"):
        command = str(payload["cmd"])
        with _pending_lock:
            pending = _pending_commands.pop((client_id, command), None)
        ack = dict(payload)
        if pending:
            ack["id"] = pending["id"]
        store.update(client_id, {
            "online": True,
            "protocol": protocol,
            "last_seen": now,
            "last_ack": ack,
            "last_ack_ts": now,
        })
        print(f"{TAG} HK ack {client_id} cmd={command}", flush=True)
    else:
        store.update(client_id, {
            "online": True,
            "protocol": protocol,
            "last_seen": now,
            "telemetry": payload,
            "last_telemetry_ts": now,
        })
        print(f"{TAG} HK state {client_id}", flush=True)


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        payload = {"raw": msg.payload.decode(errors="replace")}

    if msg.topic == common.LEGACY_MONITOR_TOPIC and common.ENABLE_HK_LEGACY_BRIDGE:
        state_payload = payload.get("state")
        if not isinstance(state_payload, dict):
            state_payload = {}
        client_id = str(
            payload.get("serial_number")
            or state_payload.get("serial_number")
            or ""
        ).strip()
        if not client_id:
            rec = serials.find_by_mac(payload.get("mac"))
            client_id = rec.get("serial", "") if rec else ""
        _handle_hk_monitor_payload(payload, client_id, "hakat_legacy")
        return

    if (
        common.ENABLE_HK_LEGACY_BRIDGE
        and msg.topic.endswith(f"/{common.HK_MQTT_UPLINK_SUFFIX}")
    ):
        parts = msg.topic.split("/")
        client_id = parts[0] if len(parts) == 2 else ""
        _handle_hk_monitor_payload(payload, client_id, "hakat_topics_v2")
        return

    client_id = _client_from_topic(msg.topic)
    if not client_id:
        return

    if msg.topic.endswith("/status"):
        online = bool(payload.get("online"))
        store.update(client_id, {"online": online, "protocol": "canonical", "last_status_ts": _now(), "status_payload": payload})
        print(f"{TAG} presence {client_id} -> {'ONLINE' if online else 'OFFLINE'}", flush=True)
    elif msg.topic.endswith("/telemetry"):
        store.update(client_id, {"protocol": "canonical", "telemetry": payload, "last_telemetry_ts": _now()})
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
    _expire_pending_commands()
    cmd_id = f"cmd-{_now()}-{int(time.time()*1000) % 1000}"
    entry = store.get(client_id) or {}
    use_hk_bridge = (
        common.ENABLE_HK_LEGACY_BRIDGE
        and entry.get("protocol") in {"hakat_legacy", "hakat_topics_v2"}
    )
    if use_hk_bridge:
        payload = _legacy_command_payload(action, params)
        if entry.get("protocol") == "hakat_topics_v2":
            topic = common.hk_device_subscribe_topic(client_id)
        else:
            topic = common.legacy_command_topic(client_id)
        with _pending_lock:
            pending_key = (client_id, payload["cmd"])
            if pending_key in _pending_commands:
                raise ValueError(f"command_already_pending:{payload['cmd']}")
            _pending_commands[pending_key] = {
                "id": cmd_id,
                "sent_at": _now(),
            }
    else:
        payload = {"id": cmd_id, "action": action, "params": params or {}}
        topic = common.topic_command(client_id)

    mqtt_client = _client_ref["mqtt"]
    if mqtt_client is None:
        raise RuntimeError("mqtt_not_connected")
    result = mqtt_client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)
    if getattr(result, "rc", 0) != mqtt.MQTT_ERR_SUCCESS:
        if use_hk_bridge:
            with _pending_lock:
                _pending_commands.pop((client_id, payload["cmd"]), None)
        raise RuntimeError(f"mqtt_publish_failed:{getattr(result, 'rc', 'unknown')}")
    print(f"{TAG} -> command {client_id} topic={topic} cmd={action}", flush=True)
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
            config, err = activate_serial(
                serial, mac=body.get("mac"), rotate=bool(body.get("rotate", False))
            )
            if err:
                # serial chưa khai báo -> 403; lỗi EMQX -> 502
                code = 403 if "khai báo" in err else 502
                return self._send(code, {"error": err})
            return self._send(200, config)

        # POST /devices/<client>/command  {action, params}
        if len(parts) == 3 and parts[0] == "devices" and parts[2] == "command":
            action = body.get("action", "noop")
            try:
                cmd_id = send_command(parts[1], action, body.get("params"))
            except ValueError as exc:
                message = str(exc)
                code = 409 if message.startswith("command_already_pending") else 422
                return self._send(code, {"error": message, "action": action})
            except RuntimeError as exc:
                return self._send(503, {"error": str(exc), "action": action})
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


def pending_timeout_loop():
    while True:
        time.sleep(1)
        _expire_pending_commands()


def main():
    common.validate_runtime_secrets()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="oriagent-monitor-consumer")
    client.username_pw_set(common.BACKEND_USERNAME, common.BACKEND_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    _client_ref["mqtt"] = client

    client.connect(common.EMQX_HOST, common.EMQX_MQTT_PORT, keepalive=30)
    threading.Thread(target=start_http, daemon=True).start()
    threading.Thread(target=pending_timeout_loop, daemon=True).start()
    client.loop_forever()


if __name__ == "__main__":
    main()
