import unittest

from core.utils.math_extractor import StreamingMathExtractor


class FakeSpeaker:
    def __init__(self, result="CÔNG_THỨC"):
        self.result = result
        self.calls = []

    def speak(self, formula, source="latex"):
        self.calls.append((formula, source))
        return self.result


def extract(chunks, speaker=None):
    speaker = speaker or FakeSpeaker()
    extractor = StreamingMathExtractor(speaker)
    output = "".join(extractor.feed(chunk) for chunk in chunks)
    return output + extractor.flush(), speaker


class StreamingMathExtractorTests(unittest.TestCase):
    def test_all_supported_delimiters(self):
        output, speaker = extract(
            ["A $x^2$ B $$\\frac{1}{2}$$ C \\(a+b\\) D \\[y=3\\]"]
        )
        self.assertEqual(
            output,
            "A CÔNG_THỨC B CÔNG_THỨC C CÔNG_THỨC D CÔNG_THỨC",
        )
        self.assertEqual(
            [call[0] for call in speaker.calls],
            ["x^2", "\\frac{1}{2}", "a+b", "y=3"],
        )

    def test_every_single_split_preserves_streaming_result(self):
        source = "Trước \\[x=\\frac{-b}{2a}\\] sau"
        for split_at in range(len(source) + 1):
            with self.subTest(split_at=split_at):
                output, speaker = extract(
                    [source[:split_at], source[split_at:]],
                    FakeSpeaker("ích bằng phân số"),
                )
                self.assertEqual(output, "Trước ích bằng phân số sau")
                self.assertEqual(len(speaker.calls), 1)

    def test_multiple_formulas_and_plain_text_keep_order(self):
        output, _ = extract(["$x", "+1$ rồi ", "$y", "^2$ hết"])
        self.assertEqual(output, "CÔNG_THỨC rồi CÔNG_THỨC hết")

    def test_currency_and_pure_numbers_are_not_converted(self):
        output, speaker = extract(["Giá $5 và $10, mã $123$."])
        self.assertEqual(output, "Giá $5 và $10, mã $123$.")
        self.assertEqual(speaker.calls, [])

    def test_escaped_and_incomplete_delimiters_are_preserved(self):
        output, speaker = extract(["Giữ \\$x$ và công thức dở $x+1"])
        self.assertEqual(output, "Giữ \\$x$ và công thức dở $x+1")
        self.assertEqual(speaker.calls, [])

    def test_sidecar_failure_preserves_original_formula(self):
        output, _ = extract(["A $x^2$ B"], FakeSpeaker(None))
        self.assertEqual(output, "A $x^2$ B")

    def test_trailing_backslash_can_form_delimiter_in_next_chunk(self):
        output, speaker = extract(["A \\", "(x+1\\", ") B"])
        self.assertEqual(output, "A CÔNG_THỨC B")
        self.assertEqual(speaker.calls[0][0], "x+1")

    def test_excessive_unclosed_formula_does_not_grow_forever(self):
        speaker = FakeSpeaker()
        extractor = StreamingMathExtractor(speaker)
        output = extractor.feed("$" + ("x" * (extractor.MAX_HOLD + 1)))
        output += extractor.flush()
        self.assertTrue(output.startswith("$"))
        self.assertEqual(len(output), extractor.MAX_HOLD + 2)
        self.assertEqual(speaker.calls, [])


if __name__ == "__main__":
    unittest.main()
