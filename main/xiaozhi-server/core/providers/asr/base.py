import os
import io
import wave
import uuid
import json
import time
import queue
import shutil
import asyncio
import tempfile
import traceback
import threading
import opuslib_next

from abc import ABC, abstractmethod
from config.logger import setup_logging
from core.providers.asr.dto.dto import InterfaceType
from core.handle.receiveAudioHandle import startToChat
from core.handle.reportHandle import enqueue_asr_report
from core.utils.util import remove_punctuation_and_length
from core.handle.receiveAudioHandle import handleAudioMessage
from core.udp_server import HYBRID_EOS_MARKER
from typing import Optional, Tuple, List, NamedTuple, TYPE_CHECKING


if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()


def _should_log_hybrid_asr_event(conn: "ConnectionHandler", event_name: str, interval: int = 25) -> bool:
    counters = getattr(conn, "_hybrid_asr_log_counters", None)
    if counters is None:
        counters = {}
        setattr(conn, "_hybrid_asr_log_counters", counters)

    count = counters.get(event_name, 0) + 1
    counters[event_name] = count
    return count == 1 or count % interval == 0


def _is_hybrid_control_message(message) -> bool:
    return isinstance(message, dict) and message.get("type") == HYBRID_EOS_MARKER


def _message_length(message) -> int:
    if isinstance(message, (bytes, bytearray)):
        return len(message)
    return 0


class ASRProviderBase(ABC):
    def __init__(self):
        pass

    async def open_audio_channels(self, conn: "ConnectionHandler"):
        existing_thread = getattr(conn, "asr_priority_thread", None)
        if existing_thread is not None and existing_thread.is_alive():
            conn.logger.bind(tag=TAG).info(
                "[HYBRID-ASR] asr_consumer_thread_already_running conn={} queue_id={}",
                id(conn),
                id(conn.asr_audio_queue),
            )
            return

        conn.logger.bind(tag=TAG).info(
            "[HYBRID-ASR] asr_consumer_thread_start conn={} queue_id={}",
            id(conn),
            id(conn.asr_audio_queue),
        )
        conn.asr_priority_thread = threading.Thread(
            target=self.asr_text_priority_thread, args=(conn,), daemon=True
        )
        conn.asr_priority_thread.start()

    def asr_text_priority_thread(self, conn: "ConnectionHandler"):
        if getattr(conn, "_hybrid_asr_wait_logged", False) is False:
            conn.logger.bind(tag=TAG).info(
                "[HYBRID-ASR] asr_queue_waiting conn={} queue_id={}",
                id(conn),
                id(conn.asr_audio_queue),
            )
            conn._hybrid_asr_wait_logged = True
        while not conn.stop_event.is_set():
            try:
                message = conn.asr_audio_queue.get(timeout=1)
                if _is_hybrid_control_message(message):
                    conn.logger.bind(tag=TAG).info(
                        "[HYBRID-EOS] queue_control device={} session={} marker={} buffered_frames={} listen_mode={}",
                        conn.device_id or "-",
                        conn.session_id or "-",
                        message.get("type"),
                        len(conn.asr_audio),
                        conn.client_listen_mode,
                    )
                    future = asyncio.run_coroutine_threadsafe(
                        self.handle_queue_control_message(conn, message),
                        conn.loop,
                    )
                    future.result()
                    continue
                if _should_log_hybrid_asr_event(conn, "queue_dequeue"):
                    conn.logger.bind(tag=TAG).info(
                        "[HYBRID-AUDIO] queue_dequeue device={} session={} chunk_len={} audio_format={}",
                        conn.device_id or "-",
                        conn.session_id or "-",
                        _message_length(message),
                        conn.audio_format,
                    )
                future = asyncio.run_coroutine_threadsafe(
                    handleAudioMessage(conn, message),
                    conn.loop,
                )
                future.result()
            except queue.Empty:
                continue
            except Exception as e:
                logger.bind(tag=TAG).error(
                    f"处理ASR文本失败: {str(e)}, 类型: {type(e).__name__}, 堆栈: {traceback.format_exc()}"
                )
                continue

    async def handle_queue_control_message(self, conn: "ConnectionHandler", message):
        if not _is_hybrid_control_message(message):
            return

        buffered_frames = len(conn.asr_audio)
        conn.client_voice_stop = True
        conn.logger.bind(tag=TAG).info(
            "[HYBRID-EOS] end_of_turn_signal device={} session={} buffered_frames={} client_have_voice={} listen_mode={}",
            conn.device_id or "-",
            conn.session_id or "-",
            buffered_frames,
            conn.client_have_voice,
            conn.client_listen_mode,
        )

        if conn.asr.interface_type == InterfaceType.STREAM:
            if hasattr(conn.asr, "_send_stop_request"):
                await conn.asr._send_stop_request()
            return

        if buffered_frames == 0:
            conn.logger.bind(tag=TAG).info(
                "[HYBRID-EOS] end_of_turn_ignored device={} session={} reason=no_buffered_audio",
                conn.device_id or "-",
                conn.session_id or "-",
            )
            return

        asr_audio_task = conn.asr_audio.copy()
        conn.reset_audio_states()
        conn.logger.bind(tag=TAG).info(
            "[HYBRID-ASR] eos_trigger_asr device={} session={} frames={} audio_format={}",
            conn.device_id or "-",
            conn.session_id or "-",
            len(asr_audio_task),
            conn.audio_format,
        )
        await self.handle_voice_stop(conn, asr_audio_task)

    async def receive_audio(self, conn: "ConnectionHandler", audio, audio_have_voice):
        if _should_log_hybrid_asr_event(conn, "receive_audio"):
            conn.logger.bind(tag=TAG).info(
                "[HYBRID-AUDIO] receive_audio device={} session={} chunk_len={} audio_format={} have_voice={} listen_mode={}",
                conn.device_id or "-",
                conn.session_id or "-",
                len(audio) if audio is not None else 0,
                conn.audio_format,
                audio_have_voice,
                conn.client_listen_mode,
            )

        if conn.client_listen_mode == "manual":
            conn.asr_audio.append(audio)
        else:
            pre_roll_before = len(conn.asr_audio)
            conn.asr_audio.append(audio)
            pre_roll_after_append = len(conn.asr_audio)
            trimmed_to_pre_roll = False

            if not audio_have_voice and not conn.client_have_voice:
                conn.asr_audio = conn.asr_audio[-10:]
                trimmed_to_pre_roll = True
                if getattr(conn, "_vad_diagnostic_log_this_packet", False):
                    conn.logger.bind(tag=TAG).info(
                        "[VAD-DIAG] pre_roll audio_have_voice={} session_have_voice={} "
                        "before_append={} after_append={} after_trim={} trimmed_to_ten={}",
                        audio_have_voice,
                        conn.client_have_voice,
                        pre_roll_before,
                        pre_roll_after_append,
                        len(conn.asr_audio),
                        trimmed_to_pre_roll,
                    )
                return

            if getattr(conn, "_vad_diagnostic_log_this_packet", False):
                conn.logger.bind(tag=TAG).info(
                    "[VAD-DIAG] pre_roll audio_have_voice={} session_have_voice={} "
                    "before_append={} after_append={} after_trim={} trimmed_to_ten={}",
                    audio_have_voice,
                    conn.client_have_voice,
                    pre_roll_before,
                    pre_roll_after_append,
                    len(conn.asr_audio),
                    trimmed_to_pre_roll,
                )

            if conn.asr.interface_type != InterfaceType.STREAM and conn.client_voice_stop:
                asr_audio_task = conn.asr_audio.copy()
                conn.reset_audio_states()

                if len(asr_audio_task) > 15:
                    conn.logger.bind(tag=TAG).info(
                        "[HYBRID-AUDIO] vad_voice_stop trigger_asr device={} session={} frames={} audio_format={}",
                        conn.device_id or "-",
                        conn.session_id or "-",
                        len(asr_audio_task),
                        conn.audio_format,
                    )
                    await self.handle_voice_stop(conn, asr_audio_task)

    async def handle_voice_stop(self, conn: "ConnectionHandler", asr_audio_task: List[bytes]):
        llm = getattr(conn, "llm", None)
        if llm is not None and hasattr(llm, "_warmup_pool"):
            threading.Thread(
                target=llm._warmup_pool, name="llm-parallel-warmup", daemon=True,
            ).start()

        try:
            total_start_time = time.monotonic()
            conn.logger.bind(tag=TAG, phase="ASR").info(
                f"ASR start: frames={len(asr_audio_task)} format={conn.audio_format}"
            )
            conn.logger.bind(tag=TAG).info(
                "[HYBRID-ASR] asr_start device={} session={} audio_format={} chunks={}",
                conn.device_id or "-",
                conn.session_id or "-",
                conn.audio_format,
                len(asr_audio_task),
            )

            if conn.audio_format == "pcm":
                pcm_data = asr_audio_task
            else:
                conn.logger.bind(tag=TAG).info(
                    "[HYBRID-ASR] opus_decode_start device={} session={} chunks={}",
                    conn.device_id or "-",
                    conn.session_id or "-",
                    len(asr_audio_task),
                )
                pcm_data = self.decode_opus(asr_audio_task)

            combined_pcm_data = b"".join(pcm_data)
            conn.logger.bind(tag=TAG).info(
                "[HYBRID-ASR] opus_decode_done device={} session={} pcm_frames={} pcm_len={}",
                conn.device_id or "-",
                conn.session_id or "-",
                len(pcm_data),
                len(combined_pcm_data),
            )

            wav_data = None
            if conn.voiceprint_provider and combined_pcm_data:
                wav_data = self._pcm_to_wav(combined_pcm_data)

            conn.logger.bind(tag=TAG).info(
                "[HYBRID-ASR] provider_start device={} session={} provider={} audio_format={}",
                conn.device_id or "-",
                conn.session_id or "-",
                type(self).__name__,
                conn.audio_format,
            )
            asr_task = self.speech_to_text_wrapper(
                asr_audio_task, conn.session_id, conn.audio_format
            )

            if conn.voiceprint_provider and wav_data:
                voiceprint_task = conn.voiceprint_provider.identify_speaker(
                    wav_data, conn.session_id
                )
                asr_result, voiceprint_result = await asyncio.gather(
                    asr_task, voiceprint_task, return_exceptions=True
                )
            else:
                asr_result = await asr_task
                voiceprint_result = None

            result_text = ""
            if isinstance(asr_result, tuple) and asr_result:
                raw_candidate = asr_result[0]
                if isinstance(raw_candidate, dict):
                    result_text = raw_candidate.get("content", "")
                elif isinstance(raw_candidate, str):
                    result_text = raw_candidate
            conn.logger.bind(tag=TAG).info(
                "[HYBRID-ASR] provider_done device={} session={} provider={} text_len={}",
                conn.device_id or "-",
                conn.session_id or "-",
                type(self).__name__,
                len(result_text) if result_text else 0,
            )

            if isinstance(asr_result, Exception):
                logger.bind(tag=TAG).error(f"ASR识别失败: {asr_result}")
                raw_text = ""
            else:
                raw_text, _ = asr_result

            if isinstance(voiceprint_result, Exception):
                logger.bind(tag=TAG).error(f"声纹识别失败: {voiceprint_result}")
                speaker_name = ""
            else:
                speaker_name = voiceprint_result

            if isinstance(raw_text, dict):
                if speaker_name:
                    raw_text["speaker"] = speaker_name

                if raw_text.get("language"):
                    logger.bind(tag=TAG).info(f"识别语言: {raw_text['language']}")
                if raw_text.get("emotion"):
                    logger.bind(tag=TAG).info(f"识别情绪: {raw_text['emotion']}")
                if raw_text.get("content"):
                    conn.logger.bind(tag=TAG, phase="ASR").info(
                        f"ASR text: {raw_text['content']}"
                    )
                if speaker_name:
                    logger.bind(tag=TAG).info(f"识别说话人: {speaker_name}")

                enhanced_text = json.dumps(raw_text, ensure_ascii=False)
                content_for_length_check = raw_text.get("content", "")
            else:
                if raw_text:
                    conn.logger.bind(tag=TAG, phase="ASR").info(f"ASR text: {raw_text}")
                if speaker_name:
                    logger.bind(tag=TAG).info(f"识别说话人: {speaker_name}")

                enhanced_text = self._build_enhanced_text(raw_text, speaker_name)
                content_for_length_check = raw_text

            total_time = time.monotonic() - total_start_time
            conn.logger.bind(tag=TAG, phase="ASR").info(
                f"ASR done: elapsed={total_time:.3f}s"
            )

            text_len, _ = remove_punctuation_and_length(content_for_length_check)
            self.stop_ws_connection()

            if text_len > 0:
                audio_snapshot = asr_audio_task.copy()
                enqueue_asr_report(conn, enhanced_text, audio_snapshot)
                await startToChat(conn, enhanced_text)
        except Exception as e:
            conn.logger.bind(tag=TAG).error(
                "[HYBRID-ASR] asr_error device={} session={} error_type={} message={}",
                conn.device_id or "-",
                conn.session_id or "-",
                type(e).__name__,
                e,
            )
            logger.bind(tag=TAG).error(f"处理语音停止失败: {e}")
            logger.bind(tag=TAG).debug(f"异常详情: {traceback.format_exc()}")

    def _build_enhanced_text(self, text: str, speaker_name: Optional[str]) -> str:
        if speaker_name and speaker_name.strip():
            return json.dumps(
                {"speaker": speaker_name, "content": text}, ensure_ascii=False
            )
        else:
            return text

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        if len(pcm_data) == 0:
            logger.bind(tag=TAG).warning("PCM数据为空，无法转换WAV")
            return b""

        if len(pcm_data) % 2 != 0:
            pcm_data = pcm_data[:-1]

        wav_buffer = io.BytesIO()
        try:
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(pcm_data)

            wav_buffer.seek(0)
            wav_data = wav_buffer.read()

            return wav_data
        except Exception as e:
            logger.bind(tag=TAG).error(f"WAV转换失败: {e}")
            return b""

    def stop_ws_connection(self):
        pass

    async def close(self):
        pass

    class AudioArtifacts(NamedTuple):
        pcm_frames: List[bytes]
        pcm_bytes: bytes
        file_path: Optional[str]
        temp_path: Optional[str]

    def get_current_artifacts(self) -> Optional["ASRProviderBase.AudioArtifacts"]:
        return self._current_artifacts

    def requires_file(self) -> bool:
        return False

    def prefers_temp_file(self) -> bool:
        return False

    def build_temp_file(self, pcm_bytes: bytes) -> Optional[str]:
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
            with wave.open(temp_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(pcm_bytes)
            return temp_path
        except Exception as e:
            logger.bind(tag=TAG).error(f"临时音频文件生成失败: {e}")
            return None

    def save_audio_to_file(self, pcm_data: List[bytes], session_id: str) -> str:
        module_name = __name__.split(".")[-1]
        file_name = f"asr_{module_name}_{session_id}_{uuid.uuid4()}.wav"
        file_path = os.path.join(self.output_dir, file_name)

        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"".join(pcm_data))

        return file_path

    async def speech_to_text_wrapper(
        self, opus_data: List[bytes], session_id: str, audio_format="opus"
    ) -> Tuple[Optional[str], Optional[str]]:
        file_path = None
        temp_path = None
        try:
            if audio_format == "pcm":
                pcm_data = opus_data
            else:
                pcm_data = self.decode_opus(opus_data)
            combined_pcm_data = b"".join(pcm_data)

            free_space = shutil.disk_usage(self.output_dir).free
            if free_space < len(combined_pcm_data) * 2:
                raise OSError("磁盘空间不足")

            if self.requires_file() and self.prefers_temp_file():
                temp_path = self.build_temp_file(combined_pcm_data)

            if (hasattr(self, "delete_audio_file") and not self.delete_audio_file) or (
                self.requires_file() and not self.prefers_temp_file()
            ):
                file_path = self.save_audio_to_file(pcm_data, session_id)

            if len(combined_pcm_data) == 0:
                artifacts = None
            else:
                artifacts = ASRProviderBase.AudioArtifacts(
                    pcm_frames=pcm_data,
                    pcm_bytes=combined_pcm_data,
                    file_path=file_path,
                    temp_path=temp_path,
                )

            text, _ = await self.speech_to_text(
                opus_data, session_id, audio_format, artifacts
            )
            return text, file_path
        except OSError as e:
            logger.bind(tag=TAG).error(f"文件操作错误: {e}")
            return None, None
        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}")
            return None, None
        finally:
            try:
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
                if (
                    hasattr(self, "delete_audio_file")
                    and self.delete_audio_file
                    and file_path
                    and os.path.exists(file_path)
                ):
                    os.remove(file_path)
            except Exception as e:
                logger.bind(tag=TAG).error(f"文件清理失败: {e}")

    @abstractmethod
    async def speech_to_text(
        self,
        opus_data: List[bytes],
        session_id: str,
        audio_format="opus",
        artifacts: Optional[AudioArtifacts] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        pass

    @staticmethod
    def decode_opus(opus_data: List[bytes]) -> List[bytes]:
        decoder = None
        try:
            decoder = opuslib_next.Decoder(16000, 1)
            pcm_data = []
            buffer_size = 960

            for i, opus_packet in enumerate(opus_data):
                try:
                    if not opus_packet or len(opus_packet) == 0:
                        continue

                    pcm_frame = decoder.decode(opus_packet, buffer_size)
                    if pcm_frame and len(pcm_frame) > 0:
                        pcm_data.append(pcm_frame)

                except opuslib_next.OpusError as e:
                    logger.bind(tag=TAG).warning(f"Opus解码错误，跳过数据包 {i}: {e}")
                except Exception as e:
                    logger.bind(tag=TAG).error(f"音频处理错误，数据包 {i}: {e}")

            return pcm_data

        except Exception as e:
            logger.bind(tag=TAG).error(
                f"[HYBRID-ASR] opus_decode_error error_type={type(e).__name__} message={e}"
            )
            logger.bind(tag=TAG).error(f"音频解码过程发生错误: {e}")
            return []
        finally:
            if decoder is not None:
                try:
                    del decoder
                except Exception as e:
                    logger.bind(tag=TAG).debug(f"释放decoder资源时出错: {e}")
