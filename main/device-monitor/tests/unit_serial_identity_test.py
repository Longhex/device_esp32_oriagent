import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from serial_store import normalize_serial_identity  # noqa: E402


class SerialIdentityTest(unittest.TestCase):
    def test_lowercase_mac_is_canonicalized(self):
        self.assertEqual(
            normalize_serial_identity("28:84:85:89:59:6c"),
            "28:84:85:89:59:6C",
        )

    def test_hyphenated_mac_is_canonicalized(self):
        self.assertEqual(
            normalize_serial_identity("28-84-85-89-59-6c"),
            "28:84:85:89:59:6C",
        )

    def test_real_serial_preserves_case(self):
        self.assertEqual(
            normalize_serial_identity("HkHt2606010046"),
            "HkHt2606010046",
        )


if __name__ == "__main__":
    unittest.main()
