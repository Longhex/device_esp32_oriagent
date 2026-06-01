"""Smoke test: chứng minh EMQX nhận pub/sub cơ bản (ẩn danh).
Chạy: python smoke_test.py [host] [port]
"""
import sys
import time
import paho.mqtt.client as mqtt

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 1883
TOPIC = "smoke/test"

received = []


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"[connect] rc={reason_code}")
    client.subscribe(TOPIC, qos=1)


def on_message(client, userdata, msg):
    received.append(msg.payload.decode())
    print(f"[recv] {msg.topic} = {msg.payload.decode()}")


c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smoke-tester")
c.on_connect = on_connect
c.on_message = on_message
c.connect(HOST, PORT, keepalive=30)
c.loop_start()
time.sleep(1.0)
c.publish(TOPIC, "hello-emqx", qos=1)
time.sleep(1.0)
c.loop_stop()
c.disconnect()

if "hello-emqx" in received:
    print("SMOKE TEST PASSED")
    sys.exit(0)
print("SMOKE TEST FAILED")
sys.exit(1)
