import os
import queue
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.mqtt_server import build_hk_server_hello
from core.mqtt_topics import (
    hk_device_publish_topic,
    hk_device_subscribe_topic,
    parse_hk_uplink_topic,
)
from core.udp_server import (
    HkEncryptedUdpSession,
    build_hk_udp_packet,
    parse_hk_udp_packet,
)


class FakeTransport:
    def __init__(self):
        self.sent = []

    def sendto(self, payload, addr):
        self.sent.append((payload, addr))


class HkMqttUdpContractTest(unittest.TestCase):
    def setUp(self):
        self.key = bytes.fromhex("00112233445566778899aabbccddeeff")
        self.client_ssrc = 0x10203040
        self.audio_queue = queue.Queue()
        self.session = HkEncryptedUdpSession(
            "HKHT2606010011",
            "A1B2C3D4E5F60708",
            self.audio_queue,
            output_sample_rate=24000,
            frame_duration=60,
            key=self.key,
            client_ssrc=self.client_ssrc,
        )

    def test_nonce_template_matches_firmware_header(self):
        config = self.session.hello_udp_config("device.example.com", 8883)
        nonce = bytes.fromhex(config["nonce"])
        self.assertEqual(len(nonce), 16)
        self.assertEqual(nonce[0], 0x01)
        self.assertEqual(int.from_bytes(nonce[4:8], "big"), self.client_ssrc)
        self.assertEqual(config["key"], self.key.hex())

    def test_device_uplink_is_decrypted_into_asr_queue(self):
        opus = b"opus-uplink-frame"
        packet = build_hk_udp_packet(
            self.key, self.client_ssrc, 960, 1, opus
        )
        self.assertTrue(self.session.handle_datagram(packet, ("10.0.0.5", 40000)))
        queued = self.audio_queue.get_nowait()
        self.assertEqual(queued["type"], "audio")
        self.assertEqual(queued["payload"], opus)
        self.assertEqual(queued["sequence"], 1)
        self.assertEqual(queued["timestamp"], 960)
        self.assertIsInstance(queued["received_monotonic"], float)

    def test_server_downlink_uses_separate_ssrc_and_sequence_one(self):
        transport = FakeTransport()
        self.session.transport = transport
        self.session.client_addr = ("10.0.0.5", 40000)
        opus = b"opus-downlink-frame"
        self.assertTrue(self.session.send_audio(opus))
        packet, addr = transport.sent[0]
        _, ssrc, timestamp, sequence, decrypted = parse_hk_udp_packet(
            self.key, packet, expected_ssrc=self.session.server_ssrc
        )
        self.assertEqual(addr, self.session.client_addr)
        self.assertEqual(ssrc, self.session.server_ssrc)
        self.assertEqual(timestamp, 1440)
        self.assertEqual(sequence, 1)
        self.assertEqual(decrypted, opus)

    def test_server_hello_contains_udp_contract(self):
        base = (
            '{"type":"hello","transport":"websocket",'
            '"audio_params":{"format":"opus","sample_rate":24000,'
            '"channels":1,"frame_duration":60}}'
        )
        result = build_hk_server_hello(
            base,
            self.session.session_id,
            self.session.hello_udp_config("device.example.com", 8883),
        )
        self.assertIn('"transport":"udp"', result)
        self.assertIn('"session_id":"A1B2C3D4E5F60708"', result)
        self.assertIn('"port":8883', result)
        self.assertNotIn('"transport":"websocket"', result)

    def test_ota_advertised_topics_route_to_same_device(self):
        device_id = "HKHT2606010046"
        uplink = hk_device_publish_topic(device_id)
        self.assertEqual(uplink, "HKHT2606010046/AI_MONITOR")
        self.assertEqual(
            hk_device_subscribe_topic(device_id),
            "HKHT2606010046/MONITOR",
        )
        self.assertEqual(
            parse_hk_uplink_topic(uplink),
            (device_id, "HKHT2606010046/MONITOR"),
        )

    def test_legacy_topic_remains_compatible_during_rollout(self):
        self.assertEqual(
            parse_hk_uplink_topic("HKHT2606010011"),
            ("HKHT2606010011", "HKHT2606010011/MONITOR"),
        )


if __name__ == "__main__":
    unittest.main()
