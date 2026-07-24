import time
import json
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler
from core.utils.util import audio_to_data
from core.handle.abortHandle import handleAbortMessage
from core.handle.intentHandler import handle_user_intent
from core.utils.output_counter import check_device_output_limit
from core.handle.sendAudioHandle import send_stt_message, SentenceType

TAG = __name__


def _should_log_hybrid_audio_event(conn: "ConnectionHandler", event_name: str, interval: int = 25) -> bool:
    counters = getattr(conn, "_hybrid_audio_log_counters", None)
    if counters is None:
        counters = {}
        setattr(conn, "_hybrid_audio_log_counters", counters)

    count = counters.get(event_name, 0) + 1
    counters[event_name] = count
    return count == 1 or count % interval == 0


async def handleAudioMessage(conn: "ConnectionHandler", audio):
    if _should_log_hybrid_audio_event(conn, "handle_audio_message"):
        conn.logger.bind(tag=TAG).info(
            "[HYBRID-AUDIO] handle_audio_message device={} session={} chunk_len={} audio_format={}",
            conn.device_id or "-",
            conn.session_id or "-",
            len(audio) if audio is not None else 0,
            conn.audio_format,
        )

    # 当前片段是否有人说话
    have_voice = conn.vad.is_vad(conn, audio)
    if _should_log_hybrid_audio_event(conn, "vad_decision"):
        conn.logger.bind(tag=TAG).info(
            "[HYBRID-AUDIO] vad_chunk device={} session={} chunk_len={} audio_format={} have_voice={} buffered_frames={}",
            conn.device_id or "-",
            conn.session_id or "-",
            len(audio) if audio is not None else 0,
            conn.audio_format,
            have_voice,
            len(conn.asr_audio),
        )
    # 如果设备刚刚被唤醒，短暂忽略VAD检测
    if hasattr(conn, "just_woken_up") and conn.just_woken_up:
        have_voice = False
        # 设置一个短暂延迟后恢复VAD检测
        if not hasattr(conn, "vad_resume_task") or conn.vad_resume_task.done():
            conn.vad_resume_task = asyncio.create_task(resume_vad_detection(conn))
        return
    # manual 模式下不打断正在播放的内容
    if have_voice:
        if conn.client_is_speaking and conn.client_listen_mode != "manual":
            await handleAbortMessage(conn)
    # 设备长时间空闲检测，用于say goodbye
    await no_voice_close_connect(conn, have_voice)
    # 接收音频
    await conn.asr.receive_audio(conn, audio, have_voice)


async def resume_vad_detection(conn: "ConnectionHandler"):
    # ESP32 DAC ramp-up + wakeword tail ~200-300ms; 2s là quá dài
    await asyncio.sleep(0.3)
    conn.just_woken_up = False


async def startToChat(conn: "ConnectionHandler", text):
    # 检查输入是否是JSON格式（包含说话人信息或情绪/语言标签）
    speaker_name = None
    language_tag = None
    actual_text = text

    try:
        # 尝试解析JSON格式的输入（FunASR返回包含language/emotion/content的dict）
        if text.strip().startswith("{") and text.strip().endswith("}"):
            data = json.loads(text)
            if "content" in data:
                # 提取纯文本内容，避免将emoji/unicode字符传入LLM请求
                actual_text = data["content"]
                language_tag = data.get("language")
                if "speaker" in data:
                    speaker_name = data["speaker"]
                    conn.logger.bind(tag=TAG).info(f"Parsed speaker info: {speaker_name}")
    except (json.JSONDecodeError, KeyError):
        # 如果解析失败，继续使用原始文本
        pass

    conn.logger.bind(tag=TAG, phase="INPUT").info(
        f"Pipeline input accepted: {actual_text[:120]}"
    )

    # 保存说话人信息到连接对象
    if speaker_name:
        conn.current_speaker = speaker_name
    else:
        conn.current_speaker = None

    if conn.need_bind:
        await check_bind_device(conn)
        return

    # 如果当日的输出字数大于限定的字数
    if conn.max_output_size > 0:
        if check_device_output_limit(
            conn.headers.get("device-id"), conn.max_output_size
        ):
            await max_out_size(conn)
            return
    # manual 模式下不打断正在播放的内容
    if conn.client_is_speaking and conn.client_listen_mode != "manual":
        await handleAbortMessage(conn)

    # 首先进行意图分析，使用实际文本内容
    intent_handled = await handle_user_intent(conn, actual_text)

    if intent_handled:
        # 如果意图已被处理，不再进行聊天
        return

    # 意图未被处理，继续常规聊天流程，使用实际文本内容
    await send_stt_message(conn, actual_text)
    conn.executor.submit(conn.chat, actual_text)


async def no_voice_close_connect(conn: "ConnectionHandler", have_voice):
    if have_voice:
        conn.last_activity_time = time.time() * 1000
        return
    return


async def max_out_size(conn: "ConnectionHandler"):
    # 播放超出最大输出字数的提示
    conn.client_abort = False
    text = "Xin lỗi nhé, hiện tại tôi hơi bận một chút, chúng ta sẽ trò chuyện tiếp vào giờ này ngày mai nhé, đã hẹn rồi đó! Mai gặp lại nha, tạm biệt!"
    await send_stt_message(conn, text)
    file_path = "config/assets/max_output_size.wav"
    opus_packets = await audio_to_data(file_path)
    conn.tts.tts_audio_queue.put((SentenceType.LAST, opus_packets, text))
    conn.close_after_chat = True


async def check_bind_device(conn: "ConnectionHandler"):
    if conn.bind_code:
        # 确保bind_code是6位数字
        if len(conn.bind_code) != 6:
            conn.logger.bind(tag=TAG).error(f"Invalid binding code format: {conn.bind_code}")
            text = "Định dạng mã liên kết bị lỗi, vui lòng kiểm tra lại cấu hình."
            await send_stt_message(conn, text)
            return

        text = f"Vui lòng đăng nhập vào trang quản lý, nhập mã {conn.bind_code} để liên kết thiết bị."

        # MQTT firmware can render this structured notification on its LCD.
        # Do not replace the STT/TTS fallback below: deployed firmware that
        # does not know the new type must still receive the spoken prompt.
        if conn.conn_from_mqtt_gateway and conn.websocket:
            activation_message = {
                "type": "activation",
                "code": conn.bind_code,
                "message": text,
                "session_id": conn.session_id,
            }
            try:
                await conn.websocket.send(
                    json.dumps(activation_message, ensure_ascii=False)
                )
                conn.logger.bind(tag=TAG).info(
                    f"[BIND] Sent MQTT activation message to device={conn.device_id}"
                )
            except Exception as e:
                # A notification failure must not block device binding by audio.
                conn.logger.bind(tag=TAG).error(
                    f"[BIND] Failed to send MQTT activation message "
                    f"to device={conn.device_id}: {e}"
                )

        await send_stt_message(conn, text)

        # 播放提示音
        if conn.tts:
            music_path = "config/assets/bind_code.wav"
            opus_packets = await audio_to_data(music_path)
            conn.tts.tts_audio_queue.put((SentenceType.FIRST, opus_packets, text))

        # 逐个播放数字
        for i in range(6):  # 确保只播放6位数字
            try:
                digit = conn.bind_code[i]
                num_path = f"config/assets/bind_code/{digit}.wav"
                num_packets = await audio_to_data(num_path)
                if conn.tts:
                    conn.tts.tts_audio_queue.put((SentenceType.MIDDLE, num_packets, None))
            except Exception as e:
                conn.logger.bind(tag=TAG).error(f"Failed to play numeric audio: {e}")
                continue
        if conn.tts:
            conn.tts.tts_audio_queue.put((SentenceType.LAST, [], None))
    else:
        # 播放未绑定提示
        conn.client_abort = False
        text = f"Không tìm thấy thông tin phiên bản của thiết bị, vui lòng cấu hình đúng địa chỉ OTA và biên dịch lại firmware."
        await send_stt_message(conn, text)
        music_path = "config/assets/bind_not_found.wav"
        opus_packets = await audio_to_data(music_path)
        if conn.tts:
            conn.tts.tts_audio_queue.put((SentenceType.LAST, opus_packets, text))
