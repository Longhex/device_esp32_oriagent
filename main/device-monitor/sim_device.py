"""Thiết bị giả lập (thay cho ESP32) — test mặt phẳng quản lý MQTT.

Mô phỏng đúng hành vi firmware sẽ làm:
- Đặt LWT = offline (retained) để broker tự báo offline khi mất kết nối.
- Khi connect: publish online (retained).
- Định kỳ publish telemetry (pin, RSSI, heap, uptime, fw_ver).
- Subscribe lệnh, thực thi, publish ack.
- Khi thoát êm (SIGINT): publish offline (retained) rồi disconnect.

Chạy:  python sim_device.py <serial_number> <password> [telemetry_interval_s]
VD:    python sim_device.py HKHT2606010011 dev01_secret_2024 5
"""
import sys
import json
import time
import signal

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import paho.mqtt.client as mqtt

import common

CLIENT = sys.argv[1] if len(sys.argv) > 1 else "HKHT2606010011"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "dev01_secret_2024"
INTERVAL = int(sys.argv[3]) if len(sys.argv) > 3 else 5

TAG = f"[sim {CLIENT}]"
_start = time.time()
_running = {"on": True}


def status_payload(online):
    return json.dumps({"online": online, "ts": int(time.time()), "fw_ver": "1.0.1"})


def telemetry_payload():
    uptime = int(time.time() - _start)
    return json.dumps({
        "ts": int(time.time()),
        "uptime_s": uptime,
        "battery_pct": max(5, 100 - uptime % 100),
        "rssi_dbm": -45 - (uptime % 30),
        "free_heap_kb": 120 - (uptime % 20),
        "fw_ver": "1.0.1",
    })


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        print(f"{TAG} connect FAILED rc={reason_code}", flush=True)
        return
    print(f"{TAG} connected", flush=True)
    # Báo online (retained) + subscribe lệnh
    client.publish(common.topic_status(CLIENT), status_payload(True), qos=1, retain=True)
    client.subscribe(common.topic_command(CLIENT), qos=1)


def on_message(client, userdata, msg):
    try:
        cmd = json.loads(msg.payload.decode())
    except Exception:
        return
    print(f"{TAG} <- command {cmd}", flush=True)
    action = cmd.get("action")
    # Mô phỏng thực thi
    result = {"ok": True}
    if action == "reboot":
        result = {"ok": True, "msg": "rebooting (simulated)"}
    elif action == "set_config":
        result = {"ok": True, "applied": cmd.get("params", {})}
    elif action == "ota":
        result = {"ok": True, "msg": "ota triggered (simulated)", "url": cmd.get("params", {}).get("url")}
    else:
        result = {"ok": False, "msg": f"unknown action {action}"}
    ack = {"id": cmd.get("id"), "action": action, "status": "done", "result": result, "ts": int(time.time())}
    client.publish(common.topic_command_ack(CLIENT), json.dumps(ack), qos=1)
    print(f"{TAG} -> ack {ack}", flush=True)


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT)
    client.username_pw_set(CLIENT, PASSWORD)
    # LWT: nếu mất kết nối đột ngột, broker phát offline (retained)
    client.will_set(common.topic_status(CLIENT), status_payload(False), qos=1, retain=True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(common.EMQX_HOST, common.EMQX_MQTT_PORT, keepalive=15)
    client.loop_start()

    def shutdown(*_):
        _running["on"] = False
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    next_tele = 0
    while _running["on"]:
        if time.time() >= next_tele:
            client.publish(common.topic_telemetry(CLIENT), telemetry_payload(), qos=1)
            next_tele = time.time() + INTERVAL
        time.sleep(0.2)

    # Thoát êm: báo offline rồi ngắt
    client.publish(common.topic_status(CLIENT), status_payload(False), qos=1, retain=True)
    time.sleep(0.3)
    client.loop_stop()
    client.disconnect()
    print(f"{TAG} stopped (offline published)", flush=True)


if __name__ == "__main__":
    main()
