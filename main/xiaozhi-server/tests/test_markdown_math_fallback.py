import unittest
import sys
import types


class _SilentLogger:
    def debug(self, *_args, **_kwargs):
        pass


# Keep this focused unit test runnable without installing the full server stack.
_original_logger_module = sys.modules.get("config.logger")
_logger_stub = types.ModuleType("config.logger")
_logger_stub.setup_logging = lambda: _SilentLogger()
sys.modules["config.logger"] = _logger_stub
try:
    from core.utils.tts import MarkdownCleaner
finally:
    if _original_logger_module is None:
        del sys.modules["config.logger"]
    else:
        sys.modules["config.logger"] = _original_logger_module


class MarkdownMathFallbackTests(unittest.TestCase):
    def test_formula_contents_are_not_deleted_when_sidecar_falls_back(self):
        cleaned = MarkdownCleaner.clean_markdown(
            "A $$x^2+1$$ B $y_1$ C \\(a+b\\) D \\[z=3\\]"
        )
        for content in ("x^2+1", "y_1", "a+b", "z=3"):
            self.assertIn(content, cleaned)

    def test_non_math_square_tags_are_still_removed(self):
        self.assertEqual(MarkdownCleaner.clean_markdown("xin [laugh] chào"), "xin chào")


if __name__ == "__main__":
    unittest.main()
