import unittest

from latex2mathml.converter import convert

from vietnamese_renderer import (
    UnsupportedMathML,
    integer_to_vietnamese,
    render_mathml,
)


def spoken(latex: str) -> str:
    return render_mathml(convert(latex))


class VietnameseNumberTests(unittest.TestCase):
    def test_integer_words(self):
        cases = {
            0: "không",
            4: "bốn",
            10: "mười",
            25: "hai mươi lăm",
            104: "một trăm linh bốn",
            2025: "hai nghìn không trăm hai mươi lăm",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(integer_to_vietnamese(value), expected)


class VietnameseRendererTests(unittest.TestCase):
    def test_quadratic_formula(self):
        self.assertEqual(
            spoken(r"x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}"),
            "x bằng phân số, âm b cộng hoặc trừ căn bậc hai của "
            "b bình phương trừ bốn a c, tất cả trên hai a",
        )

    def test_fraction_scope_and_inline_slash(self):
        self.assertEqual(spoken(r"\frac{1}{2}"), "một phần hai")
        self.assertEqual(spoken(r"\frac{a}{b}"), "a trên b")
        self.assertEqual(spoken("(a+1)/2"), "phân số, a cộng một, tất cả trên hai")
        self.assertEqual(spoken("a+1/2"), "a cộng một phần hai")
        self.assertEqual(
            spoken(r"\frac{\frac{a}{b}}{c}"),
            "phân số, a trên b, tất cả trên c",
        )

    def test_root_scope_is_audible_only_when_needed(self):
        self.assertEqual(
            spoken(r"\sqrt{a+b}+c"),
            "căn bậc hai của a cộng b, hết căn, cộng c",
        )
        self.assertEqual(
            spoken(r"\sqrt{a+b+c}"),
            "căn bậc hai của a cộng b cộng c",
        )
        self.assertEqual(spoken(r"\sqrt[3]{a+b}"), "căn bậc ba của a cộng b")

    def test_powers_functions_and_logarithms(self):
        self.assertEqual(spoken(r"x^{a+b}"), "x mũ, a cộng b")
        self.assertEqual(spoken(r"f(x)=x^2+1"), "f của x bằng x bình phương cộng một")
        self.assertEqual(spoken(r"\log_2 8=3"), "lô ga rít cơ số hai của tám bằng ba")
        self.assertEqual(
            spoken(r"\sin^2x+\cos^2x=1"),
            "sin bình phương x cộng cos bình phương x bằng một",
        )

    def test_calculus_large_operators(self):
        self.assertEqual(
            spoken(r"\sum_{i=1}^{n}i"), "tổng từ i bằng một đến n của i"
        )
        self.assertEqual(
            spoken(r"\prod_{i=1}^{n}i"), "tích từ i bằng một đến n của i"
        )
        self.assertEqual(
            spoken(r"\lim_{x\to0}f(x)"),
            "giới hạn của f của x khi x tiến tới không",
        )
        self.assertEqual(
            spoken(r"\int_a^b f(x)dx"),
            "tích phân từ a đến b của f của x theo x",
        )
        self.assertEqual(spoken(r"\frac{dy}{dx}"), "đạo hàm của y theo x")

    def test_grouping_absolute_value_prime_and_matrix(self):
        self.assertEqual(spoken(r"|a-b|"), "giá trị tuyệt đối của a trừ b")
        self.assertEqual(spoken(r"f\prime\prime(x)"), "f hai phẩy của x")
        self.assertEqual(
            spoken(r"\begin{pmatrix}a&b\\c&d\end{pmatrix}"),
            "ma trận có hai hàng, hàng một là a, b; hàng hai là c, d",
        )

    def test_common_advanced_structures(self):
        self.assertEqual(spoken(r"f''(x)"), "f hai phẩy của x")
        self.assertEqual(spoken(r"\frac{d^2y}{dx^2}"), "đạo hàm bậc hai của y theo x")
        self.assertEqual(spoken(r"\frac{\partial f}{\partial x}"), "đạo hàm riêng của f theo x")
        self.assertEqual(spoken(r"\binom{n}{k}"), "tổ hợp chập k của n")
        self.assertEqual(spoken(r"\lVert x\rVert"), "chuẩn của x")
        self.assertEqual(spoken(r"x\to-\infty"), "x tiến tới âm vô cùng")
        self.assertEqual(
            spoken(r"\begin{cases}x+y=2\\x-y=0\end{cases}"),
            "hệ phương trình gồm, x cộng y bằng hai; x trừ y bằng không",
        )
        self.assertEqual(
            spoken(r"f(x)=\begin{cases}x^2&x\ge0\\-x&x<0\end{cases}"),
            "f của x bằng hàm từng phần, x bình phương khi x lớn hơn hoặc bằng không; "
            "âm x khi x nhỏ hơn không",
        )

    def test_unknown_operator_requests_mathcat_fallback(self):
        with self.assertRaises(UnsupportedMathML):
            render_mathml("<math><mi>a</mi><mo>⪙</mo><mi>b</mi></math>")


if __name__ == "__main__":
    unittest.main()
