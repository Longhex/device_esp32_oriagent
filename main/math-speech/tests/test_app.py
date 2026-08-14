import unittest
from concurrent.futures import ThreadPoolExecutor

import app


class MathSpeechAppTests(unittest.TestCase):
    def test_health_reports_vietnamese_rules(self):
        result = app.health()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["language"], "vi")
        self.assertEqual(result["renderer"], "structured-vi+mathcat")

    def test_speak_works_from_fastapi_style_worker_thread(self):
        request = app.SpeakRequest(latex=r"\frac{1}{2}+x^2")
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(app.speak, request).result(timeout=5)
        self.assertTrue(result.ok)
        self.assertIn("bình phương", result.text)

    def test_exactly_one_input_is_required(self):
        with self.assertRaises(ValueError):
            app.SpeakRequest()
        with self.assertRaises(ValueError):
            app.SpeakRequest(latex="x", mathml="<math><mi>x</mi></math>")


def _spoken(latex: str) -> str:
    result = app.speak(app.SpeakRequest(latex=latex))
    assert result.ok
    return result.text


class VietnameseSpeechTests(unittest.TestCase):
    """Guards for the corrections in rules_overrides/vi.json."""

    def _spoken(self, latex: str) -> str:
        return _spoken(latex)

    def test_concrete_values_say_phan(self):
        self.assertEqual(self._spoken(r"\frac{1}{2}"), "một phần hai")
        self.assertEqual(self._spoken(r"\frac{25}{7}"), "hai mươi lăm phần bảy")
        self.assertEqual(self._spoken("1/2"), "một phần hai")
        self.assertEqual(self._spoken("25/7"), "hai mươi lăm phần bảy")

    def test_variables_say_tren(self):
        self.assertEqual(self._spoken(r"\frac{a}{b}"), "a trên b")
        self.assertEqual(self._spoken("a/b"), "a trên b")
        # Chỉ cần một vế là ẩn thì đã không còn là "giá trị cụ thể".
        self.assertEqual(self._spoken(r"\frac{a}{2}"), "a trên hai")
        self.assertEqual(self._spoken("a/2"), "a trên hai")

    def test_compound_numerator_is_scoped_with_tat_ca(self):
        # Đây là cặp phải nghe khác nhau rõ ràng.
        self.assertEqual(self._spoken("(a+1)/2"), "phân số, a cộng một, tất cả trên hai")
        self.assertEqual(self._spoken(r"\frac{a+1}{2}"), "phân số, a cộng một, tất cả trên hai")
        self.assertEqual(self._spoken("a + 1/2"), "a cộng một phần hai")

    def test_quadratic_formula(self):
        self.assertEqual(
            self._spoken(r"x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}"),
            "x bằng phân số, âm b cộng hoặc trừ căn bậc hai của "
            "b bình phương trừ bốn a c, tất cả trên hai a",
        )

    def test_scope_markers_only_where_they_disambiguate(self):
        for latex in (r"\frac{a+b}{c}", "(a+b)/c + d", "(a+b)/(c+d)"):
            spoken = self._spoken(latex)
            self.assertNotIn("hết phân số", spoken)
        self.assertEqual(
            self._spoken(r"\sqrt{x+1} + 2"),
            "căn bậc hai của x cộng một, hết căn, cộng hai",
        )
        self.assertEqual(self._spoken("(a+b)/c + d"), "phân số, a cộng b, tất cả trên c cộng d")

    def test_nested_fraction_stays_readable(self):
        self.assertEqual(
            self._spoken(r"\frac{\frac{a}{b}}{c}"), "phân số, a trên b, tất cả trên c"
        )

    def test_roots_mark_their_scope_when_followed_by_arithmetic(self):
        self.assertEqual(self._spoken(r"\sqrt{x+1} + 2"), "căn bậc hai của x cộng một, hết căn, cộng hai")
        self.assertEqual(self._spoken(r"x = \sqrt{a+b}"), "x bằng căn bậc hai của a cộng b")

    def test_plus_minus_is_spelled_out(self):
        self.assertEqual(self._spoken(r"a \pm b"), "a cộng hoặc trừ b")

    def test_division_sign_still_says_chia(self):
        self.assertEqual(self._spoken(r"a \div b"), "a chia b")

    def test_product_is_tich_not_pi(self):
        spoken = self._spoken(r"\prod_{i=1}^{n} i")
        self.assertIn("tích", spoken)
        self.assertNotIn("pi", spoken)

    def test_logarithms(self):
        self.assertIn("lô ga rít", self._spoken(r"\log x"))
        self.assertIn("lô ga rít tự nhiên", self._spoken(r"\ln x"))
        self.assertNotIn("lóc", self._spoken(r"\log_2 x"))

    def test_absolute_value_says_cua_once(self):
        self.assertNotIn("của của", self._spoken(r"|x|"))

    def test_limit_says_khi(self):
        spoken = self._spoken(r"\lim_{x \to 0} x")
        self.assertIn("giới hạn của", spoken)
        self.assertIn("khi x tiến tới không", spoken)

    def test_output_has_no_repeated_blanks(self):
        for latex in (r"x \neq 5", r"x \in A", r"\angle ABC"):
            self.assertNotIn("  ", self._spoken(latex))


class TidyTests(unittest.TestCase):
    def test_collapses_blanks_semicolons_and_stray_commas(self):
        self.assertEqual(app._tidy("x  khác  5"), "x khác 5")
        self.assertEqual(app._tidy("a; b"), "a, b")
        self.assertEqual(app._tidy("a , , b"), "a, b")
        self.assertEqual(app._tidy(" a phần b, "), "a phần b")


if __name__ == "__main__":
    unittest.main()
