import os
import time
import uuid

import numpy as np
import onnxruntime
import opuslib_next

from config.logger import setup_logging
from core.providers.vad.base import VADProviderBase

TAG = __name__
logger = setup_logging()


def _env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class VADProvider(VADProviderBase):
    def __init__(self, config):
        model_path = os.path.join(config["model_dir"], "src", "silero_vad", "data", "silero_vad.onnx")
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(model_path, providers=["CPUExecutionProvider"], sess_options=opts)
        self.vad_threshold = float(config.get("threshold", "0.5") or 0.5)
        self.vad_threshold_low = float(config.get("threshold_low", "0.2") or 0.2)
        self.silence_threshold_ms = int(config.get("min_silence_duration_ms", "1000") or 1000)
        self.frame_window_threshold = 3
        self.window_size = 5
        self.debug_log = _env_bool("VAD_DEBUG_LOG")
        self.debug_sample_every = max(1, int(os.getenv("VAD_DEBUG_SAMPLE_EVERY_N_BLOCKS", "1")))
        self.packet_gap_warning_ms = max(1, int(os.getenv("VAD_PACKET_GAP_WARNING_MS", "150")))
        self.stuck_voice_warning_ms = max(1, int(os.getenv("VAD_STUCK_VOICE_WARNING_MS", "10000")))
        logger.bind(tag=TAG, phase="VAD").info(
            "[VAD_CONFIG] sample_rate=16000 opus_frame_ms=60 block_samples=512 block_ms=32 "
            "threshold={} threshold_low={} window_size={} required_voice_blocks={} min_silence_ms={} "
            "debug={} debug_sample_every={} packet_gap_warning_ms={} stuck_voice_warning_ms={}",
            self.vad_threshold, self.vad_threshold_low, self.window_size, self.frame_window_threshold,
            self.silence_threshold_ms, self.debug_log, self.debug_sample_every,
            self.packet_gap_warning_ms, self.stuck_voice_warning_ms,
        )

    def _init_connection_state(self, conn):
        if not hasattr(conn, "_vad_opus_decoder"):
            conn._vad_opus_decoder = opuslib_next.Decoder(16000, 1)
        if not hasattr(conn, "_vad_state"):
            conn._vad_state = np.zeros((2, 1, 128), dtype=np.float32)
        if not hasattr(conn, "_vad_context"):
            conn._vad_context = np.zeros((1, 64), dtype=np.float32)
        if not hasattr(conn, "_vad_block_index"):
            conn._vad_block_index = 0
            conn._vad_packet_count = 0
            conn._vad_silence_audio_ms = 0
            conn._vad_last_packet_monotonic = None
            conn._vad_utterance_id = None
            conn._vad_utterance_started_monotonic = None
            conn._vad_last_stuck_warning_monotonic = 0.0
            conn._vad_hold_blocks = 0
            conn._vad_previous_window_voice = False

    @staticmethod
    def _window(conn):
        return "[{}]".format(",".join("1" if value else "0" for value in conn.client_voice_window))

    @staticmethod
    def _context(conn):
        return "device={} session={}".format(conn.device_id or "-", conn.session_id or "-")

    def release_conn_resources(self, conn):
        for attr in ("_vad_opus_decoder", "_vad_state", "_vad_context"):
            if hasattr(conn, attr):
                delattr(conn, attr)

    def _log_packet(self, conn, packet_meta, packet_bytes, decode_ms, decoded_samples, blocks, before, after):
        processed_monotonic = time.monotonic()
        now = packet_meta.get("received_monotonic", processed_monotonic) if packet_meta else processed_monotonic
        previous = conn._vad_last_packet_monotonic
        gap_ms = (now - previous) * 1000 if previous is not None else 0.0
        queue_delay_ms = max(0.0, (processed_monotonic - now) * 1000)
        conn._vad_last_packet_monotonic = now
        conn._vad_packet_count += 1
        seq = packet_meta.get("sequence", "-") if packet_meta else "-"
        utterance_id = conn._vad_utterance_id or "-"
        if previous is not None and gap_ms > self.packet_gap_warning_ms:
            conn.logger.bind(tag=TAG, phase="VAD").warning(
                "[VAD_PACKET_GAP] {} utterance_id={} seq={} gap_ms={:.3f} expected_ms=60 "
                "client_have_voice={} buffer_bytes={}",
                self._context(conn), utterance_id, seq, gap_ms, conn.client_have_voice, after,
            )
        if self.debug_log:
            conn.logger.bind(tag=TAG, phase="VAD").debug(
                "[VAD_PACKET] {} utterance_id={} seq={} packet_bytes={} packet_gap_ms={:.3f} "
                "queue_delay_ms={:.3f} decode_ms={:.3f} decoded_samples={} blocks_processed={} buffer_before_bytes={} buffer_after_bytes={}",
                self._context(conn), utterance_id, seq, packet_bytes, gap_ms, queue_delay_ms, decode_ms,
                decoded_samples, blocks, before, after,
            )

    def is_vad(self, conn, opus_packet, packet_meta=None):
        if conn.client_listen_mode == "manual":
            return True
        self._init_connection_state(conn)
        buffer_before = len(conn.client_audio_buffer)
        decode_started = time.perf_counter()
        try:
            pcm_frame = conn._vad_opus_decoder.decode(opus_packet, 960)
        except opuslib_next.OpusError:
            conn.logger.bind(tag=TAG, phase="VAD").exception(
                "[VAD_OPUS_DECODE_ERROR] {} utterance_id={} packet_bytes={}",
                self._context(conn), conn._vad_utterance_id or "-", len(opus_packet),
            )
            return False
        decode_ms = (time.perf_counter() - decode_started) * 1000
        conn.client_audio_buffer.extend(pcm_frame)
        blocks_processed = 0
        client_have_voice = False
        try:
            while len(conn.client_audio_buffer) >= 1024:
                chunk = conn.client_audio_buffer[:1024]
                conn.client_audio_buffer = conn.client_audio_buffer[1024:]
                previous_raw_voice = conn.last_is_voice
                previous_client_have_voice = conn._vad_previous_window_voice
                inference_started = time.perf_counter()
                audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                audio_input = np.concatenate([conn._vad_context, (audio_int16.astype(np.float32) / 32768.0).reshape(1, -1)], axis=1).astype(np.float32)
                out, state = self.session.run(None, {"input": audio_input, "state": conn._vad_state, "sr": np.array(16000, dtype=np.int64)})
                inference_ms = (time.perf_counter() - inference_started) * 1000
                conn._vad_state, conn._vad_context = state, audio_input[:, -64:]
                speech_prob = out.item()
                if speech_prob >= self.vad_threshold:
                    raw_is_voice, region = True, "HIGH"
                elif speech_prob <= self.vad_threshold_low:
                    raw_is_voice, region = False, "LOW"
                else:
                    raw_is_voice, region = previous_raw_voice, "HOLD"
                conn.last_is_voice = raw_is_voice
                conn.client_voice_window.append(raw_is_voice)
                client_have_voice = conn.client_voice_window.count(True) >= self.frame_window_threshold
                conn._vad_previous_window_voice = client_have_voice
                now_wall_ms = time.time() * 1000
                now_monotonic = time.monotonic()
                if region == "HOLD":
                    conn._vad_hold_blocks += 1
                else:
                    conn._vad_hold_blocks = 0
                if client_have_voice:
                    reset_reason = "HIGH" if region == "HIGH" else ("HOLD" if region == "HOLD" else "WINDOW")
                    previous_silence_ms = max(0.0, now_wall_ms - conn.last_activity_time)
                    conn.client_have_voice = True
                    conn.last_activity_time = now_wall_ms
                    conn._vad_silence_audio_ms = 0
                    if not previous_client_have_voice:
                        conn._vad_utterance_id = uuid.uuid4().hex[:10]
                        conn._vad_utterance_started_monotonic = now_monotonic
                        conn._vad_packet_count = 0
                        conn.logger.bind(tag=TAG, phase="VAD").info(
                            "[VAD_VOICE_STARTED] {} utterance_id={} speech_prob={:.3f} window={} voice_count={}",
                            self._context(conn), conn._vad_utterance_id, speech_prob, self._window(conn), conn.client_voice_window.count(True),
                        )
                    elif previous_raw_voice is False and raw_is_voice:
                        conn.logger.bind(tag=TAG, phase="VAD").info(
                            "[VAD_VOICE_RESUMED] {} utterance_id={} speech_prob={:.3f} previous_silence_ms={:.3f} reason={}",
                            self._context(conn), conn._vad_utterance_id or "-", speech_prob,
                            previous_silence_ms, reset_reason,
                        )
                else:
                    conn._vad_silence_audio_ms += 32
                    silence_elapsed_ms = max(0.0, now_wall_ms - conn.last_activity_time) if conn.client_have_voice else 0.0
                    if previous_client_have_voice:
                        conn.logger.bind(tag=TAG, phase="VAD").info(
                            "[VAD_STOP_CANDIDATE] {} utterance_id={} speech_prob={:.3f} window={} silence_elapsed_ms={:.3f} required_silence_ms={}",
                            self._context(conn), conn._vad_utterance_id or "-", speech_prob, self._window(conn), silence_elapsed_ms, self.silence_threshold_ms,
                        )
                    if (
                        conn.client_have_voice
                        and not conn.client_voice_stop
                        and silence_elapsed_ms >= self.silence_threshold_ms
                    ):
                        conn.client_voice_stop = True
                        conn._vad_voice_stop_monotonic = now_monotonic
                        duration_ms = (now_monotonic - conn._vad_utterance_started_monotonic) * 1000 if conn._vad_utterance_started_monotonic else 0.0
                        conn._vad_last_completed_metrics = {"utterance_id": conn._vad_utterance_id or "-", "voice_stop_monotonic": now_monotonic, "silence_audio_ms": conn._vad_silence_audio_ms, "utterance_duration_ms": duration_ms, "received_packets": conn._vad_packet_count + 1, "processed_blocks": conn._vad_block_index + 1}
                        conn.logger.bind(tag=TAG, phase="VAD").info(
                            "[VAD_VOICE_STOPPED] {} utterance_id={} silence_elapsed_ms={:.3f} silence_audio_ms={} required_silence_ms={} utterance_duration_ms={:.3f} received_packets={} processed_blocks={} trigger_asr=true",
                            self._context(conn), conn._vad_utterance_id or "-", silence_elapsed_ms, conn._vad_silence_audio_ms, self.silence_threshold_ms, duration_ms, conn._vad_packet_count + 1, conn._vad_block_index + 1,
                        )
                if conn.client_have_voice and conn._vad_utterance_started_monotonic and (now_monotonic - conn._vad_utterance_started_monotonic) * 1000 >= self.stuck_voice_warning_ms and now_monotonic - conn._vad_last_stuck_warning_monotonic >= self.stuck_voice_warning_ms / 1000:
                    conn._vad_last_stuck_warning_monotonic = now_monotonic
                    conn.logger.bind(tag=TAG, phase="VAD").warning(
                        "[VAD_STUCK_VOICE] {} utterance_id={} voice_duration_ms={:.3f} speech_prob={:.3f} threshold_region={} hold_blocks={} last_activity_reset={}",
                        self._context(conn), conn._vad_utterance_id or "-", (now_monotonic - conn._vad_utterance_started_monotonic) * 1000, speech_prob, region, conn._vad_hold_blocks, client_have_voice,
                    )
                conn._vad_block_index += 1
                blocks_processed += 1
                if self.debug_log and conn._vad_block_index % self.debug_sample_every == 0:
                    silence_elapsed_ms = max(0.0, now_wall_ms - conn.last_activity_time) if conn.client_have_voice else 0.0
                    conn.logger.bind(tag=TAG, phase="VAD").debug(
                        "[VAD_BLOCK] {} utterance_id={} block_index={} speech_prob={:.3f} threshold_region={} previous_raw_voice={} raw_is_voice={} window={} voice_count={} required_count={} client_have_voice={} previous_client_have_voice={} silence_elapsed_ms={:.3f} silence_audio_ms={} inference_ms={:.3f} buffer_remaining_bytes={}",
                        self._context(conn), conn._vad_utterance_id or "-", conn._vad_block_index, speech_prob, region, previous_raw_voice, raw_is_voice, self._window(conn), conn.client_voice_window.count(True), self.frame_window_threshold, client_have_voice, previous_client_have_voice, silence_elapsed_ms, conn._vad_silence_audio_ms, inference_ms, len(conn.client_audio_buffer),
                    )
            self._log_packet(conn, packet_meta or {}, len(opus_packet), decode_ms, len(pcm_frame) // 2, blocks_processed, buffer_before, len(conn.client_audio_buffer))
            return client_have_voice
        except (AttributeError, ValueError):
            conn.logger.bind(tag=TAG, phase="VAD").exception(
                "[VAD_STATE_ERROR] {} utterance_id={} block_index={}", self._context(conn), conn._vad_utterance_id or "-", conn._vad_block_index,
            )
            return False
        except Exception:
            conn.logger.bind(tag=TAG, phase="VAD").exception(
                "[VAD_INFERENCE_ERROR] {} utterance_id={} block_index={}", self._context(conn), conn._vad_utterance_id or "-", conn._vad_block_index,
            )
            return False
