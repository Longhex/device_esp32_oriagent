import os
import sys
import unittest

os.environ.setdefault("ENABLE_HK_LEGACY_BRIDGE", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from consumer import _legacy_command_payload  # noqa: E402
from emqx_admin import EmqxAdmin  # noqa: E402


class CaptureAdmin(EmqxAdmin):
    def __init__(self):
        super().__init__(api_base="http://unused", user="test", password="test")
        self.requests = []

    def _request(self, method, path, body=None, **kwargs):
        self.requests.append((method, path, body))
        return 200, {}


class LegacyCommandPayloadTest(unittest.TestCase):
    def test_reboot(self):
        self.assertEqual(_legacy_command_payload("reboot"), {"cmd": "reboot"})

    def test_ota_alias(self):
        self.assertEqual(
            _legacy_command_payload("ota", {"url": "https://example/fw.bin"}),
            {"cmd": "fota", "url": "https://example/fw.bin"},
        )

    def test_volume(self):
        self.assertEqual(
            _legacy_command_payload("volume", {"value": 42}),
            {"cmd": "volume", "value": 42},
        )

    def test_unsupported_action_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unsupported_by_current_firmware"):
            _legacy_command_payload("find")

    def test_required_param(self):
        with self.assertRaisesRegex(ValueError, "missing_required_param:url"):
            _legacy_command_payload("ota", {})


class LegacyVoiceAclTest(unittest.TestCase):
    def test_device_acl_allows_own_voice_topics(self):
        admin = CaptureAdmin()
        admin.set_device_acl("HKHT2606010011")
        rules = admin.requests[-1][2][0]["rules"]
        allowed = {(rule["action"], rule["topic"]) for rule in rules}
        self.assertIn(("publish", "HKHT2606010011"), allowed)
        self.assertIn(("subscribe", "HKHT2606010011/MONITOR"), allowed)
        self.assertNotIn(("publish", "+"), allowed)

    def test_backend_acl_allows_bare_voice_subscribe(self):
        admin = CaptureAdmin()
        admin.set_full_acl("oriagent-monitor")
        rules = admin.requests[-1][2][0]["rules"]
        allowed = {(rule["action"], rule["topic"]) for rule in rules}
        self.assertIn(("subscribe", "+"), allowed)
        self.assertIn(("publish", "+/MONITOR"), allowed)


if __name__ == "__main__":
    unittest.main()
