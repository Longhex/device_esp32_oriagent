"""Kiểm chứng ACL cô lập per-device:
- Device được subscribe topic CỦA MÌNH  -> granted (qos 1)
- Device bị từ chối subscribe topic THIẾT BỊ KHÁC -> denied (rc 128)
"""
import os
import sys
import time
import paho.mqtt.client as mqtt

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common

CLIENT = "HKHT2606010011"   # định danh = Serial-Number
PASSWORD = os.getenv("TEST_DEVICE_PASSWORD", "")
if not PASSWORD:
    raise SystemExit("TEST_DEVICE_PASSWORD is required")

results = {}


def on_subscribe(client, userdata, mid, reason_codes, properties):
    results[mid] = [int(rc.value) if hasattr(rc, "value") else int(rc) for rc in reason_codes]


c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT)
c.username_pw_set(CLIENT, PASSWORD)
c.on_subscribe = on_subscribe
c.connect(common.EMQX_HOST, common.EMQX_MQTT_PORT, keepalive=15)
c.loop_start()
time.sleep(0.5)

own = c.subscribe(common.topic_command(CLIENT), qos=1)[1]      # cho phép
legacy_own = c.subscribe(common.legacy_command_topic(CLIENT), qos=1)[1]
other = c.subscribe("devices/zz_99_88_77_66_55/command", qos=1)[1]  # phải bị chặn
time.sleep(1.0)
c.loop_stop()
c.disconnect()

own_rc = results.get(own, [None])[0]
other_rc = results.get(other, [None])[0]
legacy_own_rc = results.get(legacy_own, [None])[0]
print(f"subscribe OWN topic   rc={own_rc}  (kỳ vọng 1 = granted qos1)")
print(f"subscribe LEGACY OWN  rc={legacy_own_rc}  (kỳ vọng 1 = granted qos1)")
print(f"subscribe OTHER topic rc={other_rc}  (kỳ vọng 128 = denied)")

if own_rc in (0, 1) and legacy_own_rc in (0, 1) and other_rc == 128:
    print("ACL TEST PASSED")
    sys.exit(0)
print("ACL TEST FAILED")
sys.exit(1)
