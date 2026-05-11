import re
import json
import asyncio
import websockets
import ssl
import queue
from contextlib import asynccontextmanager

from config.logger import setup_logging
from core.utils.tts import MarkdownCleaner
from core.providers.tts.dto.dto import SentenceType, ContentType, InterfaceType
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()

# =============================================================================
# V2 BLAZE SPEED TTS — PRODUCTION GRADE (100% RELIABILITY)
# =============================================================================

INITIAL_BUFFER_BYTES = 4800     # ~100ms @ 24kHz/16bit/mono
CONTINUOUS_JITTER_BYTES = 4800  # ~100ms continuous buffer
WAV_HEADER_SIZE = 44
POOL_SIZE = 4
FETCH_TIMEOUT = 10.0
POOL_HEALTH_INTERVAL = 5.0
PLAYBACK_JOIN_TIMEOUT = 30.0
SEGMENT_FETCH_TIMEOUT = 25.0  # Increased to allow Producer retries (10s+10s+5s)

# =============================================================================
# CONNECTION POOL: PRE-WARMED & SELF-HEALING
# =============================================================================
class BlazeConnectionPool:
    def __init__(self, ws_url, token, pool_size=POOL_SIZE, ssl_context=None):
        self.ws_url = ws_url
        self.token = token
        self.pool_size = pool_size
        self.ssl_context = ssl_context
        self.pool = [None] * pool_size
        self.locks = [asyncio.Lock() for _ in range(pool_size)]
        self._maintain_task = None
        self._maintain_event = asyncio.Event()
        self._active = False
        self.last_idx = 0

    async def _connect_and_auth(self, idx):
        # Ensure old connection is closed if it exists
        if self.pool[idx]:
            try:
                await self.pool[idx].close()
            except:
                pass
            self.pool[idx] = None

        ws = None
        try:
            ws = await asyncio.wait_for(
                websockets.connect(
                    self.ws_url, ssl=self.ssl_context,
                    ping_interval=30.0, ping_timeout=30.0, # Relaxed ping
                ),
                timeout=5.0,
            )
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            await ws.send(json.dumps({"token": self.token, "strategy": "streaming"}))
            auth_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)

            if "successful-authentication" not in str(auth_msg):
                logger.bind(tag=TAG).error(f"Pool[{idx}]: Auth failed.")
                await ws.close()
                return False

            self.pool[idx] = ws
            logger.bind(tag=TAG).info(f"Pool[{idx}]: Ready.")
            return True
        except Exception as e:
            logger.bind(tag=TAG).error(f"Pool[{idx}]: Connection failed: {e}")
            if ws: await ws.close()
            self.pool[idx] = None
            return False

    async def warm_up(self):
        self._active = True
        tasks = [self._connect_and_auth(i) for i in range(self.pool_size)]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _maintain_loop(self):
        while self._active:
            try:
                for i in range(self.pool_size):
                    async with self.locks[i]: # PREVENT RACE CONDITION with get_connection
                        ws = self.pool[i]
                        if ws is None or getattr(ws, "closed", True):
                            await self._connect_and_auth(i)
                
                await asyncio.wait_for(self._maintain_event.wait(), timeout=POOL_HEALTH_INTERVAL * 6)
                self._maintain_event.clear()
            except asyncio.TimeoutError: pass
            except asyncio.CancelledError: break
            except Exception as e:
                logger.bind(tag=TAG).error(f"Pool maintain error: {e}")
                await asyncio.sleep(POOL_HEALTH_INTERVAL)

    def start_maintenance(self, loop):
        self._maintain_task = loop.create_task(self._maintain_loop())

    @asynccontextmanager
    async def get_connection(self):
        target_idx = -1
        for _ in range(self.pool_size):
            idx = self.last_idx % self.pool_size
            self.last_idx += 1
            if not self.locks[idx].locked():
                await self.locks[idx].acquire()
                if self.pool[idx] is None or getattr(self.pool[idx], "closed", True):
                    await self._connect_and_auth(idx)
                
                if self.pool[idx] and not getattr(self.pool[idx], "closed", True):
                    target_idx = idx
                    break
                else:
                    self.locks[idx].release()

        if target_idx == -1:
            target_idx = self.last_idx % self.pool_size
            self.last_idx += 1
            await self.locks[target_idx].acquire()
            if self.pool[target_idx] is None or getattr(self.pool[target_idx], "closed", True):
                await self._connect_and_auth(target_idx)

        try:
            yield target_idx, self.pool[target_idx]
        finally:
            if self.locks[target_idx].locked():
                self.locks[target_idx].release()

    def mark_dead(self, idx):
        logger.bind(tag=TAG).warning(f"Pool[{idx}]: Connection marked DEAD, triggering revival.")
        self.pool[idx] = None
        self._maintain_event.set()

    async def close_all(self):
        self._active = False
        if self._maintain_task: self._maintain_task.cancel()
        for i, ws in enumerate(self.pool):
            if ws: await ws.close()
            self.pool[i] = None

# =============================================================================
# TTS PROVIDER V2
# =============================================================================
class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.interface_type = InterfaceType.DUAL_STREAM
        self.api_key = config.get("api_key")
        self.model = config.get("model", "2.0-realtime")
        self.speaker_id = config.get("private_voice", "HN-Nu-ThuHuyenDeThuong")
        self.audio_speed = config.get("audio_speed", "1.1")
        self.audio_format = "wav"
        self.sample_rate = 24000
        self.audio_quality = 128

        domain = config.get("domain") or "api.blaze.vn"
        self.ws_url = f"wss://{domain}/v1/tts/realtime"

        ssl_ctx = ssl.create_default_context()
        if config.get("verify_ssl") is False:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        self.pool = BlazeConnectionPool(self.ws_url, self.api_key, POOL_SIZE, ssl_ctx)
        self.emoji_pattern = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)

        self.playback_queue = None
        self.segment_queues = {}
        self.playback_task = None
        self._playback_active = False
        self._fetch_tasks = set()
        self.current_session_id = 0
        self.processed_chars = 0
        self.segment_counter = 0

    async def open_audio_channels(self, conn):
        await super().open_audio_channels(conn)
        await self.pool.warm_up()
        self.pool.start_maintenance(conn.loop)

    async def _start_playback_worker(self):
        if self.playback_queue is None:
            self.playback_queue = asyncio.Queue()
            self._playback_active = True
            self.playback_task = self.conn.loop.create_task(self._playback_loop())

    async def _playback_loop(self):
        jitter_buffer = bytearray()
        first_packet_sent = False

        while self._playback_active:
            try:
                item = await self.playback_queue.get()

                if item == "END_OF_SESSION":
                    if len(jitter_buffer) > 0:
                        if len(jitter_buffer) % 2 != 0: jitter_buffer = jitter_buffer[:-1]
                        self.opus_encoder.encode_pcm_to_opus_stream(bytes(jitter_buffer), True, self.handle_opus)
                    else:
                        self.opus_encoder.reset_state()
                    jitter_buffer.clear()
                    first_packet_sent = False
                    self.playback_queue.task_done()
                    continue

                if item == "FLUSH":
                    jitter_buffer.clear()
                    self.opus_encoder.reset_state()
                    self.playback_queue.task_done()
                    continue

                if self.conn.client_abort:
                    jitter_buffer.clear()
                    self.playback_queue.task_done()
                    continue

                # Expected item: (idx, is_first, segment_text, session_id)
                if not (isinstance(item, tuple) and len(item) == 4):
                    self.playback_queue.task_done()
                    continue

                idx, is_first, segment_text, session_id = item
                task_id = f"{session_id}_{idx}"

                if self.current_session_id != session_id:
                    self.playback_queue.task_done()
                    continue

                if is_first:
                    self.tts_audio_queue.put((SentenceType.FIRST, None, segment_text))
                else:
                    self.tts_audio_queue.put((SentenceType.MIDDLE, None, segment_text))

                seg_queue = self.segment_queues.get(task_id)
                if not seg_queue:
                    self.playback_queue.task_done()
                    continue

                try:
                    while True:
                        if self.conn.client_abort or self.current_session_id != session_id: break
                        try:
                            pcm_chunk = await asyncio.wait_for(seg_queue.get(), timeout=SEGMENT_FETCH_TIMEOUT)
                        except asyncio.TimeoutError:
                            logger.bind(tag=TAG).warning(f"V2: Segment #{task_id} timeout.")
                            break

                        if pcm_chunk == b"END_OF_SEGMENT":
                            if len(jitter_buffer) > 0:
                                valid_len = len(jitter_buffer) - (len(jitter_buffer) % 2)
                                if valid_len > 0:
                                    self.opus_encoder.encode_pcm_to_opus_stream(bytes(jitter_buffer[:valid_len]), False, self.handle_opus)
                                    del jitter_buffer[:valid_len]
                            jitter_buffer.clear()
                            seg_queue.task_done()
                            first_packet_sent = True
                            break

                        jitter_buffer.extend(pcm_chunk)
                        if not first_packet_sent:
                            if len(jitter_buffer) >= INITIAL_BUFFER_BYTES:
                                valid_len = len(jitter_buffer) - (len(jitter_buffer) % 2)
                                self.opus_encoder.encode_pcm_to_opus_stream(bytes(jitter_buffer[:valid_len]), False, self.handle_opus)
                                del jitter_buffer[:valid_len]
                                first_packet_sent = True
                        else:
                            if len(jitter_buffer) >= CONTINUOUS_JITTER_BYTES:
                                valid_len = len(jitter_buffer) - (len(jitter_buffer) % 2)
                                self.opus_encoder.encode_pcm_to_opus_stream(bytes(jitter_buffer[:valid_len]), False, self.handle_opus)
                                del jitter_buffer[:valid_len]
                finally:
                    self.segment_queues.pop(task_id, None)
                    self.playback_queue.task_done()

            except asyncio.CancelledError: break
            except Exception as e:
                if self._playback_active:
                    logger.bind(tag=TAG).error(f"V2 Playback Error: {e}")
                    await asyncio.sleep(0.1)

    def _flush_pipeline(self):
        for task in list(self._fetch_tasks):
            if not task.done(): task.cancel()
        self._fetch_tasks.clear()

        if self.playback_queue:
            while not self.playback_queue.empty():
                try:
                    self.playback_queue.get_nowait()
                    self.playback_queue.task_done()
                except: break
            try:
                self.opus_encoder.reset_state()
                self.playback_queue.put_nowait("FLUSH")
            except: pass

        for sq in self.segment_queues.values():
            while not sq.empty():
                try: sq.get_nowait()
                except: break
        self.segment_queues.clear()

    async def _fetch_with_retry(self, idx, text, session_id, is_last=False):
        task_id = f"{session_id}_{idx}"
        seg_queue = self.segment_queues.get(task_id)
        if not seg_queue: return

        # Clean text
        text = self.emoji_pattern.sub(r"", text)
        text = text.replace("**", "").replace("*", "").replace("__", "").replace("_", "").replace("`", "").replace("...", ",")
        allowed_chars = ".,?!:;，。！？；： "
        text = "".join(ch for ch in text if ch.isalnum() or ch in allowed_chars)

        if not any(ch.isalnum() for ch in text):
            await seg_queue.put(b"END_OF_SEGMENT")
            return

        if is_last and text and text[-1] not in ".?!": text += "."

        try:
            success = await self._do_fetch(idx, text, session_id, attempt=0)
            if not success and not self.conn.client_abort and self.current_session_id == session_id:
                await self._do_fetch(idx, text, session_id, attempt=1)
        except asyncio.CancelledError: pass
        finally:
            await seg_queue.put(b"END_OF_SEGMENT")

    async def _do_fetch(self, idx, text, session_id, attempt=0):
        pool_idx = -1
        try:
            async with self.pool.get_connection() as (p_idx, ws):
                pool_idx = p_idx
                if not ws or self.current_session_id != session_id: return False
                
                req = {
                    "query": text, "normalization": "basic", "language": "vi",
                    "audio_format": self.audio_format, "audio_quality": self.audio_quality,
                    "audio_speed": self.audio_speed, "speaker_id": self.speaker_id,
                    "model": self.model, "sample_rate": self.sample_rate,
                }
                await ws.send(json.dumps(req))
                header_skipped = False
                task_id = f"{session_id}_{idx}"
                seg_queue = self.segment_queues.get(task_id)
                if not seg_queue: return False

                while True:
                    if self.conn.client_abort or self.current_session_id != session_id: return True
                    message = await asyncio.wait_for(ws.recv(), timeout=FETCH_TIMEOUT)

                    if isinstance(message, bytes):
                        pcm_data = message
                        if not header_skipped:
                            if pcm_data[:4] == b"RIFF": pcm_data = pcm_data[WAV_HEADER_SIZE:]
                            header_skipped = True
                        if pcm_data: await seg_queue.put(pcm_data)
                    else:
                        data = json.loads(message)
                        status = data.get("type") or data.get("status")
                        if status == "finished-byte-stream": return True
                        if status in ("failed-request", "internal-error", "bad-request"):
                            return False
        except Exception:
            if pool_idx != -1:
                self.pool.mark_dead(pool_idx)
            return False

    def _schedule_fetch(self, idx, text, session_id, is_last=False):
        async def _tracked():
            task = asyncio.current_task()
            self._fetch_tasks.add(task)
            try: await self._fetch_with_retry(idx, text, session_id, is_last)
            finally: self._fetch_tasks.discard(task)
        asyncio.run_coroutine_threadsafe(_tracked(), self.conn.loop)

    def tts_text_priority_thread(self):
        logger.bind(tag=TAG).info("Blaze Speed V2 (Final): Active.")
        asyncio.run_coroutine_threadsafe(self._start_playback_worker(), self.conn.loop)

        while not self.conn.stop_event.is_set():
            try:
                message = self.tts_text_queue.get(timeout=1)
                if message.sentence_type == SentenceType.FIRST:
                    self.conn.client_abort = False
                    self.current_session_id += 1
                    self.tts_text_buff = []
                    self.processed_chars = 0
                    self.segment_counter = 0
                    self._flush_pipeline()
                    while not self.tts_text_queue.empty():
                        try: self.tts_text_queue.get_nowait()
                        except: break
                    logger.bind(tag=TAG).info(f"V2: Reset SID: {self.current_session_id}")

                if self.conn.client_abort: continue

                if ContentType.TEXT == message.content_type and message.content_detail:
                    self.tts_text_buff.append(message.content_detail)
                    while True:
                        segment = self._get_smart_segment()
                        if not segment: break
                        idx = self.segment_counter
                        self.segment_counter += 1
                        task_id = f"{self.current_session_id}_{idx}"
                        self.segment_queues[task_id] = asyncio.Queue()
                        asyncio.run_coroutine_threadsafe(
                            self.playback_queue.put((idx, idx==0, segment, self.current_session_id)),
                            self.conn.loop,
                        )
                        self._schedule_fetch(idx, segment, self.current_session_id, False)

                if message.sentence_type == SentenceType.LAST:
                    full_text = "".join(self.tts_text_buff)
                    remaining = full_text[self.processed_chars:]
                    if remaining.strip() and not self.conn.client_abort:
                        idx = self.segment_counter
                        self.segment_counter += 1
                        task_id = f"{self.current_session_id}_{idx}"
                        self.segment_queues[task_id] = asyncio.Queue()
                        asyncio.run_coroutine_threadsafe(
                            self.playback_queue.put((idx, idx==0, remaining, self.current_session_id)),
                            self.conn.loop,
                        )
                        self._schedule_fetch(idx, remaining, self.current_session_id, True)
                    self.conn.executor.submit(self._wait_for_all_and_finish, message.content_detail)
            except queue.Empty: continue
            except Exception as e: logger.bind(tag=TAG).error(f"V2 Master Error: {e}")

    def _get_smart_segment(self):
        full_text = "".join(self.tts_text_buff)
        text_to_process = full_text[self.processed_chars:]
        if not text_to_process: return None
        temp_text = self.emoji_pattern.sub(r"", text_to_process)
        words = temp_text.split()
        word_count = len(words)

        # Priority 1: Hard stops
        hard_stops = [".", "!", "?", "\n", "。", "！", "？"]
        for i, char in enumerate(text_to_process):
            if char in hard_stops:
                seg = text_to_process[:i+1].strip()
                if seg:
                    self.processed_chars += i + 1
                    return seg

        # Priority 2: Soft stops (8 words / 60 chars)
        soft_stops = [",", ":", ";", "，", "：", "；"]
        for i, char in enumerate(text_to_process):
            if char in soft_stops:
                if word_count >= 8 or i >= 60:
                    seg = text_to_process[:i+1].strip()
                    if seg:
                        self.processed_chars += i + 1
                        return seg

        # Priority 3: Hard limit (12 words / 100 chars)
        if word_count >= 12 or len(text_to_process) >= 100:
            limit = min(len(text_to_process), 100)
            last_space = text_to_process.rfind(" ", 0, limit)
            if last_space == -1: last_space = limit
            seg = text_to_process[:last_space].strip()
            if seg:
                self.processed_chars += last_space
                return seg
        return None

    def _wait_for_all_and_finish(self, content_detail):
        async def wait_loop():
            if self.playback_queue:
                await self.playback_queue.put("END_OF_SESSION")
                try: await asyncio.wait_for(self.playback_queue.join(), timeout=PLAYBACK_JOIN_TIMEOUT)
                except: pass
                await asyncio.sleep(0.2)
        future = asyncio.run_coroutine_threadsafe(wait_loop(), self.conn.loop)
        try: future.result(timeout=PLAYBACK_JOIN_TIMEOUT + 2)
        except: pass
        self.tts_audio_queue.put((SentenceType.LAST, [], content_detail))

    def text_to_speak(self, text, _): pass
    def to_tts(self, text: str) -> list: return [{"type": "tts", "text": text}]

    async def close(self):
        self._playback_active = False
        for task in list(self._fetch_tasks):
            if not task.done(): task.cancel()
        if self.playback_task: self.playback_task.cancel()
        await self.pool.close_all()
