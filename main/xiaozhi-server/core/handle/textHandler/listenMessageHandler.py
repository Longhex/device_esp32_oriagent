import time
import asyncio
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

from core.handle.receiveAudioHandle import startToChat
from core.handle.reportHandle import enqueue_asr_report
from core.handle.sendAudioHandle import send_stt_message, send_tts_message
from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from core.utils.util import remove_punctuation_and_length
from core.providers.asr.dto.dto import InterfaceType

TAG = __name__


def _schedule_oriagent_warmup(conn: "ConnectionHandler", trigger: str) -> None:
    if not conn.device_id:
        return

    existing = getattr(conn, "oriagent_warmup_task", None)
    if existing is not None and not existing.done():
        conn.logger.bind(tag=TAG, phase="LLM").debug(
            "[TIMING] event=oriagent_ws_warm_already_running device={} session={} trigger={} wall_ms={}",
            conn.device_id or "-",
            conn.session_id or "-",
            trigger,
            int(time.time() * 1000),
        )
        return

    async def _run_warmup():
        await conn.llm_ready_event.wait()
        if conn.stop_event.is_set():
            return
        llm = getattr(conn, "llm", None)
        if llm is None or not hasattr(llm, "warmup"):
            return

        conn.logger.bind(tag=TAG, phase="LLM").info(
            "[TIMING] event=oriagent_ws_warm_scheduled device={} session={} trigger={} wall_ms={}",
            conn.device_id or "-",
            conn.session_id or "-",
            trigger,
            int(time.time() * 1000),
        )
        await asyncio.to_thread(
            llm.warmup,
            conn.device_id,
            conn.session_id,
            trigger,
            conn.stop_event.is_set,
        )

    conn.oriagent_warmup_task = asyncio.create_task(_run_warmup())


class ListenTextMessageHandler(TextMessageHandler):
    """Listen消息处理器"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.LISTEN

    async def handle(self, conn: "ConnectionHandler", msg_json: Dict[str, Any]) -> None:
        if "mode" in msg_json:
            conn.client_listen_mode = msg_json["mode"]
            conn.logger.bind(tag=TAG).debug(
                f"客户端拾音模式：{conn.client_listen_mode}"
            )
        if msg_json["state"] == "start":
            conn.logger.bind(tag=TAG, phase="INPUT").info(
                "[TIMING] event=listen_start_received device={} session={} wall_ms={} mode={}",
                conn.device_id or "-",
                conn.session_id or "-",
                int(time.time() * 1000),
                conn.client_listen_mode,
            )
            # Warm upstream while the user is speaking; by VAD stop the
            # Oriagent handshake should already be off the critical path.
            _schedule_oriagent_warmup(conn, "listen_start")
            # 设备从播放模式切回录音模式,清除所有音频状态和缓冲区
            conn.reset_audio_states()
        elif msg_json["state"] == "stop":
            conn.client_voice_stop = True
            if conn.asr.interface_type == InterfaceType.STREAM:
                # 流式模式下，发送结束请求
                asyncio.create_task(conn.asr._send_stop_request())
            else:
                # 非流式模式：直接触发ASR识别
                if len(conn.asr_audio) > 0:
                    asr_audio_task = conn.asr_audio.copy()
                    conn.reset_audio_states()

                    if len(asr_audio_task) > 0:
                        await conn.asr.handle_voice_stop(conn, asr_audio_task)
        elif msg_json["state"] == "detect":
            conn.client_have_voice = False
            conn.reset_audio_states()
            if "text" in msg_json:
                conn.last_activity_time = time.time() * 1000
                original_text = msg_json["text"]  # 保留原始文本
                filtered_len, filtered_text = remove_punctuation_and_length(
                    original_text
                )

                # 识别是否是唤醒词
                is_wakeup_words = filtered_text in conn.config.get("wakeup_words")
                # 是否开启唤醒词回复
                enable_greeting = conn.config.get("enable_greeting", True)

                if is_wakeup_words and not enable_greeting:
                    # 如果是唤醒词，且关闭了唤醒词回复，就不用回答
                    await send_stt_message(conn, original_text)
                    await send_tts_message(conn, "stop", None)
                    conn.client_is_speaking = False
                elif is_wakeup_words:
                    conn.just_woken_up = True
                    # 上报纯文字数据（复用ASR上报功能，但不提供音频数据）
                    enqueue_asr_report(conn, "嘿，你好呀", [])
                    await startToChat(conn, "嘿，你好呀")
                else:
                    conn.just_woken_up = True
                    # 上报纯文字数据（复用ASR上报功能，但不提供音频数据）
                    enqueue_asr_report(conn, original_text, [])
                    # 否则需要LLM对文字内容进行答复
                    await startToChat(conn, original_text)