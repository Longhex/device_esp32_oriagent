import re
import time
import json
import asyncio
import websockets
import ssl
import queue
from contextlib import asynccontextmanager

from config.logger import setup_logging
from core.utils.tts import MarkdownCleaner
from core.utils import perf_metrics
from core.providers.tts.dto.dto import SentenceType, ContentType, InterfaceType
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()

# =============================================================================
# V2 BLAZE SPEED TTS — PRODUCTION GRADE (100% RELIABILITY)
# =============================================================================

INITIAL_BUFFER_BYTES = 14400    # ~300ms @ 24kHz/16bit/mono (Fix 1: was 200ms)
CONTINUOUS_JITTER_BYTES = 14400 # ~300ms continuous buffer (Fix 1: was 100ms, chịu được TTFB jitter ~300ms)
WAV_HEADER_SIZE = 44
POOL_SIZE = 8  # Higher capacity for simultaneous segments
FETCH_TIMEOUT = 10.0
POOL_HEALTH_INTERVAL = 5.0      # Fix 3: maintenance loop check mỗi 5s (was: 30s vì timeout=interval*6)
PLAYBACK_JOIN_TIMEOUT = 30.0
SEGMENT_FETCH_TIMEOUT = 25.0  # Increased to allow Producer retries (10s+10s+5s)
FETCH_CONCURRENCY = 3           # Fix 2: max 3 segment fetches song song (chống rate-limit Blaze)
UNDERRUN_THRESHOLD_MS = 100     # Fix 4: gap audio playback > 100ms coi là underrun
KEEPALIVE_IDLE_SEC = 25.0       # Fix 5: gửi ping nếu connection idle quá ngưỡng này

# Task 3.1 — Health thresholds
MAX_RETRY_ATTEMPTS = 3           # was 2, now 3 với backoff
RETRY_BACKOFF_MS = (0, 200, 600) # ms để chờ trước mỗi attempt
HEALTH_WINDOW_SIZE = 20          # rolling window cho outcomes gần đây
DEGRADED_FAIL_RATIO = 0.4        # >40% fail trong window → degraded
DEGRADED_CONSECUTIVE = 3         # 3 fail liên tiếp → degraded ngay
DEGRADED_LOG_INTERVAL = 30.0     # giây — chống log spam khi degraded kéo dài


class _HealthMonitor:
    """
    Track outcomes (success/fail) của Blaze fetch để phát hiện degradation sớm.
    Khi degraded → emit perf_metric `blaze_health_degraded` + log critical.
    Auto-recover khi có streak success.

    Trạng thái dùng để ops/dashboards quyết định failover thủ công sang TTS khác.
    Auto-swap provider để Phase 4 — cần monitoring stack thật để xác nhận.
    """
    __slots__ = ("recent", "consecutive_fail", "is_degraded", "_last_log_ts", "_lock_unused")

    def __init__(self):
        from collections import deque
        self.recent: deque[bool] = deque(maxlen=HEALTH_WINDOW_SIZE)  # True=success
        self.consecutive_fail = 0
        self.is_degraded = False
        self._last_log_ts = 0.0

    def record_outcome(self, success: bool, text_len: int, attempt: int) -> None:
        self.recent.append(success)
        if success:
            self.consecutive_fail = 0
        else:
            self.consecutive_fail += 1

        # Evaluate state
        n = len(self.recent)
        fails = sum(1 for x in self.recent if not x)
        fail_ratio = fails / n if n else 0.0
        degraded_now = (
            self.consecutive_fail >= DEGRADED_CONSECUTIVE
            or (n >= HEALTH_WINDOW_SIZE // 2 and fail_ratio >= DEGRADED_FAIL_RATIO)
        )

        if degraded_now and not self.is_degraded:
            self.is_degraded = True
            logger.bind(tag=TAG).error(
                f"[ALERT] BLAZE TTS DEGRADED -- consecutive_fail={self.consecutive_fail}, "
                f"fail_ratio={fail_ratio:.0%} ({fails}/{n})"
            )
            perf_metrics.record(
                "blaze_health_degraded", float(self.consecutive_fail),
                fail_ratio=round(fail_ratio, 2), window_n=n,
            )
            self._last_log_ts = time.time()
        elif not degraded_now and self.is_degraded:
            self.is_degraded = False
            logger.bind(tag=TAG).info(
                f"[OK] Blaze TTS recovered -- last {n} requests, fail_ratio={fail_ratio:.0%}"
            )
            perf_metrics.record("blaze_health_recovered", 0.0, window_n=n)
        elif degraded_now and (time.time() - self._last_log_ts) > DEGRADED_LOG_INTERVAL:
            # Re-emit periodic so dashboards thấy still-degraded
            logger.bind(tag=TAG).warning(
                f"Blaze TTS still degraded — fail_ratio={fail_ratio:.0%}, "
                f"consec_fail={self.consecutive_fail}"
            )
            perf_metrics.record(
                "blaze_health_degraded", float(self.consecutive_fail),
                fail_ratio=round(fail_ratio, 2), window_n=n,
            )
            self._last_log_ts = time.time()

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
        # Fix 5: track last activity time per slot để biết slot nào idle quá lâu
        self.last_activity: list[float] = [0.0] * pool_size

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
                    ping_interval=30.0, ping_timeout=30.0,
                ),
                timeout=5.0,
            )
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            await ws.send(json.dumps({"token": self.token, "strategy": "request"}))
            auth_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)

            if "successful-authentication" not in str(auth_msg):
                logger.bind(tag=TAG).error(f"Pool[{idx}]: Auth failed.")
                await ws.close()
                return False

            self.pool[idx] = ws
            self.last_activity[idx] = time.time()  # Fix 5: mark fresh
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
                now = time.time()
                for i in range(self.pool_size):
                    async with self.locks[i]: # PREVENT RACE CONDITION with get_connection
                        ws = self.pool[i]
                        if ws is None or getattr(ws, "closed", True):
                            await self._connect_and_auth(i)
                        else:
                            # Fix 5: gửi ping nếu idle quá lâu, giữ WS alive xuyên qua server-side timeout
                            idle_sec = now - self.last_activity[i]
                            if idle_sec > KEEPALIVE_IDLE_SEC:
                                try:
                                    pong = await ws.ping()
                                    await asyncio.wait_for(pong, timeout=3.0)
                                    self.last_activity[i] = now
                                    logger.bind(tag=TAG).debug(
                                        f"Pool[{i}]: keepalive ping OK (idle was {idle_sec:.0f}s)"
                                    )
                                except Exception as e:
                                    logger.bind(tag=TAG).warning(
                                        f"Pool[{i}]: ping failed ({e}), marking dead"
                                    )
                                    try: await ws.close()
                                    except: pass
                                    self.pool[i] = None
                                    await self._connect_and_auth(i)

                # Fix 3: timeout = POOL_HEALTH_INTERVAL (5s) thay vì *6 (30s)
                # → phát hiện connection chết nhanh hơn 6×, giảm cold handshake cho turn tiếp
                await asyncio.wait_for(self._maintain_event.wait(), timeout=POOL_HEALTH_INTERVAL)
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
            self.last_activity[target_idx] = time.time()  # Fix 5: mark fresh on use
            yield target_idx, self.pool[target_idx]
        finally:
            self.last_activity[target_idx] = time.time()  # Fix 5: mark fresh after release
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
        self.audio_speed = config.get("audio_speed", "1.2")
        self.audio_format = "opus"
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

        # Task 3.1 — Health monitor
        self.health = _HealthMonitor()

        # Fix 2 — Semaphore giới hạn concurrent fetch. Tránh Blaze rate-limit per-key
        # khi LLM stream nhiều segments cùng lúc (smart-segment hạ 150→80 ở Phase 1).
        # Lazy-init trong open_audio_channels vì cần event loop.
        self._fetch_semaphore: asyncio.Semaphore | None = None

    async def open_audio_channels(self, conn):
        await super().open_audio_channels(conn)
        await self.pool.warm_up()
        self.pool.start_maintenance(conn.loop)
        # Fix 2: lazy-init semaphore (cần event loop đã chạy)
        if self._fetch_semaphore is None:
            self._fetch_semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
            logger.bind(tag=TAG).info(
                f"Blaze fetch semaphore initialized (max concurrent={FETCH_CONCURRENCY})"
            )

    async def _start_playback_worker(self):
        if self.playback_queue is None:
            self.playback_queue = asyncio.Queue()
            self._playback_active = True
            self.playback_task = self.conn.loop.create_task(self._playback_loop())

    async def _playback_loop(self):
        jitter_buffer = bytearray()
        first_packet_sent = False
        last_segment_complete_ts: float | None = None  # Fix 4: track gap giữa segments

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
                    last_segment_complete_ts = None  # reset cho session mới
                else:
                    self.tts_audio_queue.put((SentenceType.MIDDLE, None, segment_text))
                    # Fix 4: đo gap giữa segment trước hoàn thành và segment này bắt đầu
                    if last_segment_complete_ts is not None:
                        gap_ms = (time.perf_counter() - last_segment_complete_ts) * 1000
                        if gap_ms > UNDERRUN_THRESHOLD_MS:
                            logger.bind(tag=TAG).warning(
                                f"V2 UNDERRUN: gap {gap_ms:.0f}ms before segment #{idx} "
                                f"(client se nghe khung audio)"
                            )
                            perf_metrics.record(
                                "blaze_underrun_ms", gap_ms,
                                idx=idx, session=str(session_id),
                            )

                seg_queue = self.segment_queues.get(task_id)
                if not seg_queue:
                    self.playback_queue.task_done()
                    continue

                try:
                    while True:
                        if self.conn.client_abort or self.current_session_id != session_id: break
                        try:
                            audio_chunk = await asyncio.wait_for(seg_queue.get(), timeout=SEGMENT_FETCH_TIMEOUT)
                        except asyncio.TimeoutError:
                            logger.bind(tag=TAG).warning(f"V2: Segment #{task_id} timeout.")
                            break

                        if audio_chunk == b"END_OF_SEGMENT":
                            # No jitter buffer to flush anymore
                            seg_queue.task_done()
                            first_packet_sent = True
                            last_segment_complete_ts = time.perf_counter()  # Fix 4: mark segment xong
                            break

                        # Bắn thẳng Ogg/Opus chunk từ server xuống ESP32 không qua nén
                        self.handle_opus(audio_chunk)
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

        # Fix 2: lazy-init semaphore (cần event loop)
        if self._fetch_semaphore is None:
            self._fetch_semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

        success = False
        attempt = 0
        t_queue = time.perf_counter()
        try:
            # Throttle concurrent fetches → chống Blaze rate-limit per-key
            async with self._fetch_semaphore:
                queue_wait_ms = (time.perf_counter() - t_queue) * 1000
                if queue_wait_ms > 50:
                    perf_metrics.record(
                        "blaze_fetch_queue_ms", queue_wait_ms,
                        idx=idx, text_len=len(text),
                    )

                for attempt in range(MAX_RETRY_ATTEMPTS):
                    if self.conn.client_abort or self.current_session_id != session_id:
                        break
                    backoff_ms = RETRY_BACKOFF_MS[attempt] if attempt < len(RETRY_BACKOFF_MS) else 1000
                    if backoff_ms > 0:
                        await asyncio.sleep(backoff_ms / 1000.0)

                    success = await self._do_fetch(idx, text, session_id, attempt=attempt)
                    if success:
                        break
                    if attempt + 1 < MAX_RETRY_ATTEMPTS:
                        next_backoff = RETRY_BACKOFF_MS[min(attempt + 1, len(RETRY_BACKOFF_MS) - 1)]
                        logger.bind(tag=TAG).warning(
                            f"V2: segment #{idx} fetch failed attempt={attempt}, "
                            f"backing off {next_backoff}ms"
                        )

            # Record outcome (sau khi release semaphore)
            self.health.record_outcome(success=success, text_len=len(text), attempt=attempt)

            if not success:
                logger.bind(tag=TAG).error(
                    f"[ALERT] Blaze fetch GIVE UP segment #{idx} sau {MAX_RETRY_ATTEMPTS} attempts. "
                    f"Segment bi skip -- user se thieu 1 doan audio."
                )
                perf_metrics.record(
                    "blaze_segment_dropped", float(MAX_RETRY_ATTEMPTS),
                    text_len=len(text), idx=idx,
                )
        except asyncio.CancelledError:
            pass
        finally:
            await seg_queue.put(b"END_OF_SEGMENT")

    async def _do_fetch(self, idx, text, session_id, attempt=0):
        pool_idx = -1
        ttfb_recorded = False
        t_send = None
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
                t_send = time.perf_counter()
                await ws.send(json.dumps(req))

                # Protocol from demo: processing-request -> started-byte-stream -> chunks
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=FETCH_TIMEOUT)
                    # Skip 'processing-request' if it arrives
                    if not isinstance(msg, bytes) and "processing-request" in str(msg):
                        msg = await asyncio.wait_for(ws.recv(), timeout=FETCH_TIMEOUT)
                    # Skip 'started-byte-stream' if it arrives
                    if not isinstance(msg, bytes) and "started-byte-stream" in str(msg):
                        pass
                except: pass

                header_skipped = False
                task_id = f"{session_id}_{idx}"
                seg_queue = self.segment_queues.get(task_id)
                if not seg_queue: return False

                while True:
                    if self.conn.client_abort or self.current_session_id != session_id: return True
                    message = await asyncio.wait_for(ws.recv(), timeout=FETCH_TIMEOUT)

                    if isinstance(message, bytes):
                        if not ttfb_recorded and t_send is not None:
                            ttfb_ms = (time.perf_counter() - t_send) * 1000
                            perf_metrics.record(
                                "blaze_ttfb_ms", ttfb_ms,
                                attempt=attempt, text_len=len(text),
                                session=str(session_id),
                            )
                            ttfb_recorded = True
                        # Using raw PCM from server - no header to skip
                        await seg_queue.put(message)
                    else:
                        data = json.loads(message)
                        status = data.get("type") or data.get("status")
                        if status == "finished-byte-stream":
                            if t_send is not None:
                                total_ms = (time.perf_counter() - t_send) * 1000
                                perf_metrics.record(
                                    "blaze_total_ms", total_ms,
                                    attempt=attempt, text_len=len(text),
                                )
                            return True
                        if status in ("failed-request", "internal-error", "bad-request"):
                            perf_metrics.record(
                                "blaze_error_ms",
                                (time.perf_counter() - t_send) * 1000 if t_send else 0,
                                attempt=attempt, status=str(status), text_len=len(text),
                            )
                            return False
        except Exception as e:
            if pool_idx != -1:
                self.pool.mark_dead(pool_idx)
            perf_metrics.record(
                "blaze_exception_ms",
                (time.perf_counter() - t_send) * 1000 if t_send else 0,
                attempt=attempt, error=type(e).__name__, text_len=len(text),
            )
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
        """
        Tách câu cho TTS theo 3 mức ưu tiên:
        1) Hard stop  (. ! ? 。 ！ ？ \n)                — cắt ngay khi gặp
        2) Soft stop  (, ; : ， ； ：) nếu đoạn ≥ 40 ký tự — cắt theo nhịp tự nhiên
        3) Force      nếu đoạn ≥ 80 ký tự                — chống buffer overflow

        Lý do hạ 150→80 và thêm soft-stop: với LLM Dify thường non-streaming
        (xem Phase 2 plan), TTS phải chia đoạn càng sớm càng tốt để giảm TTFA pipeline.
        Soft-stop giúp giữ ngữ điệu tự nhiên thay vì cắt giữa cụm.
        """
        full_text = "".join(self.tts_text_buff)
        text_to_process = full_text[self.processed_chars:]
        if not text_to_process: return None

        hard_stops = (".", "!", "?", "\n", "。", "！", "？")
        soft_stops = (",", ";", ":", "，", "；", "：")
        MIN_SOFT_LEN = 40
        FORCE_SEG_LEN = 80
        FORCE_LIMIT = 60

        soft_idx = -1
        for i, char in enumerate(text_to_process):
            if char in hard_stops:
                seg = text_to_process[:i+1].strip()
                if seg:
                    self.processed_chars += i + 1
                    return seg
            elif soft_idx < 0 and char in soft_stops and (i + 1) >= MIN_SOFT_LEN:
                soft_idx = i  # ghi nhận soft-stop ĐẦU TIÊN sau ngưỡng

        # Priority 2: Soft stop (dấu phẩy/chấm phẩy) — chỉ kích hoạt khi đoạn đã đủ dài
        if soft_idx >= 0:
            seg = text_to_process[:soft_idx + 1].strip()
            if seg:
                self.processed_chars += soft_idx + 1
                return seg

        # Priority 3: Force segment khi text quá dài
        if len(text_to_process) >= FORCE_SEG_LEN:
            last_space = text_to_process.rfind(" ", 0, FORCE_LIMIT)
            if last_space == -1: last_space = FORCE_LIMIT
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
