import json
import time
import queue
import asyncio
import ssl
import threading

import websockets

from config.logger import setup_logging
from core.utils.tts import MarkdownCleaner
from core.providers.tts.dto.dto import SentenceType, ContentType, InterfaceType
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    """
    Blaze.vn Realtime TTS provider - V3 SEQUENTIAL VERSION (STREAMING OPUS-TO-OPUS).

    Mỗi request mở một WS riêng và chạy đúng protocol V3:
        connect -> successful-connection
              -> {token, strategy:"request"} -> successful-authentication
              -> query -> processing-request -> started-byte-stream
              -> binary chunks (OPUS) -> stream ngay xuống thiết bị
              -> finished-byte-stream
    """

    PCM_SAMPLE_RATE = 24000
    PCM_CHANNELS = 1

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.config = config
        self.interface_type = InterfaceType.DUAL_STREAM
        self.api_key = config.get("api_key", "")

        self.model = config.get("model", "2.0-realtime")
        self.speaker_id = config.get("private_voice", "HN-Nu-ThuHuyenDeThuong")
        self.audio_speed = str(config.get("audio_speed", "1"))
        self.audio_quality = int(config.get("audio_quality", 64))
        
        # ĐỔI THÀNH OPUS (Xin Opus/Ogg từ server)
        self.audio_format = "opus"  
        
        self.normalization = config.get("normalization", "basic")
        self.language = config.get("language", "vi")
        self.sample_rate = self.PCM_SAMPLE_RATE

        domain = config.get("domain") or "api.blaze.vn"
        self.ws_url = f"wss://{domain}/v1/tts/realtime"

        self._segment_done = threading.Event()
        self.processed_chars = 0

    async def _recv_json(self, ws, timeout: float = 15.0) -> dict:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        if isinstance(raw, bytes):
            raise ValueError(f"Expected JSON, got binary ({len(raw)} bytes)")
        return json.loads(raw)

    async def _do_tts_request(self, text: str):
        """One WS per request — preserves original V3 demo flow, but streams immediately."""
        cleaned = []
        for ch in text:
            if ch.isalnum() or ch.isspace() or ch in ".?!":
                cleaned.append(ch)
            else:
                cleaned.append(" ")
        text = "".join(cleaned).strip()
        if not text:
            return
        if text[-1] not in ".?!":
            text = text + "."

        ws = None
        t0 = time.perf_counter()
        try:
            ssl_context = ssl.create_default_context()
            if self.config.get("verify_ssl") is False:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            ws = await websockets.connect(
                self.ws_url, ssl=ssl_context, ping_interval=None
            )

            # 1. successful-connection
            msg = await self._recv_json(ws, timeout=5.0)
            if msg.get("type") != "successful-connection":
                logger.bind(tag=TAG).error(f"Blaze V3: unexpected greeting: {msg}")
                return
            logger.bind(tag=TAG).info(
                f"Blaze V3: connected ({(time.perf_counter()-t0)*1000:.0f} ms)"
            )

            # 2. auth
            await ws.send(json.dumps({"token": self.api_key, "strategy": "request"}))
            msg = await self._recv_json(ws, timeout=5.0)
            if msg.get("type") != "successful-authentication":
                logger.bind(tag=TAG).error(f"Blaze V3: auth failed: {msg}")
                return

            # 3. query
            query = {
                "query": text,
                "language": self.language,
                "audio_format": self.audio_format,
                "audio_quality": self.audio_quality,
                "audio_speed": self.audio_speed,
                "speaker_id": self.speaker_id,
                "normalization": self.normalization,
                "model": self.model,
            }
            t_query = time.perf_counter()
            await ws.send(json.dumps(query))
            logger.bind(tag=TAG).info(f"Blaze V3 >> SENDING: {text[:60]}")

            # 4. processing-request
            msg = await self._recv_json(ws)
            if msg.get("type") != "processing-request":
                logger.bind(tag=TAG).error(f"Blaze V3: unexpected after query: {msg}")
                return

            # 5. started-byte-stream
            msg = await self._recv_json(ws)
            if msg.get("status") != "started-byte-stream":
                logger.bind(tag=TAG).error(f"Blaze V3: unexpected stream start: {msg}")
                return

            # 6. byte chunks ... finished-byte-stream
            t_first = None
            chunks_count = 0
            total_bytes = 0

            while True:
                if self.conn.client_abort:
                    return

                message = await asyncio.wait_for(ws.recv(), timeout=60.0)

                if isinstance(message, bytes):
                    if t_first is None:
                        t_first = time.perf_counter()
                        ttfb_ms = (t_first - t_query) * 1000
                        logger.bind(tag=TAG).info(f"Blaze V3: TTFB {ttfb_ms:.0f} ms")
                    
                    chunks_count += 1
                    total_bytes += len(message)
                    
                    # STREAM TRỰC TIẾP GIỐNG TTS_TEST.PY (không gom vào mảng nữa)
                    self.handle_opus(message)
                    continue

                data = json.loads(message)
                event = data.get("type") or data.get("status")
                if event == "finished-byte-stream":
                    total_ms = (time.perf_counter() - t_query) * 1000
                    logger.bind(tag=TAG).info(
                        f"Blaze V3: finished — chunks={chunks_count}, "
                        f"bytes={total_bytes}, total={total_ms:.0f} ms"
                    )
                    break
                if event in ("failed-request", "internal-error", "bad-request"):
                    logger.bind(tag=TAG).error(f"Blaze V3: server error: {data}")
                    return

        except asyncio.TimeoutError:
            logger.bind(tag=TAG).error("Blaze V3: timeout waiting for audio.")
        except Exception as e:
            logger.bind(tag=TAG).error(f"Blaze V3: request error: {e}")
        finally:
            if ws:
                try:
                    await ws.close()
                except Exception:
                    pass

    async def text_to_speak(self, text, _):
        filtered_text = MarkdownCleaner.clean_markdown(text)
        if not filtered_text:
            return
        self._segment_done.clear()
        try:
            await self._do_tts_request(filtered_text)
        finally:
            self._segment_done.set()

    def tts_text_priority_thread(self):
        logger.bind(tag=TAG).info("Blaze V3 TTS: worker thread active (1-connection mode).")
        while not self.conn.stop_event.is_set():
            try:
                message = self.tts_text_queue.get(timeout=1)

                if message.sentence_type == SentenceType.FIRST:
                    self.conn.client_abort = False
                    self.tts_text_buff = []

                if self.conn.client_abort:
                    continue

                if ContentType.TEXT == message.content_type and message.content_detail:
                    self.tts_text_buff.append(message.content_detail)
                    # GOM TOÀN BỘ CHỮ, KHÔNG CẮT ĐOẠN ĐỂ DÙNG 1 CONNECTION DUY NHẤT

                if message.sentence_type == SentenceType.LAST:
                    full_text = "".join(self.tts_text_buff)
                    if full_text.strip():
                        if self.conn.client_abort:
                            continue
                        asyncio.run_coroutine_threadsafe(
                            self.text_to_speak(full_text, None), self.conn.loop
                        ).result(timeout=60)
                    self.tts_audio_queue.put(
                        (SentenceType.LAST, [], message.content_detail)
                    )

            except queue.Empty:
                continue
            except Exception as e:
                logger.bind(tag=TAG).error(f"Blaze V3 thread error: {e}")

    def _get_smart_segment(self):
        """Only split when text has punctuation AND length > MIN_LENGTH."""
        MIN_LENGTH = 50
        full_text = "".join(self.tts_text_buff)
        text_to_process = full_text[self.processed_chars:]

        if len(text_to_process) < MIN_LENGTH:
            return None

        breakers = [".", "?", "!"]
        last_pos = -1
        for b in breakers:
            pos = text_to_process.rfind(b)
            if pos != -1 and pos > last_pos:
                last_pos = pos + 1

        if last_pos != -1:
            segment = text_to_process[:last_pos].strip()
            if segment:
                self.processed_chars += last_pos
                return segment
        return None

    def to_tts(self, text: str) -> list:
        return [{"type": "tts", "text": text}]

    async def close(self):
        self._segment_done.set()
