import time
import os
import numpy as np
import opuslib_next
import onnxruntime
from config.logger import setup_logging
from core.providers.vad.base import VADProviderBase

TAG = __name__
logger = setup_logging()
VAD_DIAGNOSTIC_INITIAL_PACKETS = 50
VAD_DIAGNOSTIC_INTERVAL_PACKETS = 25


def _should_log_vad_diagnostics(conn):
    """Bound VAD diagnostics without changing inference or state transitions."""
    packet_index = getattr(conn, "_vad_diagnostic_packet_count", 0) + 1
    conn._vad_diagnostic_packet_count = packet_index
    should_log = (
        packet_index <= VAD_DIAGNOSTIC_INITIAL_PACKETS
        or packet_index % VAD_DIAGNOSTIC_INTERVAL_PACKETS == 0
    )
    conn._vad_diagnostic_log_this_packet = should_log
    return packet_index, should_log


def _pcm_metrics(samples):
    """Return aggregate PCM metrics only; never retain or log raw audio."""
    if samples.size == 0:
        return {
            "samples": 0,
            "minimum": 0,
            "maximum": 0,
            "peak": 0,
            "rms": 0.0,
            "non_zero_ratio": 0.0,
        }

    samples_i32 = samples.astype(np.int32)
    return {
        "samples": int(samples.size),
        "minimum": int(samples.min()),
        "maximum": int(samples.max()),
        "peak": int(np.abs(samples_i32).max()),
        "rms": float(np.sqrt(np.mean(samples_i32.astype(np.float64) ** 2))),
        "non_zero_ratio": float(np.count_nonzero(samples_i32) / samples_i32.size),
    }


class VADProvider(VADProviderBase):
    def __init__(self, config):
        logger.bind(tag=TAG).info("SileroVAD", config)

        model_path = os.path.join(
            config["model_dir"], "src", "silero_vad", "data", "silero_vad.onnx"
        )
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(
            model_path, providers=["CPUExecutionProvider"], sess_options=opts
        )

        threshold = config.get("threshold", "0.5")
        threshold_low = config.get("threshold_low", "0.2")
        min_silence_duration_ms = config.get("min_silence_duration_ms", "1000")

        self.vad_threshold = float(threshold) if threshold else 0.5
        self.vad_threshold_low = float(threshold_low) if threshold_low else 0.2

        self.silence_threshold_ms = (
            int(min_silence_duration_ms) if min_silence_duration_ms else 1000
        )

        self.frame_window_threshold = 3

    def _init_connection_state(self, conn):
        """为连接初始化独立的 VAD 状态"""
        if not hasattr(conn, "_vad_opus_decoder"):
            conn._vad_opus_decoder = opuslib_next.Decoder(16000, 1)
        if not hasattr(conn, "_vad_state"):
            conn._vad_state = np.zeros((2, 1, 128), dtype=np.float32)
        if not hasattr(conn, "_vad_context"):
            conn._vad_context = np.zeros((1, 64), dtype=np.float32)

    def release_conn_resources(self, conn):
        """释放连接的 VAD 资源（连接关闭时调用）"""
        for attr in ("_vad_opus_decoder", "_vad_state", "_vad_context"):
            if hasattr(conn, attr):
                try:
                    delattr(conn, attr)
                except Exception:
                    pass

    def is_vad(self, conn, opus_packet):
        # 手动模式：直接返回True，不进行实时VAD检测，所有音频都缓存
        if conn.client_listen_mode == "manual":
            return True

        try:
            self._init_connection_state(conn)
            packet_index, log_diagnostics = _should_log_vad_diagnostics(conn)

            pcm_frame = conn._vad_opus_decoder.decode(opus_packet, 960)
            conn.client_audio_buffer.extend(pcm_frame)
            decoded_pcm = np.frombuffer(pcm_frame, dtype=np.int16)
            decoded_metrics = _pcm_metrics(decoded_pcm)
            if log_diagnostics:
                conn.logger.bind(tag=TAG).info(
                    "[VAD-DIAG] decoded packet={} opus_bytes={} pcm_bytes={} "
                    "pcm_samples={} pcm_min={} pcm_max={} pcm_peak={} pcm_rms={:.2f} "
                    "non_zero_ratio={:.4f} pending_pcm_bytes={}",
                    packet_index,
                    len(opus_packet),
                    len(pcm_frame),
                    decoded_metrics["samples"],
                    decoded_metrics["minimum"],
                    decoded_metrics["maximum"],
                    decoded_metrics["peak"],
                    decoded_metrics["rms"],
                    decoded_metrics["non_zero_ratio"],
                    len(conn.client_audio_buffer),
                )

            client_have_voice = False
            vad_window_index = 0
            while len(conn.client_audio_buffer) >= 512 * 2:
                vad_window_index += 1
                chunk = conn.client_audio_buffer[: 512 * 2]
                conn.client_audio_buffer = conn.client_audio_buffer[512 * 2 :]

                audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                pcm_metrics = _pcm_metrics(audio_int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0
                audio_input = np.concatenate(
                    [conn._vad_context, audio_float32.reshape(1, -1)], axis=1
                ).astype(np.float32)

                ort_inputs = {
                    "input": audio_input,
                    "state": conn._vad_state,
                    "sr": np.array(16000, dtype=np.int64),
                }
                out, state = self.session.run(None, ort_inputs)

                conn._vad_state = state
                conn._vad_context = audio_input[:, -64:]
                speech_prob = out.item()
                session_have_voice_before = conn.client_have_voice

                # 双阈值判断
                if speech_prob >= self.vad_threshold:
                    is_voice = True
                elif speech_prob <= self.vad_threshold_low:
                    is_voice = False
                else:
                    is_voice = conn.last_is_voice

                # 声音没低于最低值则延续前一个状态，判断为有声音
                conn.last_is_voice = is_voice

                # 更新滑动窗口
                conn.client_voice_window.append(is_voice)
                client_have_voice = (
                    conn.client_voice_window.count(True) >= self.frame_window_threshold
                )

                # 如果之前有声音，但本次没有声音，且与上次有声音的时间差已经超过了静默阈值，则认为已经说完一句话
                if conn.client_have_voice and not client_have_voice:
                    stop_duration = time.time() * 1000 - conn.last_activity_time
                    if stop_duration >= self.silence_threshold_ms:
                        conn.client_voice_stop = True
                if client_have_voice:
                    conn.client_have_voice = True
                    conn.last_activity_time = time.time() * 1000

                positive_count = conn.client_voice_window.count(True)
                negative_count = conn.client_voice_window.count(False)
                state_changed = session_have_voice_before != conn.client_have_voice
                if log_diagnostics or state_changed or conn.client_voice_stop:
                    conn.logger.bind(tag=TAG).info(
                        "[VAD-DIAG] window packet={} index={} vad_input_samples={} "
                        "pcm_min={} pcm_max={} pcm_peak={} pcm_rms={:.2f} non_zero_ratio={:.4f} "
                        "speech_prob={:.4f} threshold_high={:.2f} threshold_low={:.2f} "
                        "raw_is_voice={} rolling_positive={} rolling_negative={} rolling_size={} "
                        "have_voice_return={} session_have_voice_before={} "
                        "session_have_voice_after={} voice_stop={} pending_pcm_bytes={}",
                        packet_index,
                        vad_window_index,
                        pcm_metrics["samples"],
                        pcm_metrics["minimum"],
                        pcm_metrics["maximum"],
                        pcm_metrics["peak"],
                        pcm_metrics["rms"],
                        pcm_metrics["non_zero_ratio"],
                        speech_prob,
                        self.vad_threshold,
                        self.vad_threshold_low,
                        is_voice,
                        positive_count,
                        negative_count,
                        len(conn.client_voice_window),
                        client_have_voice,
                        session_have_voice_before,
                        conn.client_have_voice,
                        conn.client_voice_stop,
                        len(conn.client_audio_buffer),
                    )

            if log_diagnostics and vad_window_index == 0:
                conn.logger.bind(tag=TAG).info(
                    "[VAD-DIAG] no_complete_window packet={} pending_pcm_bytes={}",
                    packet_index,
                    len(conn.client_audio_buffer),
                )

            return client_have_voice
        except opuslib_next.OpusError as e:
            logger.bind(tag=TAG).info(f"解码错误: {e}")
        except Exception as e:
            logger.bind(tag=TAG).error(f"Error processing audio packet: {e}")
