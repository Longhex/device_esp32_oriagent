"""E2E tự động cho mặt phẳng quản lý MQTT — chạy 1 lệnh, tự dọn.

Yêu cầu: EMQX đang chạy (docker compose up -d emqx) + đã provision auth.
Script tự: chạy provision (idempotent) -> bật consumer -> bật device giả lập ->
kiểm presence/telemetry/command-ack/LWT/ACL -> tắt mọi tiến trình -> in tổng kết.

Chạy:  python tests/e2e_test.py
Exit code 0 = tất cả PASS.
"""
import os
import sys
import time
import json
import signal
import subprocess
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import common  # noqa: E402

PY = sys.executable
HTTP_PORT = int(os.getenv("E2E_HTTP_PORT", "8091"))
BASE = f"http://127.0.0.1:{HTTP_PORT}"
DEVICE = "HKHT2606010011"   # định danh = Serial-Number
DEVICE_PASS = "dev01_secret_2024"

results = []  # (name, ok, detail)


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    mark = "✅ PASS" if ok else "❌ FAIL"
    print(f"{mark}  {name}" + (f"  — {detail}" if detail else ""), flush=True)
    return ok


def http_get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def http_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


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


def run_env():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["MONITOR_HTTP_PORT"] = str(HTTP_PORT)
    return env


def main():
    env = run_env()
    consumer = None
    sim = None
    try:
        # 0) provision idempotent
        p = subprocess.run([PY, os.path.join(ROOT, "provision_auth.py")],
                           env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        check("provision auth/ACL (idempotent)", "PROVISION DONE" in p.stdout, p.stdout.strip().splitlines()[-1] if p.stdout else p.stderr[-200:])

        # 1) bật consumer
        consumer = subprocess.Popen([PY, os.path.join(ROOT, "consumer.py")], env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        up = wait_until(lambda: http_get("/healthz")[0] == 200, timeout=15)
        check("consumer HTTP API lên", up, BASE)
        if not up:
            return

        # 2) bật device giả lập
        sim = subprocess.Popen([PY, os.path.join(ROOT, "sim_device.py"), DEVICE, DEVICE_PASS, "2"],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 3) presence ONLINE
        online = wait_until(lambda: http_get(f"/devices/{DEVICE}")[1].get("online") is True, timeout=15)
        check("presence ONLINE (retained)", online)

        # 4) telemetry
        def has_tele():
            d = http_get(f"/devices/{DEVICE}")[1]
            return bool(d.get("telemetry")) and "battery_pct" in d["telemetry"]
        check("telemetry nhận được", wait_until(has_tele, timeout=10))

        # 5) command + ack
        st, resp = http_post(f"/devices/{DEVICE}/command",
                             {"action": "set_config", "params": {"report_interval": 10}})
        cmd_id = resp.get("command_id")
        ack_ok = wait_until(
            lambda: (http_get(f"/devices/{DEVICE}")[1].get("last_ack") or {}).get("id") == cmd_id,
            timeout=10)
        check("command + ack round-trip", ack_ok and st == 202, f"cmd_id={cmd_id}")

        # 6) LWT offline khi kill cứng
        sim.terminate()  # Windows: TerminateProcess -> abrupt -> LWT
        sim.wait(timeout=5)
        offline = wait_until(lambda: http_get(f"/devices/{DEVICE}")[1].get("online") is False, timeout=25)
        check("offline tự động qua LWT", offline)
        sim = None

        # 7) ACL per-device
        acl = subprocess.run([PY, os.path.join(HERE, "acl_test.py")], env=env,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
        check("ACL cô lập per-device", "ACL TEST PASSED" in acl.stdout,
              acl.stdout.strip().splitlines()[-1] if acl.stdout else acl.stderr[-200:])

    finally:
        for proc in (sim, consumer):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()

    # tổng kết
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n===== KẾT QUẢ: {passed}/{total} PASS =====", flush=True)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
