import unittest

from core.utils.math_speech_client import MathSpeechClient


class FakeResponse:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return {"ok": bool(self.text), "text": self.text or ""}


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json):
        self.calls.append((url, json))
        return self.responses.pop(0)


class MathSpeechClientTests(unittest.TestCase):
    def test_disabled_client_never_calls_http(self):
        http = FakeHTTP([])
        client = MathSpeechClient(enabled=False, http_client=http)
        self.assertIsNone(client.speak("x^2"))
        self.assertEqual(http.calls, [])

    def test_success_uses_expected_contract(self):
        http = FakeHTTP([FakeResponse("ích mũ hai")])
        client = MathSpeechClient(
            base_url="http://sidecar:8100/",
            enabled=True,
            http_client=http,
        )
        self.assertEqual(client.speak("x^2"), "ích mũ hai")
        self.assertEqual(
            http.calls,
            [("http://sidecar:8100/speak", {"latex": "x^2"})],
        )

    def test_circuit_breaker_skips_calls_then_recovers(self):
        now = [100.0]
        http = FakeHTTP(
            [
                FakeResponse(error=RuntimeError("down")),
                FakeResponse(error=RuntimeError("still down")),
                FakeResponse("đã hồi phục"),
            ]
        )
        client = MathSpeechClient(
            enabled=True,
            failure_threshold=2,
            cooldown_seconds=30,
            http_client=http,
            clock=lambda: now[0],
        )
        self.assertIsNone(client.speak("x"))
        self.assertIsNone(client.speak("x"))
        self.assertIsNone(client.speak("x"))
        self.assertEqual(len(http.calls), 2)

        now[0] += 31
        self.assertEqual(client.speak("x"), "đã hồi phục")
        self.assertEqual(len(http.calls), 3)


if __name__ == "__main__":
    unittest.main()
