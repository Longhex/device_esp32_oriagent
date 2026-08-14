"""Verify the Vietnamese rule overrides against the vendored MathCAT archive.

These tests do not import MathCAT, so they run on the repo's Python 3.10 as
well as inside the 3.11 image.
"""

import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_DIR / "scripts"))

from apply_rule_overrides import OverrideError, apply_overrides  # noqa: E402

VENDOR_RULES = SERVICE_DIR / "vendor" / "Rules"
OVERRIDES_DIR = SERVICE_DIR / "rules_overrides"


def _read_vi(rules_dir: Path, name: str) -> str:
    with zipfile.ZipFile(rules_dir / "Languages" / "vi" / "vi.zip") as archive:
        return archive.read(name).decode("utf-8")


class RuleOverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls.out_dir = Path(cls._tmp) / "rules"
        apply_overrides(VENDOR_RULES, OVERRIDES_DIR, cls.out_dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_vendored_rules_are_left_untouched(self):
        self.assertIn("  - T: trên", _read_vi(VENDOR_RULES, "SimpleSpeak_Rules.yaml"))

    def test_fraction_rule_picks_phan_or_tren_by_operand_type(self):
        simple_speak = _read_vi(self.out_dir, "SimpleSpeak_Rules.yaml")
        self.assertIn('      if: "*[1][self::m:mn] and *[2][self::m:mn]"', simple_speak)
        self.assertIn("      then: [{T: phần}]", simple_speak)
        self.assertIn("      else: [{T: trên}]", simple_speak)
        self.assertNotIn("  - T: trên\n", simple_speak)

    def test_compound_fraction_says_tat_ca_tren(self):
        simple_speak = _read_vi(self.out_dir, "SimpleSpeak_Rules.yaml")
        self.assertEqual(simple_speak.count("  - T: tất cả trên"), 2)
        self.assertEqual(simple_speak.count("  - T: phân số"), 2)

    def test_end_markers_are_gone(self):
        simple_speak = _read_vi(self.out_dir, "SimpleSpeak_Rules.yaml")
        self.assertNotIn("hết căn", simple_speak)
        self.assertNotIn("hết phân số", simple_speak)

    def test_slash_rules_precede_the_shared_includes(self):
        simple_speak = _read_vi(self.out_dir, "SimpleSpeak_Rules.yaml")
        for name in ("- name: slash-simple", "- name: slash-compound"):
            self.assertIn(name, simple_speak)
            self.assertLess(
                simple_speak.index(name),
                simple_speak.index('- include: "SharedRules/'),
                f"{name} must come before the SharedRules includes to win",
            )

    def test_unit_fractions_keep_saying_tren(self):
        # "5 mét trên giây" must not become "5 mét phần giây".
        simple_speak = _read_vi(self.out_dir, "SimpleSpeak_Rules.yaml")
        self.assertIn('  - t: "trên"', simple_speak)

    def test_superscript_keeps_saying_tren(self):
        shared_default = _read_vi(self.out_dir, "SharedRules/default.yaml")
        self.assertIn("""  - T: "trên"      # phrase(x 'super' 2)""", shared_default)
        self.assertIn("""  - T: "phần"               # phrase(""", shared_default)

    def test_slash_says_tren_but_division_sign_keeps_chia(self):
        unicode_yaml = _read_vi(self.out_dir, "unicode.yaml")
        self.assertIn(' - "/": [T: trên]', unicode_yaml)
        self.assertIn(' - "÷": [T: chia]', unicode_yaml)

    def test_product_and_logarithm_translations(self):
        unicode_yaml = _read_vi(self.out_dir, "unicode.yaml")
        self.assertIn(' - "∏": [T: tích]', unicode_yaml)
        self.assertNotIn(' - "∏": [T: pi]', unicode_yaml)

        general = _read_vi(self.out_dir, "SharedRules/general.yaml")
        self.assertNotIn("lóc", general)
        self.assertIn('[T: "lô-ga-rít"]', general)

    def test_absolute_value_no_longer_doubles_cua(self):
        definitions = _read_vi(self.out_dir, "definitions.yaml")
        self.assertIn(
            '"absolute-value": "function= ; trị tuyệt đối: trị tuyệt đối: '
            'trị tuyệt đối; hết trị tuyệt đối"',
            definitions,
        )

    def test_missing_target_line_fails_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_overrides = Path(tmp) / "overrides"
            bad_overrides.mkdir()
            spec = json.loads((OVERRIDES_DIR / "vi.json").read_text(encoding="utf-8"))
            spec["edits"] = [
                {
                    "file": "SimpleSpeak_Rules.yaml",
                    "find": "  - T: khong-ton-tai",
                    "replace": "  - T: x",
                    "count": 1,
                }
            ]
            (bad_overrides / "vi.json").write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaises(OverrideError):
                apply_overrides(VENDOR_RULES, bad_overrides, Path(tmp) / "out")

    def test_refuses_to_patch_the_vendored_tree_in_place(self):
        with self.assertRaises(OverrideError):
            apply_overrides(VENDOR_RULES, OVERRIDES_DIR, VENDOR_RULES)


if __name__ == "__main__":
    unittest.main()
