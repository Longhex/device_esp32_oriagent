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
)


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
            result["subscribe_topic"], "HKHT2606010046/AI_REMOTE"
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
            result["subscribe_topic"], "HKHT2606010046/AI_REMOTE"
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
