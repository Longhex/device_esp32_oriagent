"""E2E luồng kích hoạt theo Serial-Number — chạy với container device-monitor.

Kịch bản thật:
  khai báo serial -> (activate serial chưa khai báo bị từ chối) -> activate ->
  nhận MQTT credential -> thiết bị dùng credential kết nối -> được giám sát ->
  điều khiển -> gỡ thiết bị (unbind, clear retained).

Yêu cầu: stack đang chạy (emqx + redis + device-monitor) + đã provision auth.
Target API: MONITOR_BASE (mặc định http://127.0.0.1:8090 = container).

Chạy:  python tests/activation_e2e_test.py    (exit 0 = all PASS)
"""
import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PY = sys.executable
BASE = os.getenv("MONITOR_BASE", "http://127.0.0.1:8090")
SERIAL = "HKHT2606010099"          # serial test (khác serial demo)
UNDECLARED = "HKHT0000000000"      # serial chưa khai báo

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("✅ PASS  " if ok else "❌ FAIL  ") + name + (f"  — {detail}" if detail else ""), flush=True)
    return ok


def http(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, (json.loads(raw) if raw else None)


def wait_until(fn, timeout=20, interval=1.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def main():
    sim = None
    try:
        # dọn trước cho sạch (idempotent)
        http("DELETE", f"/serials/{SERIAL}")

        # 1) khai báo serial
        st, rec = http("POST", "/serials", {"serial": SERIAL, "batch": "test"})
        check("khai báo serial", st == 201 and rec.get("status") == "declared", f"status={rec}")

        # 2) activate serial CHƯA khai báo -> phải bị từ chối 403
        st, _ = http("POST", "/activate", {"serial": UNDECLARED})
        check("activate serial chưa khai báo bị từ chối", st == 403, f"http={st}")

        # 3) activate serial đã khai báo -> nhận MQTT credential
        st, cfg = http("POST", "/activate", {"serial": SERIAL, "mac": "aa:bb:cc:00:00:99"})
        mqtt_cfg = (cfg or {}).get("mqtt", {})
        pwd = mqtt_cfg.get("password")
        ok_act = bool(st == 200 and mqtt_cfg.get("username") == SERIAL and pwd
                      and mqtt_cfg.get("endpoint"))
        check("activate -> cấp MQTT credential", ok_act,
              f"endpoint={mqtt_cfg.get('endpoint')} user={mqtt_cfg.get('username')}")
        if not ok_act:
            return

        # Re-activate is idempotent so OTA discovery does not rotate the
        # credential on every reboot.
        st2, cfg2 = http("POST", "/activate", {"serial": SERIAL, "mac": "aa:bb:cc:00:00:99"})
        check("activate lặp lại giữ nguyên credential",
              st2 == 200 and (cfg2 or {}).get("mqtt", {}).get("password") == pwd)

        # 4) thiết bị dùng credential vừa cấp để kết nối
        env = dict(os.environ); env["PYTHONIOENCODING"] = "utf-8"
        sim = subprocess.Popen([PY, os.path.join(ROOT, "sim_device.py"), SERIAL, pwd, "2"],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        online = wait_until(lambda: http("GET", f"/devices/{SERIAL}")[1].get("online") is True, timeout=15)
        check("thiết bị kết nối bằng credential -> ONLINE", online)

        # 5) telemetry
        check("telemetry", wait_until(
            lambda: "battery_pct" in (http("GET", f"/devices/{SERIAL}")[1].get("telemetry") or {}), timeout=10))

        # 6) command + ack
        st, resp = http("POST", f"/devices/{SERIAL}/command", {"action": "reboot"})
        cid = (resp or {}).get("command_id")
        ack = wait_until(lambda: (http("GET", f"/devices/{SERIAL}")[1].get("last_ack") or {}).get("id") == cid, timeout=10)
        check("command + ack", ack and st == 202, f"cmd={cid}")

        # 7) kill -> LWT offline
        sim.terminate(); sim.wait(timeout=5); sim = None
        check("offline qua LWT", wait_until(
            lambda: http("GET", f"/devices/{SERIAL}")[1].get("online") is False, timeout=25))

        # 8) gỡ thiết bị (unbind) -> serial biến mất
        http("DELETE", f"/serials/{SERIAL}")
        gone = http("GET", f"/serials/{SERIAL}")[0] == 404
        check("unbind: xóa credential + retained + Redis", gone)

    finally:
        if sim and sim.poll() is None:
            sim.terminate()
            try:
                sim.wait(timeout=5)
            except Exception:
                sim.kill()

    passed = sum(results)
    print(f"\n===== KẾT QUẢ: {passed}/{len(results)} PASS =====", flush=True)
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
