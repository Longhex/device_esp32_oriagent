import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.api.ota_handler import (  # noqa: E402
    OTAHandler,
    build_firmware_mqtt_config,
    resolve_ota_serial_number,
)
from core.utils.util import protocol_payload_json_for_log  # noqa: E402


def make_handler():
    handler = OTAHandler.__new__(OTAHandler)
    handler.config = {
        "server": {
            "websocket": "",
            "websocket_protocol_version": 1,
        }
    }
    return handler


def make_request(host="device.example.com", scheme="http", headers=None):
    return SimpleNamespace(host=host, scheme=scheme, headers=headers or {})


class OtaPublicContractTest(unittest.TestCase):
    def test_protocol_log_keeps_contract_fields_and_redacts_credentials(self):
        logged = protocol_payload_json_for_log(
            {
                "mqtt": {
                    "endpoint": "194.163.186.89:1883",
                    "client_id": "HKHT2606010046",
                    "username": "device-user",
                    "password": "device-password",
                    "publish_topic": "HKHT2606010046/AI_MONITOR",
                },
                "websocket": {"token": "secret-token"},
                "udp": {"key": "secret-key", "nonce": "secret-nonce"},
            }
        )
        self.assertIn('"endpoint":"194.163.186.89:1883"', logged)
        self.assertIn('"client_id":"HKHT2606010046"', logged)
        self.assertIn('"username":"device-user"', logged)
        self.assertIn('"publish_topic":"HKHT2606010046/AI_MONITOR"', logged)
        self.assertNotIn("device-password", logged)
        self.assertNotIn("secret-token", logged)
        self.assertNotIn("secret-key", logged)
        self.assertNotIn("secret-nonce", logged)
        self.assertEqual(logged.count("<redacted:set>"), 4)

    def test_ota_serial_header_wins_over_device_mac(self):
        serial, used_mac_fallback = resolve_ota_serial_number(
            {"serial-number": "HKHT2606010046"},
            "28:84:85:89:59:6C",
        )
        self.assertEqual(serial, "HKHT2606010046")
        self.assertFalse(used_mac_fallback)

    def test_ota_serial_falls_back_to_device_mac_when_header_is_missing(self):
        serial, used_mac_fallback = resolve_ota_serial_number(
            {},
            "28:84:85:89:59:6C",
        )
        self.assertEqual(serial, "28:84:85:89:59:6C")
        self.assertTrue(used_mac_fallback)

    def test_blank_ota_serial_header_falls_back_to_device_mac(self):
        serial, used_mac_fallback = resolve_ota_serial_number(
            {"serial-number": "   "},
            "28:84:85:89:59:6C",
        )
        self.assertEqual(serial, "28:84:85:89:59:6C")
        self.assertTrue(used_mac_fallback)

    def test_mac_serial_header_is_canonicalized_before_provisioning(self):
        serial, used_mac_fallback = resolve_ota_serial_number(
            {"serial-number": "28:84:85:89:59:6c"},
            "28:84:85:89:59:6C",
        )
        self.assertEqual(serial, "28:84:85:89:59:6C")
        self.assertFalse(used_mac_fallback)

    def test_hyphenated_mac_serial_header_is_canonicalized(self):
        serial, used_mac_fallback = resolve_ota_serial_number(
            {"serial-number": "28-84-85-89-59-6c"},
            "28:84:85:89:59:6C",
        )
        self.assertEqual(serial, "28:84:85:89:59:6C")
        self.assertFalse(used_mac_fallback)

    def test_real_serial_preserves_its_case(self):
        serial, used_mac_fallback = resolve_ota_serial_number(
            {"serial-number": "HkHt2606010046"},
            "28:84:85:89:59:6C",
        )
        self.assertEqual(serial, "HkHt2606010046")
        self.assertFalse(used_mac_fallback)

    def test_mqtt_topics_are_derived_from_provisioned_client_id(self):
        result = build_firmware_mqtt_config({
            "endpoint": "broker.hkrobotics.ai",
            "client_id": "HKHT2606010046",
            "username": "device-user",
            "password": "device-password",
        })
        self.assertEqual(
            result["publish_topic"], "HKHT2606010046/AI_MONITOR"
        )
        self.assertEqual(
            result["subscribe_topic"], "HKHT2606010046/MONITOR"
        )

    def test_mqtt_topics_use_serial_when_client_id_is_generated(self):
        result = build_firmware_mqtt_config(
            {
                "endpoint": "broker.hkrobotics.ai",
                "client_id": "GID_test@@@90_70_69_19_9d_00@@@uuid",
                "username": "device-user",
                "password": "device-password",
            },
            topic_identity="HKHT2606010046",
        )
        self.assertEqual(
            result["publish_topic"], "HKHT2606010046/AI_MONITOR"
        )
        self.assertEqual(
            result["subscribe_topic"], "HKHT2606010046/MONITOR"
        )

    def test_mqtt_topics_are_standardized_for_colon_serial(self):
        result = build_firmware_mqtt_config(
            {
                "endpoint": "broker.hkrobotics.ai",
                "client_id": "A0:F2:62:EA:1E:68",
                "username": "A0:F2:62:EA:1E:68",
                "password": "device-password",
                "publish_topic": "A0_F2_62_EA_1E_68/AI_MONITOR",
                "subscribe_topic": "A0_F2_62_EA_1E_68/AI_REMOTE",
            },
            topic_identity="A0:F2:62:EA:1E:68",
        )
        self.assertEqual(result["client_id"], "A0:F2:62:EA:1E:68")
        self.assertEqual(
            result["publish_topic"], "A0:F2:62:EA:1E:68/AI_MONITOR"
        )
        self.assertEqual(
            result["subscribe_topic"], "a0:f2:62:ea:1e:68/MONITOR"
        )

    def test_generated_topics_normalize_mac_identity(self):
        result = build_firmware_mqtt_config(
            {
                "endpoint": "broker.hkrobotics.ai",
                "client_id": "A0:F2:62:EA:1E:68",
                "username": "A0:F2:62:EA:1E:68",
                "password": "device-password",
            }
        )
        self.assertEqual(
            result["publish_topic"], "A0:F2:62:EA:1E:68/AI_MONITOR"
        )
        self.assertEqual(
            result["subscribe_topic"], "a0:f2:62:ea:1e:68/MONITOR"
        )
    def test_explicit_public_url_wins(self):
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "PUBLIC_WEBSOCKET_URL": "wss://voice.example.com/xiaozhi/v1/",
                "PUBLIC_DOMAIN": "",
            },
            clear=False,
        ):
            url = make_handler()._get_websocket_url("127.0.0.1", 8000)
        self.assertEqual(url, "wss://voice.example.com/xiaozhi/v1/")

    def test_public_domain_builds_wss(self):
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "PUBLIC_WEBSOCKET_URL": "",
                "PUBLIC_DOMAIN": "device.example.com",
            },
            clear=False,
        ):
            url = make_handler()._get_websocket_url("127.0.0.1", 8000)
        self.assertEqual(url, "wss://device.example.com/xiaozhi/v1/")

    def test_trusted_proxy_builds_wss_and_https_origin(self):
        request = make_request(
            headers={
                "Host": "edge:80",
                "X-Forwarded-Host": "device.example.com",
                "X-Forwarded-Proto": "https",
            }
        )
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "PUBLIC_WEBSOCKET_URL": "",
                "PUBLIC_DOMAIN": "",
                "TRUST_PROXY_HEADERS": "true",
            },
            clear=False,
        ):
            handler = make_handler()
            self.assertEqual(
                handler._get_websocket_url("127.0.0.1", 8000, request),
                "wss://device.example.com/xiaozhi/v1/",
            )
            self.assertEqual(
                handler._get_public_http_origin(request),
                "https://device.example.com",
            )

    def test_production_rejects_private_ws(self):
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "PUBLIC_WEBSOCKET_URL": "ws://192.168.1.10/xiaozhi/v1/",
                "PUBLIC_DOMAIN": "",
            },
            clear=False,
        ):
            with self.assertRaises(ValueError):
                make_handler()._get_websocket_url("127.0.0.1", 8000)


if __name__ == "__main__":
    unittest.main()
