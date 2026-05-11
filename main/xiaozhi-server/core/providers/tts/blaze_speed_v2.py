import json
import asyncio
import websockets
import ssl
import queue
import re

from config.logger import setup_logging
from core.utils.tts import MarkdownCleaner
from core.providers.tts.dto.dto import SentenceType, ContentType, InterfaceType
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()

# =============================================================================
# V2 BLAZE SPEED TTS — PRE-WARMED POOL + RETRY + FLUSH-AWARE PIPELINE
#
# Improvements over V1:
#   1. BlazeConnectionPool: Pre-warmed & self-healing WS pool (no cold-start)
#   2. Retry: Failed segments auto-retry on alternate WS (max 1 retry)
#   3. FLUSH: Explicit pipeline flush — cancel tasks + clear jitter buffer
#   4. Task tracking: All fetch tasks tracked for proper cancellation
#   5. Adaptive first segment: Smaller first segment for lower TTFB
# =============================================================================

INITIAL_BUFFER_BYTES = 9600     # ~400ms @ 24kHz/16bit/mono — first packet threshold
CONTINUOUS_JITTER_BYTES = 4800  # ~100ms continuous buffer
WAV_HEADER_SIZE = 44
POOL_SIZE = 4
FETCH_TIMEOUT = 15.0
POOL_HEALTH_INTERVAL = 5.0


# =============================================================================
# CONNECTION POOL: PRE-WARMED & SELF-HEALING
# =============================================================================
class BlazeConnectionPool:
    """
    Pre-warmed, self-healing WebSocket connection pool.
    Maintains N authenticated connections ready for immediate use.
    Background maintainer auto-revives dead connections.
    """

    def __init__(self, ws_url, token, pool_size=POOL_SIZE, ssl_context=None):
        self.ws_url = ws_url
        self.token = token
        self.pool_size = pool_size
        self.ssl_context = ssl_context
        self.pool = [None] * pool_size
        self.locks = [asyncio.Lock() for _ in range(pool_size)]
        self._maintain_task = None
        self._active = False

    async def _connect_and_auth(self, idx):
        """Create and authenticate a single WebSocket connection."""
        try:
            ws = await asyncio.wait_for(
                websockets.connect(
                    self.ws_url, ssl=self.ssl_context,
                    ping_interval=20.0, ping_timeout=10.0,
                ),
                timeout=10.0,
            )
            # Wait for successful-connection message
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            # Auth with streaming strategy (persistent connection)
            await ws.send(json.dumps({"token": self.token, "strategy": "streaming"}))
            auth_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)

            if "successful-authentication" not in str(auth_msg):
                logger.bind(tag=TAG).error(f"Pool[{idx}]: Auth failed: {auth_msg}")
                await ws.close()
                self.pool[idx] = None
                return False

            self.pool[idx] = ws
            logger.bind(tag=TAG).info(f"Pool[{idx}]: Pre-warmed & ready.")
            return True

        except Exception as e:
            logger.bind(tag=TAG).error(f"Pool[{idx}]: Warm-up failed: {e}")
            self.pool[idx] = None
            return False

    async def warm_up(self):
        """Pre-warm all connections in parallel at session start."""
        self._active = True
        tasks = [self._connect_and_auth(i) for i in range(self.pool_size)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ready = sum(1 for r in results if r is True)
        logger.bind(tag=TAG).info(f"Pool: {ready}/{self.pool_size} connections ready.")

    async def _maintain_loop(self):
        """Background task: revive dead connections automatically."""
        while self._active:
            try:
                for i in range(self.pool_size):
                    ws = self.pool[i]
                    if ws is None or getattr(ws, "closed", True):
                        if self._active:
                            await self._connect_and_auth(i)
                await asyncio.sleep(POOL_HEALTH_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.bind(tag=TAG).error(f"Pool maintain error: {e}")
                await asyncio.sleep(POOL_HEALTH_INTERVAL)

    def start_maintenance(self, loop):
        """Start the background health-check task."""
        self._maintain_task = loop.create_task(self._maintain_loop())

    async def get_connection(self, segment_idx):
        """
        Get a connection via round-robin with lock.
        Returns (pool_idx, ws). ws may be None if connection is dead.
        Caller MUST call release_connection() when done.
        """
        idx = segment_idx % self.pool_size
        await self.locks[idx].acquire()

        ws = self.pool[idx]
        if ws is None or getattr(ws, "closed", True):
            # Inline reconnect attempt
            await self._connect_and_auth(idx)
            ws = self.pool[idx]

        return idx, ws

    def release_connection(self, idx):
        """Release the lock on a pool slot."""
        try:
            self.locks[idx].release()
        except RuntimeError:
            pass  # Already released

    def mark_dead(self, idx):
        """Mark a connection as dead — maintainer will revive it."""
        self.pool[idx] = None

    async def close_all(self):
        """Shutdown pool: cancel maintainer, close all connections."""
        self._active = False
        if self._maintain_task and not self._maintain_task.done():
            self._maintain_task.cancel()
            try:
                await self._maintain_task
            except asyncio.CancelledError:
                pass

        for i, ws in enumerate(self.pool):
            if ws:
                try:
                    await ws.close()
                except Exception:
                    pass
            self.pool[i] = None


# =============================================================================
# TTS PROVIDER V2
# =============================================================================
class TTSProvider(TTSProviderBase):
    """
    V2 Blaze Speed TTS Provider.

    Architecture (Producer-Consumer Pipeline):
      LLM Text Stream → Smart Segmenter → Connection Pool (4x WS parallel)
                                              ↓
      Client ← Opus Encoder ← Jitter Buffer ← Audio Assembler (ordered)

    Key improvements:
      - Pre-warmed pool: 4 WS connected & authed at session start
      - Auto-retry: Failed segments retried on alternate WS
      - FLUSH pipeline: Cancel all pending tasks + clear jitter buffer on interrupt
      - Self-healing: Background task revives dead connections
    """

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

        # SSL
        ssl_ctx = ssl.create_default_context()
        if config.get("verify_ssl") is False:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        # Connection Pool (pre-warm happens in open_audio_channels)
        self.pool = BlazeConnectionPool(
            ws_url=self.ws_url, token=self.api_key,
            pool_size=POOL_SIZE, ssl_context=ssl_ctx,
        )

        self.emoji_pattern = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)

        # Async Orchestration
        self.playback_queue = None
        self.segment_queues = {}
        self.playback_task = None
        self._playback_active = False
        self._fetch_tasks = set()  # Track all active fetch asyncio.Tasks

    async def open_audio_channels(self, conn):
        """Override: pre-warm the connection pool at session start."""
        await super().open_audio_channels(conn)
        await self.pool.warm_up()
        self.pool.start_maintenance(conn.loop)

    # =========================================================================
    # CONSUMER: FLUSH-AWARE ORDERED PLAYBACK
    # =========================================================================
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

                # --- End of session: flush remaining buffer ---
                if item == "END_OF_SESSION":
                    if jitter_buffer:
                        self.opus_encoder.encode_pcm_to_opus_stream(
                            bytes(jitter_buffer), False, self.handle_opus
                        )
                        jitter_buffer.clear()
                    first_packet_sent = False
                    self.playback_queue.task_done()
                    continue

                # --- V2 FLUSH: clear jitter buffer immediately ---
                if item == "FLUSH":
                    jitter_buffer.clear()
                    first_packet_sent = False
                    self.playback_queue.task_done()
                    continue

                # --- Abort check (defensive) ---
                if self.conn.client_abort:
                    jitter_buffer.clear()
                    first_packet_sent = False
                    self.playback_queue.task_done()
                    continue

                idx, is_first, segment_text = item

                # Push text update when audio is about to play
                if is_first:
                    self.tts_audio_queue.put((SentenceType.FIRST, None, segment_text))
                else:
                    self.tts_audio_queue.put((SentenceType.MIDDLE, None, segment_text))

                seg_queue = self.segment_queues.get(idx)
                if not seg_queue:
                    self.playback_queue.task_done()
                    continue

                while True:
                    if self.conn.client_abort:
                        break

                    pcm_chunk = await seg_queue.get()
                    if pcm_chunk == b"END_OF_SEGMENT":
                        # Flush jitter on segment boundary if not started yet
                        if not first_packet_sent and jitter_buffer:
                            self.opus_encoder.encode_pcm_to_opus_stream(
                                bytes(jitter_buffer), False, self.handle_opus
                            )
                            jitter_buffer.clear()
                            first_packet_sent = True
                        seg_queue.task_done()
                        break

                    jitter_buffer.extend(pcm_chunk)

                    if not first_packet_sent:
                        if len(jitter_buffer) >= INITIAL_BUFFER_BYTES:
                            self.opus_encoder.encode_pcm_to_opus_stream(
                                bytes(jitter_buffer), False, self.handle_opus
                            )
                            jitter_buffer.clear()
                            first_packet_sent = True
                    else:
                        if len(jitter_buffer) >= CONTINUOUS_JITTER_BYTES:
                            self.opus_encoder.encode_pcm_to_opus_stream(
                                bytes(jitter_buffer), False, self.handle_opus
                            )
                            jitter_buffer.clear()

                    seg_queue.task_done()

                self.segment_queues.pop(idx, None)
                self.playback_queue.task_done()

            except asyncio.CancelledError:
                self._playback_active = False
                break
            except Exception as e:
                if self._playback_active:
                    logger.bind(tag=TAG).error(f"V2 Playback Error: {e}")
                    await asyncio.sleep(0.5)
                else:
                    break

    # =========================================================================
    # V2 FLUSH PIPELINE
    # =========================================================================
    def _flush_pipeline(self):
        """
        Full pipeline flush on interruption/new session:
        1. Cancel all pending fetch tasks
        2. Clear playback queue + send FLUSH signal to clear jitter buffer
        3. Clear all segment queues
        """
        # 1. Cancel all active fetch tasks
        for task in list(self._fetch_tasks):
            if not task.done():
                task.cancel()
        self._fetch_tasks.clear()

        # 2. Drain playback queue and send FLUSH
        if self.playback_queue:
            while not self.playback_queue.empty():
                try:
                    self.playback_queue.get_nowait()
                    self.playback_queue.task_done()
                except Exception:
                    break
            # FLUSH signal tells playback_loop to clear jitter_buffer
            try:
                self.playback_queue.put_nowait("FLUSH")
            except Exception:
                pass

        # 3. Clear all segment data queues
        for sq in self.segment_queues.values():
            while not sq.empty():
                try:
                    sq.get_nowait()
                except Exception:
                    break
        self.segment_queues.clear()

    # =========================================================================
    # PRODUCER: PARALLEL FETCH WITH RETRY
    # =========================================================================
    async def _fetch_with_retry(self, idx, text, is_last=False):
        """
        Wrapper: fetch audio for a segment, retry once on failure.
        Always sends END_OF_SEGMENT when done (success or final failure).
        """
        seg_queue = self.segment_queues.get(idx)
        if not seg_queue:
            return

        # Clean text for Blaze API
        text = self.emoji_pattern.sub(r"", text)
        text = text.replace("...", ",")
        allowed_chars = ".,?!:;，。！？；： "
        text = "".join(ch for ch in text if ch.isalnum() or ch in allowed_chars)

        if not any(ch.isalnum() for ch in text):
            await seg_queue.put(b"END_OF_SEGMENT")
            return

        if is_last and text and text[-1] not in ".?!":
            text = text + "."

        try:
            success = await self._do_fetch(idx, text, attempt=0)
            if not success and not self.conn.client_abort:
                logger.bind(tag=TAG).info(f"V2 Retrying Seg#{idx} on alternate WS...")
                await self._do_fetch(idx, text, attempt=1)
        except asyncio.CancelledError:
            logger.bind(tag=TAG).debug(f"V2 Fetch Seg#{idx} cancelled (FLUSH).")
        finally:
            await seg_queue.put(b"END_OF_SEGMENT")

    async def _do_fetch(self, idx, text, attempt=0):
        """
        Single fetch attempt. Returns True on success, False on failure.
        Uses attempt offset for round-robin to pick a different WS on retry.
        """
        pool_idx, ws = await self.pool.get_connection(idx + attempt)

        try:
            if not ws:
                logger.bind(tag=TAG).warning(f"V2 Fetch[{pool_idx}] Seg#{idx}: No connection.")
                return False

            req = {
                "query": text, "normalization": "basic", "language": "vi",
                "audio_format": self.audio_format, "audio_quality": self.audio_quality,
                "audio_speed": self.audio_speed, "speaker_id": self.speaker_id,
                "model": self.model, "sample_rate": self.sample_rate,
            }
            tag = f"V2 Fetch[{pool_idx}] Seg#{idx}{' (RETRY)' if attempt else ''}"
            logger.bind(tag=TAG).info(f"{tag}: {text[:50]}")

            await ws.send(json.dumps(req))
            header_skipped = False
            seg_queue = self.segment_queues.get(idx)
            if not seg_queue:
                return False

            while True:
                if self.conn.client_abort:
                    return True  # Treated as "handled"

                message = await asyncio.wait_for(ws.recv(), timeout=FETCH_TIMEOUT)

                if isinstance(message, bytes):
                    pcm_data = message
                    if not header_skipped:
                        if pcm_data[:4] == b"RIFF":
                            pcm_data = pcm_data[WAV_HEADER_SIZE:]
                        header_skipped = True
                    if pcm_data:
                        await seg_queue.put(pcm_data)
                else:
                    data = json.loads(message)
                    status = data.get("type") or data.get("status")
                    if status == "finished-byte-stream":
                        return True
                    elif status in ("failed-request", "internal-error", "bad-request"):
                        logger.bind(tag=TAG).error(f"{tag} API error: {data}")
                        return False

        except websockets.exceptions.ConnectionClosed as e:
            logger.bind(tag=TAG).warning(f"V2 Fetch[{pool_idx}] Seg#{idx} WS closed: {e}")
            self.pool.mark_dead(pool_idx)
            return False
        except asyncio.TimeoutError:
            logger.bind(tag=TAG).error(f"V2 Fetch[{pool_idx}] Seg#{idx} timeout.")
            self.pool.mark_dead(pool_idx)
            return False
        except asyncio.CancelledError:
            raise  # Propagate to _fetch_with_retry
        except Exception as e:
            logger.bind(tag=TAG).error(f"V2 Fetch[{pool_idx}] Seg#{idx} error: {e}")
            self.pool.mark_dead(pool_idx)
            return False
        finally:
            self.pool.release_connection(pool_idx)

    def _schedule_fetch(self, idx, text, is_last=False):
        """Schedule a fetch as a tracked asyncio.Task (cancellable via FLUSH)."""
        async def _tracked():
            task = asyncio.current_task()
            self._fetch_tasks.add(task)
            try:
                await self._fetch_with_retry(idx, text, is_last)
            finally:
                self._fetch_tasks.discard(task)

        asyncio.run_coroutine_threadsafe(_tracked(), self.conn.loop)

    # =========================================================================
    # MASTER THREAD: TEXT FLOW MANAGEMENT
    # =========================================================================
    def tts_text_priority_thread(self):
        logger.bind(tag=TAG).info("Blaze Speed V2: Master Pipeline active.")
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
                    self._flush_pipeline()
                    logger.bind(tag=TAG).info("V2: Session Reset (FLUSH).")

                if self.conn.client_abort:
                    continue

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
                            self.conn.loop,
                        )
                        self.is_first_segment = False
                        self._schedule_fetch(idx, segment, False)

                if message.sentence_type == SentenceType.LAST:
                    full_text = "".join(self.tts_text_buff)
                    remaining = full_text[self.processed_chars:]
                    if remaining.strip() and not self.conn.client_abort:
                        idx = self.segment_counter
                        self.segment_counter += 1

                        self.segment_queues[idx] = asyncio.Queue()
                        asyncio.run_coroutine_threadsafe(
                            self.playback_queue.put((idx, self.is_first_segment, remaining)),
                            self.conn.loop,
                        )
                        self.is_first_segment = False
                        self._schedule_fetch(idx, remaining, True)

                    self.conn.executor.submit(
                        self._wait_for_all_and_finish, message.content_detail
                    )

            except queue.Empty:
                continue
            except Exception as e:
                logger.bind(tag=TAG).error(f"V2 Master Thread Error: {e}")

    # =========================================================================
    # SMART SEGMENTER
    # =========================================================================
    def _get_smart_segment(self):
        """
        Smart text segmenter for minimal TTFB:
        - Priority 1: Hard stops (. ! ? \\n) — split immediately
        - Priority 2: Soft stops (, : ;) — split if >= 10 words
        - Priority 3: Word boundary fallback — split at 25 words
        """
        full_text = "".join(self.tts_text_buff)
        text_to_process = full_text[self.processed_chars:]
        if not text_to_process:
            return None

        temp_text = self.emoji_pattern.sub(r"", text_to_process)
        words = temp_text.split()
        word_count = len(words)

        # Priority 1: Hard stops — split immediately
        hard_stops = [".", "!", "?", "\n", "。", "！", "？"]
        for i, char in enumerate(text_to_process):
            if char in hard_stops:
                seg = text_to_process[: i + 1].strip()
                if seg:
                    self.processed_chars += i + 1
                    return seg

        # Priority 2: Soft stops — only if enough words accumulated
        soft_stops = [",", ":", ";", "，", "：", "；"]
        for i, char in enumerate(text_to_process):
            if char in soft_stops:
                if word_count >= 10:
                    seg = text_to_process[: i + 1].strip()
                    if seg:
                        self.processed_chars += i + 1
                        return seg

        # Priority 3: Word boundary fallback at 25 words
        if word_count >= 25:
            last_space = text_to_process.rfind(" ")
            if last_space != -1:
                seg = text_to_process[:last_space].strip()
                if seg:
                    self.processed_chars += last_space + 1
                    return seg

        return None

    # =========================================================================
    # SESSION END
    # =========================================================================
    def _wait_for_all_and_finish(self, content_detail):
        """Wait for all segments to finish playing, then signal LAST."""

        async def wait_loop():
            if self.playback_queue:
                await self.playback_queue.put("END_OF_SESSION")
                try:
                    await asyncio.wait_for(self.playback_queue.join(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.bind(tag=TAG).warning("V2: playback_queue.join() timeout!")
                await asyncio.sleep(0.5)

        future = asyncio.run_coroutine_threadsafe(wait_loop(), self.conn.loop)
        try:
            future.result(timeout=12)
        except Exception:
            if self._playback_active and not self.conn.stop_event.is_set():
                logger.bind(tag=TAG).warning("V2: Wait loop timeout!")

        self.tts_audio_queue.put((SentenceType.LAST, [], content_detail))

    # =========================================================================
    # INTERFACE STUBS
    # =========================================================================
    def text_to_speak(self, text, _):
        pass

    def to_tts(self, text: str) -> list:
        return [{"type": "tts", "text": text}]

    # =========================================================================
    # CLEANUP
    # =========================================================================
    async def close(self):
        """Graceful shutdown: cancel all tasks, close pool."""
        self._playback_active = False

        # Cancel all fetch tasks
        for task in list(self._fetch_tasks):
            if not task.done():
                task.cancel()
        self._fetch_tasks.clear()

        # Cancel playback task
        if self.playback_task and not self.playback_task.done():
            self.playback_task.cancel()

        # Close connection pool
        await self.pool.close_all()
