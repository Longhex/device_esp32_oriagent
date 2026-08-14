import unittest
from unittest.mock import patch

from core.providers.tts.oriagent_voice import (
    CONTINUOUS_JITTER_MS,
    INITIAL_BUFFER_MS,
    TTSProvider,
)


class FakeConn:
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.client_abort = False


def make_provider(**overrides):
    config = {"api_url": "https://studio.evomlabs.com/api/v1", "api_key": "vc_sk_live_x"}
    config.update(overrides)
    with patch.object(TTSProvider, "__init__", TTSProvider.__init__):
        return TTSProvider(config, delete_audio_file=True)


class BufferSizingTests(unittest.TestCase):
    """Buffer phải là một khoảng THỜI GIAN cố định, không phải số byte cố định."""

    def _sized(self, rate):
        p = make_provider()
        p.conn = FakeConn(rate)
        bytes_per_ms = rate * 2 / 1000
        p._initial_buffer_bytes = max(2, int(bytes_per_ms * INITIAL_BUFFER_MS))
        p._continuous_jitter_bytes = max(2, int(bytes_per_ms * CONTINUOUS_JITTER_MS))
        p._lead_in_bytes = max(0, int(bytes_per_ms * p.lead_in_silence_ms))
        return p

    def test_initial_buffer_is_same_duration_at_both_rates(self):
        for rate in (16000, 24000):
            p = self._sized(rate)
            ms = p._initial_buffer_bytes / (rate * 2 / 1000)
            self.assertAlmostEqual(ms, INITIAL_BUFFER_MS, delta=1)

    def test_lead_in_is_same_duration_at_both_rates(self):
        for rate in (16000, 24000):
            p = self._sized(rate)
            ms = p._lead_in_bytes / (rate * 2 / 1000)
            self.assertAlmostEqual(ms, p.lead_in_silence_ms, delta=1)

    def test_byte_counts_actually_differ_between_rates(self):
        # Nếu hai rate cho cùng số byte thì tức là vẫn đang hard-code byte.
        self.assertNotEqual(
            self._sized(16000)._initial_buffer_bytes,
            self._sized(24000)._initial_buffer_bytes,
        )


class ResampleTests(unittest.TestCase):
    def _provider(self, device_rate):
        p = make_provider()
        p.conn = FakeConn(device_rate)
        p._resample_state = None
        p._resample_carry = b""
        return p

    def test_passthrough_when_rates_match(self):
        p = self._provider(24000)
        pcm = b"\x01\x02" * 100
        self.assertIs(p._to_device_rate(pcm, 24000), pcm)

    def test_downsample_24k_to_16k_shrinks_by_two_thirds(self):
        p = self._provider(16000)
        # 24000 sample = 1 giây @24k -> phải ra ~16000 sample @16k
        pcm = b"\x00\x00" * 24000
        out = p._to_device_rate(pcm, 24000)
        self.assertAlmostEqual(len(out) / 2, 16000, delta=50)

    def test_streaming_in_chunks_matches_single_shot_length(self):
        """Chia nhỏ chunk phải cho tổng độ dài như xử lý một lần — bằng chứng state
        được mang qua chunk chứ không reset (reset sẽ làm lệch số sample)."""
        pcm = bytes(range(256)) * 40  # 10240 byte, chẵn
        single = self._provider(16000)._to_device_rate(pcm, 24000)

        chunked = self._provider(16000)
        out = b"".join(
            chunked._to_device_rate(pcm[i:i + 512], 24000)
            for i in range(0, len(pcm), 512)
        )
        self.assertAlmostEqual(len(out), len(single), delta=8)

    def test_odd_length_chunk_does_not_break_frame_alignment(self):
        p = self._provider(16000)
        out = p._to_device_rate(b"\x01\x02\x03", 24000)  # 3 byte -> lẻ
        self.assertEqual(len(out) % 2, 0)
        self.assertEqual(p._resample_carry, b"\x03")

    def test_carry_byte_is_consumed_by_next_chunk(self):
        p = self._provider(16000)
        p._to_device_rate(b"\x01\x02\x03", 24000)   # dư \x03
        self.assertEqual(p._resample_carry, b"\x03")
        # Tổng 3+3=6 byte là chẵn -> byte dư phải được tiêu thụ hết.
        p._to_device_rate(b"\x04\x05\x06", 24000)
        self.assertEqual(p._resample_carry, b"")

    def test_no_sample_is_lost_across_odd_chunks(self):
        """Tổng sample ra phải khớp với xử lý một lần, dù mọi chunk đều lẻ byte."""
        pcm = bytes(range(256)) * 8  # 2048 byte
        single = self._provider(16000)._to_device_rate(pcm, 24000)

        p = self._provider(16000)
        out = b"".join(
            p._to_device_rate(pcm[i:i + 511], 24000)  # 511 = lẻ
            for i in range(0, len(pcm), 511)
        )
        self.assertAlmostEqual(len(out), len(single), delta=8)


class StartMessageTests(unittest.TestCase):
    def test_quality_fields_default_on(self):
        p = make_provider()
        self.assertTrue(p.do_normalize)
        self.assertTrue(p.denoise)
        self.assertTrue(p.preprocess_prompt)
        self.assertTrue(p.postprocess_output)

    def test_quality_fields_can_be_disabled(self):
        p = make_provider(do_normalize=False, denoise=False)
        self.assertFalse(p.do_normalize)
        self.assertFalse(p.denoise)

    def test_speed_clamped_to_documented_range(self):
        self.assertEqual(make_provider(speed=9.0).speed, 1.5)
        self.assertEqual(make_provider(speed=0.1).speed, 0.5)
        self.assertEqual(make_provider(speed=1.2).speed, 1.2)

    def test_invalid_speed_falls_back_to_one(self):
        self.assertEqual(make_provider(speed="nhanh").speed, 1.0)


if __name__ == "__main__":
    unittest.main()
