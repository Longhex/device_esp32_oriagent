import os
import sys
import time
import unittest
from collections import deque
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.providers.vad.silero import VADProvider  # noqa: E402


class FakeLogger:
    def __init__(self):
        self.events = []

    def bind(self, **_kwargs):
        return self

    def debug(self, message, *_args, **_kwargs):
        self.events.append(message)

    info = debug
    warning = debug

    def exception(self, message, *_args, **_kwargs):
        self.events.append(message)


class FakeDecoder:
    def decode(self, _packet, _samples):
        # One 512-sample / 32 ms PCM block, matching the VAD implementation.
        return b"\x00" * 1024


class FakeSession:
    def __init__(self, probabilities):
        self.probabilities = iter(probabilities)

    def run(self, _outputs, _inputs):
        import numpy as np

        return np.array([next(self.probabilities)], dtype=np.float32), np.zeros(
            (2, 1, 128), dtype=np.float32
        )


def make_provider(probabilities, silence_ms=1):
    provider = VADProvider.__new__(VADProvider)
    provider.session = FakeSession(probabilities)
    provider.vad_threshold = 0.5
    provider.vad_threshold_low = 0.3
    provider.silence_threshold_ms = silence_ms
    provider.frame_window_threshold = 3
    provider.window_size = 5
    provider.debug_log = True
    provider.debug_sample_every = 1
    provider.packet_gap_warning_ms = 150
    provider.stuck_voice_warning_ms = 10000
    return provider


def make_connection():
    return SimpleNamespace(
        device_id="device-test",
        session_id="session-test",
        client_listen_mode="auto",
        client_audio_buffer=bytearray(),
        client_voice_window=deque(maxlen=5),
        last_is_voice=False,
        client_have_voice=False,
        client_voice_stop=False,
        last_activity_time=time.time() * 1000,
        _vad_opus_decoder=FakeDecoder(),
        logger=FakeLogger(),
    )


class VADDiagnosticsTest(unittest.TestCase):
    def assert_logged(self, conn, marker):
        self.assertTrue(any(marker in event for event in conn.logger.events), marker)

    def test_high_low_hold_and_window_transitions_are_recorded(self):
        # Three HIGH blocks start speech; HOLD preserves the previous HIGH
        # decision; following LOW blocks drain the 5-block window and stop.
        provider = make_provider(
            [0.8, 0.8, 0.8, 0.4, 0.1, 0.1, 0.1, 0.1], silence_ms=0
        )
        conn = make_connection()
        for sequence in range(1, 9):
            provider.is_vad(conn, b"opus", {"sequence": sequence})

        self.assertTrue(conn.client_voice_stop)
        self.assertIn("utterance_id", conn._vad_last_completed_metrics)
        self.assertGreater(conn._vad_last_completed_metrics["processed_blocks"], 0)
        self.assert_logged(conn, "[VAD_VOICE_STARTED]")
        self.assert_logged(conn, "[VAD_STOP_CANDIDATE]")
        self.assert_logged(conn, "[VAD_VOICE_STOPPED]")
        self.assert_logged(conn, "[VAD_BLOCK]")

    def test_packet_gap_is_warned_without_logging_audio_data(self):
        provider = make_provider([0.1])
        conn = make_connection()
        provider._init_connection_state(conn)
        conn._vad_last_packet_monotonic = time.monotonic() - 0.2

        provider._log_packet(
            conn, {"sequence": 9}, 123, 1.5, 960, 1, 0, 0
        )

        self.assert_logged(conn, "[VAD_PACKET_GAP]")
        self.assert_logged(conn, "[VAD_PACKET]")
        self.assertNotIn("opus", " ".join(conn.logger.events))


if __name__ == "__main__":
    unittest.main()
