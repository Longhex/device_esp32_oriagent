import os
import io
import json
import asyncio
import websockets
import ssl
import threading
import queue
import time
import re

from config.logger import setup_logging
from core.utils.tts import MarkdownCleaner
from core.providers.tts.dto.dto import SentenceType, ContentType, InterfaceType
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()

# =============================================================================
# V5 THE ULTIMATE HYBRID: DUAL-POOL FETCH + ORDERED QUEUE CONSUMER
# - Fetch parallel using 4 WS connections for 0s network latency.
# - Consumer reads from Strict Ordered Queues -> 100% Thread-safe & No Deadlocks.
# - Smart Segments expanded to 25 words to prevent mid-sentence cutting.
# - Fixed: is_first_segment tracking to prevent audio cutting & properly show text.
# - Fixed: while True loop added to ensure all segments are processed.
# =============================================================================

INITIAL_BUFFER_BYTES = 9600  # ~400ms of audio at 24kHz/16bit/mono for ultra-low latency start
WAV_HEADER_SIZE = 44

class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.config = config
        self.interface_type = InterfaceType.DUAL_STREAM
        self.api_key = config.get("api_key")

        # Blaze Settings
        self.model = config.get("model", "2.0-realtime")
        self.speaker_id = config.get("private_voice", "HN-Nu-ThuHuyenDeThuong")
        self.audio_speed = config.get("audio_speed", "1.5")
        self.audio_format = "wav"
        self.sample_rate = 24000
        self.audio_quality = 128

        domain = config.get("domain") or "api.blaze.vn"
        self.ws_url = f"wss://{domain}/v1/tts/realtime"

        # Parallel Management
        self.ws_pool = [None, None, None, None]
        self.ws_locks = [asyncio.Lock(), asyncio.Lock(), asyncio.Lock(), asyncio.Lock()]

        self.emoji_pattern = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)

        # [V5] Async Orchestration
        self.playback_queue = None
        self.segment_queues = {}
        self.playback_task = None
        self._playback_active = False

    async def _ensure_connection(self, pool_idx):
        ws = self.ws_pool[pool_idx]
        if ws and getattr(ws, "open", False):
            return ws

        ssl_context = ssl.create_default_context()
        if self.config.get("verify_ssl") is False:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        try:
            ws = await websockets.connect(
                self.ws_url, ssl=ssl_context, ping_interval=5.0, ping_timeout=5.0
            )
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            await ws.send(json.dumps({"token": self.api_key, "strategy": "streaming"}))
            auth_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)

            if "successful-authentication" not in auth_msg:
                logger.bind(tag=TAG).error(f"Blaze WS[{pool_idx}]: Auth failed.")
                await ws.close()
                return None

            logger.bind(tag=TAG).info(f"Blaze WS[{pool_idx}]: Connected.")
            self.ws_pool[pool_idx] = ws
            return ws
        except Exception as e:
            logger.bind(tag=TAG).error(f"Blaze WS[{pool_idx}]: Error: {e}")
            return None

    # =========================================================================
    # CONSUMER: BẢO ĐẢM THỨ TỰ PHÁT (STRICT ORDER)
    # =========================================================================
    async def _start_playback_worker(self):
        if self.playback_queue is None:
            self.playback_queue = asyncio.Queue()
            self._playback_active = True
            self.playback_task = self.conn.loop.create_task(self._playback_loop())

    async def _playback_loop(self):
        jitter_buffer = bytearray()
        first_packet_sent = False
        CONTINUOUS_JITTER_THRESHOLD = 4800  # 100ms buffer

        while self._playback_active:
            try:
                item = await self.playback_queue.get()

                if item == 'END_OF_SESSION':
                    if jitter_buffer:
                        self.opus_encoder.encode_pcm_to_opus_stream(bytes(jitter_buffer), False, self.handle_opus)
                        jitter_buffer.clear()
                    first_packet_sent = False
                    self.playback_queue.task_done()
                    continue

                if self.conn.client_abort:
                    self.playback_queue.task_done()
                    continue

                idx, is_first, segment_text = item
                
                # Push Text update exactly when audio is about to play
                if is_first:
                    self.tts_audio_queue.put((SentenceType.FIRST, None, segment_text))
                else:
                    self.tts_audio_queue.put((SentenceType.MIDDLE, None, segment_text))

                seg_queue = self.segment_queues.get(idx)
                if not seg_queue:
                    self.playback_queue.task_done()
                    continue

                while True:
                    if self.conn.client_abort: break

                    pcm_chunk = await seg_queue.get()
                    if pcm_chunk == b'END_OF_SEGMENT':
                        if not first_packet_sent and jitter_buffer:
                            self.opus_encoder.encode_pcm_to_opus_stream(bytes(jitter_buffer), False, self.handle_opus)
                            jitter_buffer.clear()
                            first_packet_sent = True
                        seg_queue.task_done()
                        break

                    jitter_buffer.extend(pcm_chunk)

                    if not first_packet_sent:
                        if len(jitter_buffer) >= INITIAL_BUFFER_BYTES:
                            self.opus_encoder.encode_pcm_to_opus_stream(bytes(jitter_buffer), False, self.handle_opus)
                            jitter_buffer.clear()
                            first_packet_sent = True
                    else:
                        if len(jitter_buffer) >= CONTINUOUS_JITTER_THRESHOLD:
                            self.opus_encoder.encode_pcm_to_opus_stream(bytes(jitter_buffer), False, self.handle_opus)
                            jitter_buffer.clear()

                    seg_queue.task_done()

                self.segment_queues.pop(idx, None)
                self.playback_queue.task_done()

            except asyncio.CancelledError:
                self._playback_active = False
                break
            except Exception as e:
                if self._playback_active:
                    logger.bind(tag=TAG).error(f"Playback Loop Error: {e}")
                    await asyncio.sleep(0.5)
                else:
                    break

    def _empty_queues(self):
        if self.playback_queue:
            while not self.playback_queue.empty():
                try: self.playback_queue.get_nowait()
                except queue.Empty: break
        self.segment_queues.clear()

    # =========================================================================
    # PRODUCER: TẢI SONG SONG (DUAL FETCH)
    # =========================================================================
    async def _fetch_segment(self, idx, text, is_last=False):
        pool_idx = idx % 4
        seg_queue = self.segment_queues[idx]

        text = self.emoji_pattern.sub(r"", text)
        text = text.replace("...", ",")
        allowed_chars = ".,?!:;，。！？；： "
        text = "".join(ch for ch in text if ch.isalnum() or ch in allowed_chars)

        if not any(ch.isalnum() for ch in text):
            await seg_queue.put(b'END_OF_SEGMENT')
            return

        if is_last and text and text[-1] not in ".?!":
            text = text + "."

        async with self.ws_locks[pool_idx]:
            ws = await self._ensure_connection(pool_idx)
            if not ws:
                await seg_queue.put(b'END_OF_SEGMENT')
                return

            req = {
                "query": text, "normalization": "basic", "language": "vi",
                "audio_format": self.audio_format, "audio_quality": self.audio_quality,
                "audio_speed": self.audio_speed, "speaker_id": self.speaker_id, "model": self.model,
                "sample_rate": self.sample_rate
            }
            logger.bind(tag=TAG).info(f"Blaze WS[{pool_idx}] FETCHING [Idx:{idx}]: {text[:40]}")

            try:
                await ws.send(json.dumps(req))
                header_skipped = False

                while True:
                    if self.conn.client_abort: break

                    message = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    if isinstance(message, bytes):
                        pcm_data = message
                        if not header_skipped:
                            if pcm_data[:4] == b'RIFF': pcm_data = pcm_data[WAV_HEADER_SIZE:]
                            header_skipped = True
                        if pcm_data: await seg_queue.put(pcm_data)
                    else:
                        data = json.loads(message)
                        if data.get("type") == "finished-byte-stream":
                            break
            except websockets.exceptions.ConnectionClosed:
                logger.bind(tag=TAG).debug(f"Blaze WS[{pool_idx}] closed gracefully.")
                self.ws_pool[pool_idx] = None
            except Exception as e:
                logger.bind(tag=TAG).error(f"Blaze WS[{pool_idx}] Fetch Error: {e}")
                self.ws_pool[pool_idx] = None
            finally:
                await seg_queue.put(b'END_OF_SEGMENT')

    # =========================================================================
    # MASTER THREAD: QUẢN LÝ DÒNG CHẢY TEXT
    # =========================================================================
    def tts_text_priority_thread(self):
        logger.bind(tag=TAG).info("Blaze Speed TTS: V5 Master Pipeline active.")
        asyncio.run_coroutine_threadsafe(self._start_playback_worker(), self.conn.loop)

        while not self.conn.stop_event.is_set():
            try:
                message = self.tts_text_queue.get(timeout=1)

                if message.sentence_type == SentenceType.FIRST:
                    self.conn.client_abort = False
                    self.tts_text_buff = []
                    self.processed_chars = 0
                    self.segment_counter = 0
                    self.is_first_segment = True
                    self._empty_queues()
                    logger.bind(tag=TAG).info("Blaze Speed TTS: Session Reset.")

                if self.conn.client_abort: continue

                if ContentType.TEXT == message.content_type and message.content_detail:
                    self.tts_text_buff.append(message.content_detail)
                    
                    while True:
                        segment = self._get_smart_segment()
                        if not segment:
                            break
                        
                        idx = self.segment_counter
                        self.segment_counter += 1

                        self.segment_queues[idx] = asyncio.Queue()
                        asyncio.run_coroutine_threadsafe(
                            self.playback_queue.put((idx, self.is_first_segment, segment)), 
                            self.conn.loop
                        )
                        self.is_first_segment = False
                        asyncio.run_coroutine_threadsafe(self._fetch_segment(idx, segment, False), self.conn.loop)

                if message.sentence_type == SentenceType.LAST:
                    full_text = "".join(self.tts_text_buff)
                    remaining = full_text[self.processed_chars:]
                    if remaining.strip() and not self.conn.client_abort:
                        idx = self.segment_counter
                        self.segment_counter += 1

                        self.segment_queues[idx] = asyncio.Queue()
                        asyncio.run_coroutine_threadsafe(
                            self.playback_queue.put((idx, self.is_first_segment, remaining)), 
                            self.conn.loop
                        )
                        self.is_first_segment = False
                        asyncio.run_coroutine_threadsafe(self._fetch_segment(idx, remaining, True), self.conn.loop)

                    self.conn.executor.submit(self._wait_for_all_and_finish, message.content_detail)

            except queue.Empty: continue
            except Exception as e:
                logger.bind(tag=TAG).error(f"Blaze Speed Thread Error: {e}")

    def _get_smart_segment(self):
        full_text = "".join(self.tts_text_buff)
        text_to_process = full_text[self.processed_chars:]
        if not text_to_process: return None

        temp_text = self.emoji_pattern.sub(r"", text_to_process)
        words = temp_text.split()
        word_count = len(words)

        hard_stops = [".", "!", "?", "\n", "。", "！", "？"]
        for i, char in enumerate(text_to_process):
            if char in hard_stops:
                seg = text_to_process[:i+1].strip()
                if seg:
                    self.processed_chars += (i + 1)
                    return seg

        soft_stops = [",", ":", ";", "，", "：", "；"]
        for i, char in enumerate(text_to_process):
            if char in soft_stops:
                if word_count >= 10:
                    seg = text_to_process[:i+1].strip()
                    if seg:
                        self.processed_chars += (i + 1)
                        return seg

        if word_count >= 25:
            last_space = text_to_process.rfind(" ")
            if last_space != -1:
                seg = text_to_process[:last_space].strip()
                if seg:
                    self.processed_chars += (last_space + 1)
                    return seg

        return None

    def _wait_for_all_and_finish(self, content_detail):
        async def wait_loop():
            if self.playback_queue:
                await self.playback_queue.put('END_OF_SESSION')
                await self.playback_queue.join()
                await asyncio.sleep(0.5)

        future = asyncio.run_coroutine_threadsafe(wait_loop(), self.conn.loop)
        try:
            future.result(timeout=10) # Reduced from 60 to 10
        except Exception:
            if self._playback_active and not self.conn.stop_event.is_set():
                logger.bind(tag=TAG).warning("Blaze Speed TTS: Wait loop timeout!")

        self.tts_audio_queue.put((SentenceType.LAST, [], content_detail))

    def text_to_speak(self, text, _):
        pass

    def to_tts(self, text: str) -> list:
        return [{"type": "tts", "text": text}]

    async def close(self):
        self._playback_active = False
        if self.playback_task: self.playback_task.cancel()
        for ws in self.ws_pool:
            if ws:
                try: await ws.close()
                except: pass
