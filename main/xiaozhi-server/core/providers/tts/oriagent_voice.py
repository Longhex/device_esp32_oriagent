import re
import time
import json
import asyncio
import ssl
import queue
from urllib.parse import urlencode, urlsplit

import httpx
import websockets

from config.logger import setup_logging
from core.utils import perf_metrics
from core.providers.tts.dto.dto import SentenceType, ContentType, InterfaceType
from core.providers.tts.base import TTSProviderBase
from core.utils.tts import MarkdownCleaner
from core.handle.sendAudioHandle import send_tts_message

TAG = __name__
logger = setup_logging()

# Cache toàn cục: base URL nào đã xác nhận WS realtime 404 -> mọi instance/phiên sau
# bỏ qua WS ngay, đi thẳng blocking (tiết kiệm ~1s probe WS cho mỗi câu trả lời đầu).
_WS_DEAD_BASES = set()

# =============================================================================
# ORIAGENT VOICE TTS — WebSocket realtime (VoxCPM Voice Clone TTS API v1)
#
# Khác Blaze ở chỗ KHÔNG mở WS trực tiếp bằng api_key. Luồng 2 bước:
#   1) POST {base}/tts/stream-token  (Bearer api_key, {"text_length": N})
#        -> { stream_token, ws_url, expires_in: 60, ... }
#   2) WS  {ws_url}?token={stream_token}
#        client gửi {"type":"start", text, language, ...}
#        server trả  {"type":"start","format":"pcm16","sample_rate":24000}
#                    -> binary PCM16 chunks
#                    -> {"type":"done"} | {"type":"error"}
#
# Nguyên tắc cốt lõi của API: MỖI API KEY = MỘT GIỌNG. Không gửi voice_id.
# Vì vậy danh sách giọng được lưu ở config dưới dạng:
#   voices: [{name, language, api_key}, ...]
# Giọng agent chọn (private_voice = TÊN giọng) -> resolve sang api_key tương ứng.
#
# Token sống 60s + quota trừ ngay khi lấy token -> KHÔNG pre-warm pool như Blaze.
# Mỗi segment tự lấy token mới + mở WS riêng (vẫn fetch song song nhiều segment).
# =============================================================================

INITIAL_BUFFER_BYTES = 14400     # ~300ms @ 24kHz/16bit/mono — buffer trước packet đầu
CONTINUOUS_JITTER_BYTES = 14400  # ~300ms — buffer liên tục, chịu jitter mạng
# Lead-in: chèn ~250ms im lặng TRƯỚC audio thật của segment đầu để che giai đoạn
# DAC/amp ESP32 ramp-up (nếu không, âm tiết đầu bị clip).
LEAD_IN_SILENCE_BYTES = 12000

FETCH_CONCURRENCY = 3            # giới hạn token+WS song song (rate limit 100 req/min/key)
TOKEN_TIMEOUT = 8.0             # timeout REST lấy stream-token
WS_CONNECT_TIMEOUT = 6.0       # timeout mở WebSocket
WS_RECV_TIMEOUT = 12.0         # timeout chờ mỗi frame audio
SEGMENT_FETCH_TIMEOUT = 25.0  # timeout playback chờ chunk từ seg_queue
PLAYBACK_JOIN_TIMEOUT = 30.0
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_MS = (0, 200, 600)

DEFAULT_API_BASE = "https://voice.oriagent.com/api/v1"


def _normalize_api_base(api_url: str) -> str:
    """Chuẩn hóa api_url của model về base (…/api/v1).

    Chấp nhận base (…/api/v1) hoặc full URL (…/tts/stream-token / …/tts/generate).
    """
    base = (api_url or DEFAULT_API_BASE).strip().rstrip("/")
    for suffix in ("/tts/stream-token", "/tts/generate"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.interface_type = InterfaceType.DUAL_STREAM

        self.api_base = _normalize_api_base(config.get("api_url"))
        self.token_url = f"{self.api_base}/tts/stream-token"
        self.generate_url = f"{self.api_base}/tts/generate"
        # Endpoint WS realtime có thể chưa được deploy (server trả ws_url 404).
        # Nếu base này đã bị xác nhận 404 ở phiên trước -> bỏ qua WS ngay (không probe lại).
        self._ws_disabled = self.api_base in _WS_DEAD_BASES
        self._ws_warned = False

        # ── Resolve giọng -> api_key (mỗi api_key là một giọng riêng) ──────────
        # voices: danh sách [{name, language, api_key}] lưu trong config model.
        # private_voice (hoặc voice) = TÊN giọng agent đã chọn.
        voices = config.get("voices")
        if not isinstance(voices, list):
            voices = []
        # lọc bỏ entry rỗng
        voices = [v for v in voices if isinstance(v, dict) and (v.get("api_key") or v.get("name"))]

        selected_name = config.get("private_voice") or config.get("voice")
        chosen = None
        if selected_name:
            for v in voices:
                if str(v.get("name")) == str(selected_name):
                    chosen = v
                    break
        if chosen is None and voices:
            chosen = voices[0]  # mặc định: giọng đầu tiên
        if chosen is None:
            # backward-compat: config phẳng kiểu cũ (api_key/voice ở top-level)
            chosen = {
                "name": selected_name or "",
                "api_key": config.get("api_key", ""),
                "language": config.get("language", "auto"),
            }

        self.voice_name = chosen.get("name") or ""
        self.api_key = chosen.get("api_key") or ""
        lang = chosen.get("language") or config.get("language") or "auto"
        self.language = "auto" if str(lang).strip().lower() in ("", "auto") else str(lang).strip()

        # Tham số tổng hợp (theo doc VoxCPM)
        self.cfg_value = config.get("cfg_value", 2.0)
        # Chiến thuật fast-start: segment đầu dùng ít bước diffusion hơn để giảm TTFB
        # (audio ra sớm), các segment sau dùng nhiều bước hơn cho chất lượng — độ trễ
        # thêm bị che khuất vì fetch song song trong lúc segment trước đang phát.
        self.dit_steps = config.get("dit_steps", 8)
        self.dit_steps_first = config.get("dit_steps_first", 6)
        self.streaming_mode = config.get("streaming_mode", "stable")
        self.control_instruction = config.get("control_instruction", "")

        # Lead-in silence (ms) chèn trước câu đầu để che DAC/amp ramp-up (chống clip âm
        # tiết đầu). Tăng nếu thiết bị vẫn bị mất chữ đầu. Tính ra bytes ở open_audio_channels.
        self.lead_in_silence_ms = int(config.get("lead_in_silence_ms", 500))
        self._lead_in_bytes = LEAD_IN_SILENCE_BYTES

        self._verify_ssl = config.get("verify_ssl") is not False
        self._ssl_ctx = ssl.create_default_context()
        if not self._verify_ssl:
            self._ssl_ctx.check_hostname = False
            self._ssl_ctx.verify_mode = ssl.CERT_NONE

        self.emoji_pattern = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)

        # State pipeline (giống Blaze v2)
        self.playback_queue = None
        self.segment_queues = {}
        self.playback_task = None
        self._playback_active = False
        self._fetch_tasks = set()
        self.current_session_id = 0
        self.processed_chars = 0
        self.segment_counter = 0
        self._fetch_semaphore = None
        self._http = None  # httpx.AsyncClient, lazy-init trong event loop

        # ── Prewarm WS (đòn #1: giấu token+connect khỏi TTFA segment đầu) ──────
        # Mở sẵn stream-token + WebSocket ngay đầu turn (song song LLM), segment 0
        # tái dùng -> tiết kiệm ~200ms token+connect. Tắt bằng enable_ws_prewarm=false
        # nếu muốn tiết kiệm quota (token prewarm trừ theo prewarm_text_length).
        self._prewarm_enabled = config.get("enable_ws_prewarm", True) is not False
        self._prewarm_chars = int(config.get("prewarm_text_length", 200))
        self._prewarm_max_age = 25.0  # giây; token sống 60s, nginx idle ~30s -> coi stale sớm
        self._prewarmed = None  # (ws, session_id, monotonic_ts) hoặc None

        if not self.api_key:
            logger.bind(tag=TAG).warning(
                "Oriagent Voice TTS: chưa resolve được api_key (voices rỗng?) — TTS sẽ lỗi khi gọi."
            )

    async def open_audio_channels(self, conn):
        await super().open_audio_channels(conn)
        # Lead-in silence theo sample_rate thực tế của thiết bị.
        self._lead_in_bytes = max(0, int(conn.sample_rate * 2 * self.lead_in_silence_ms / 1000))
        if self._fetch_semaphore is None:
            self._fetch_semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=TOKEN_TIMEOUT, verify=self._verify_ssl, follow_redirects=True)
        logger.bind(tag=TAG).info(
            f"Oriagent Voice TTS active — voice='{self.voice_name}', lang='{self.language}', "
            f"token_url={self.token_url}"
        )

    # ── Playback worker (gom PCM16 -> jitter buffer -> Opus) ──────────────────
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
                        valid_len = len(jitter_buffer) - (len(jitter_buffer) % 2)
                        if valid_len > 0:
                            self.opus_encoder.encode_pcm_to_opus_stream(
                                bytes(jitter_buffer[:valid_len]), True, self.handle_opus
                            )
                    else:
                        self.opus_encoder.reset_state()
                    jitter_buffer.clear()
                    first_packet_sent = False
                    self.playback_queue.task_done()
                    continue

                if item == "FLUSH":
                    jitter_buffer.clear()
                    self.opus_encoder.reset_state()
                    first_packet_sent = False
                    self.playback_queue.task_done()
                    continue

                if self.conn.client_abort:
                    jitter_buffer.clear()
                    self.playback_queue.task_done()
                    continue

                if not (isinstance(item, tuple) and len(item) == 5):
                    self.playback_queue.task_done()
                    continue

                idx, is_first, segment_text, session_id, seg_end_offset = item
                task_id = f"{session_id}_{idx}"

                if self.current_session_id != session_id:
                    self.playback_queue.task_done()
                    continue

                if is_first:
                    # Khởi tạo pipeline audio (rate controller) — KHÔNG gửi text ở đây nữa.
                    self.tts_audio_queue.put((SentenceType.FIRST, None, None))
                    if not first_packet_sent:
                        jitter_buffer.extend(b"\x00" * self._lead_in_bytes)

                # Text của segment được gửi NGAY KHI audio bắt đầu phát (lúc encode opus đầu
                # tiên của segment), cho MỌI segment -> client nhận đủ text cả câu, đồng bộ audio.
                seg_text_sent = False

                async def _emit_seg_text():
                    nonlocal seg_text_sent
                    if not seg_text_sent and segment_text and segment_text.strip():
                        await send_tts_message(self.conn, "sentence_start", segment_text)
                        seg_text_sent = True
                        # Show ảnh gắn với vị trí <= cuối segment này -> đồng bộ audio.
                        try:
                            self.conn.fire_pending_images_up_to(seg_end_offset)
                        except Exception as _e:
                            logger.bind(tag=TAG).warning(f"fire_pending_images lỗi: {_e}")

                seg_queue = self.segment_queues.get(task_id)
                if not seg_queue:
                    self.playback_queue.task_done()
                    continue

                try:
                    while True:
                        if self.conn.client_abort or self.current_session_id != session_id:
                            break
                        try:
                            pcm_chunk = await asyncio.wait_for(
                                seg_queue.get(), timeout=SEGMENT_FETCH_TIMEOUT
                            )
                        except asyncio.TimeoutError:
                            logger.bind(tag=TAG).warning(f"Segment #{task_id} timeout chờ PCM.")
                            break

                        if pcm_chunk == b"END_OF_SEGMENT":
                            if len(jitter_buffer) > 0:
                                valid_len = len(jitter_buffer) - (len(jitter_buffer) % 2)
                                if valid_len > 0:
                                    await _emit_seg_text()
                                    self.opus_encoder.encode_pcm_to_opus_stream(
                                        bytes(jitter_buffer[:valid_len]), False, self.handle_opus
                                    )
                                    del jitter_buffer[:valid_len]
                            seg_queue.task_done()
                            first_packet_sent = True
                            break

                        jitter_buffer.extend(pcm_chunk)
                        if not first_packet_sent:
                            if len(jitter_buffer) >= INITIAL_BUFFER_BYTES:
                                valid_len = len(jitter_buffer) - (len(jitter_buffer) % 2)
                                await _emit_seg_text()
                                self.opus_encoder.encode_pcm_to_opus_stream(
                                    bytes(jitter_buffer[:valid_len]), False, self.handle_opus
                                )
                                del jitter_buffer[:valid_len]
                                first_packet_sent = True
                        else:
                            if len(jitter_buffer) >= CONTINUOUS_JITTER_BYTES:
                                valid_len = len(jitter_buffer) - (len(jitter_buffer) % 2)
                                await _emit_seg_text()
                                self.opus_encoder.encode_pcm_to_opus_stream(
                                    bytes(jitter_buffer[:valid_len]), False, self.handle_opus
                                )
                                del jitter_buffer[:valid_len]
                finally:
                    self.segment_queues.pop(task_id, None)
                    self.playback_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._playback_active:
                    logger.bind(tag=TAG).error(f"Playback error: {e}")
                    await asyncio.sleep(0.1)

    def _flush_pipeline(self):
        # Đóng WS prewarm còn treo từ turn trước (nếu segment 0 chưa kịp tái dùng).
        self._drop_prewarmed()
        for task in list(self._fetch_tasks):
            if not task.done():
                task.cancel()
        self._fetch_tasks.clear()

        if self.playback_queue:
            while not self.playback_queue.empty():
                try:
                    self.playback_queue.get_nowait()
                    self.playback_queue.task_done()
                except Exception:
                    break
            try:
                self.opus_encoder.reset_state()
                self.playback_queue.put_nowait("FLUSH")
            except Exception:
                pass

        for sq in self.segment_queues.values():
            while not sq.empty():
                try:
                    sq.get_nowait()
                except Exception:
                    break
        self.segment_queues.clear()

    # ── Fetch một segment: token -> WS -> PCM16 ───────────────────────────────
    async def _fetch_with_retry(self, idx, text, session_id, is_last=False):
        task_id = f"{session_id}_{idx}"
        seg_queue = self.segment_queues.get(task_id)
        if not seg_queue:
            return

        text = self.emoji_pattern.sub("", text)
        text = (
            text.replace("**", "").replace("*", "").replace("__", "")
            .replace("_", "").replace("`", "").replace("...", ",")
        )
        text = text.strip()
        if not any(ch.isalnum() for ch in text):
            await seg_queue.put(b"END_OF_SEGMENT")
            return
        if is_last and text and text[-1] not in ".?!。！？":
            text += "."

        if self._fetch_semaphore is None:
            self._fetch_semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

        success = False
        try:
            async with self._fetch_semaphore:
                for attempt in range(MAX_RETRY_ATTEMPTS):
                    if self.conn.client_abort or self.current_session_id != session_id:
                        break
                    backoff_ms = RETRY_BACKOFF_MS[min(attempt, len(RETRY_BACKOFF_MS) - 1)]
                    if backoff_ms > 0:
                        await asyncio.sleep(backoff_ms / 1000.0)
                    success = await self._do_fetch(idx, text, session_id, attempt)
                    if success:
                        break
            if not success and not self.conn.client_abort:
                logger.bind(tag=TAG).error(
                    f"[ALERT] Oriagent Voice GIVE UP segment #{idx} sau {MAX_RETRY_ATTEMPTS} attempts."
                )
                perf_metrics.record("oriagent_voice_segment_dropped", float(MAX_RETRY_ATTEMPTS), idx=idx)
        except asyncio.CancelledError:
            pass
        finally:
            await seg_queue.put(b"END_OF_SEGMENT")

    async def _get_stream_token(self, text_length: int):
        """POST /tts/stream-token -> (stream_token, ws_url) hoặc (None, None)."""
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=TOKEN_TIMEOUT, verify=self._verify_ssl, follow_redirects=True)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # text_length phải > 0 và <= 10000 (theo doc)
        body = {"text_length": max(1, min(int(text_length), 10000))}
        resp = await self._http.post(self.token_url, json=body, headers=headers)
        if resp.status_code != 200:
            logger.bind(tag=TAG).warning(
                f"stream-token lỗi {resp.status_code}: {resp.text[:200]}"
            )
            return None, None
        payload = resp.json()
        if not payload.get("ok"):
            logger.bind(tag=TAG).warning(f"stream-token từ chối: {payload.get('error')}")
            return None, None
        data = payload.get("data") or {}
        return data.get("stream_token"), data.get("ws_url")

    @staticmethod
    def _build_ws_url(ws_url: str, token: str) -> str:
        parts = urlsplit(ws_url)
        sep = "&" if parts.query else "?"
        return f"{ws_url}{sep}{urlencode({'token': token})}"

    # ── Prewarm: mở sẵn token+WS đầu turn, segment 0 tái dùng ─────────────────
    async def _safe_close_ws(self, ws):
        try:
            await ws.close()
        except Exception:
            pass

    async def _prewarm_ws(self, session_id):
        """Lấy stream-token + mở WS ngay đầu turn (song song LLM). Best-effort:
        lỗi thì bỏ qua, segment 0 tự lấy token/WS như bình thường. Server chờ ở
        receive_json() nên giữ socket mở mà chưa gửi `start` là hợp lệ (~<30s)."""
        if self._ws_disabled:
            return
        ws = None
        try:
            token, ws_url = await self._get_stream_token(self._prewarm_chars)
            if not token or not ws_url or self.current_session_id != session_id:
                return
            full_ws_url = self._build_ws_url(ws_url, token)
            use_ssl = self._ssl_ctx if full_ws_url.startswith("wss") else None
            ws = await asyncio.wait_for(
                websockets.connect(full_ws_url, ssl=use_ssl, ping_interval=20.0, ping_timeout=20.0),
                timeout=WS_CONNECT_TIMEOUT,
            )
            if self.current_session_id != session_id or self.conn.client_abort:
                await self._safe_close_ws(ws)
                return
            self._prewarmed = (ws, session_id, time.monotonic())
        except Exception as e:
            if ws is not None:
                await self._safe_close_ws(ws)
            # 404/rejected -> đường chính (_do_fetch_ws) sẽ tự phát hiện & tắt WS.
            logger.bind(tag=TAG).debug(f"prewarm WS bỏ qua: {e}")

    def _take_prewarmed(self, session_id, need_chars):
        """Trả WS đã mở sẵn nếu còn hợp lệ cho segment đầu; None nếu không dùng được
        (đóng luôn socket stale). Chạy trên event loop -> ensure_future an toàn."""
        pw = self._prewarmed
        if not pw:
            return None
        self._prewarmed = None
        ws, sid, ts = pw
        stale = (
            session_id != sid
            or need_chars > self._prewarm_chars
            or (time.monotonic() - ts) > self._prewarm_max_age
            or self.conn.client_abort
        )
        if stale:
            asyncio.ensure_future(self._safe_close_ws(ws))
            return None
        return ws

    def _schedule_prewarm(self, session_id):
        if not self._prewarm_enabled or self._ws_disabled:
            return
        asyncio.run_coroutine_threadsafe(self._prewarm_ws(session_id), self.conn.loop)

    def _drop_prewarmed(self):
        """Đóng WS prewarm còn treo (gọi khi flush/turn mới/close)."""
        pw = self._prewarmed
        if not pw:
            return
        self._prewarmed = None
        ws = pw[0]
        try:
            asyncio.run_coroutine_threadsafe(self._safe_close_ws(ws), self.conn.loop)
        except Exception:
            pass

    async def _do_fetch(self, idx, text, session_id, attempt=0) -> bool:
        """Dispatcher: ưu tiên WS realtime; nếu WS không khả dụng (404) -> blocking /tts/generate."""
        if not self._ws_disabled:
            ok = await self._do_fetch_ws(idx, text, session_id, attempt)
            if ok:
                return True
            if not self._ws_disabled:
                return False  # lỗi WS tạm thời -> để vòng retry thử lại WS
            # WS vừa bị tắt (404) -> rơi xuống blocking ngay trong attempt này
        return await self._do_fetch_blocking(idx, text, session_id, attempt)

    async def _do_fetch_ws(self, idx, text, session_id, attempt=0) -> bool:
        task_id = f"{session_id}_{idx}"
        seg_queue = self.segment_queues.get(task_id)
        if not seg_queue:
            return False
        t_send = None
        ws = None
        try:
            # Segment đầu (attempt đầu): tái dùng WS đã prewarm để giấu token+connect.
            if idx == 0 and attempt == 0:
                ws = self._take_prewarmed(session_id, len(text))
            if ws is None:
                stream_token, ws_url = await self._get_stream_token(len(text))
                if not stream_token or not ws_url:
                    return False
                if self.conn.client_abort or self.current_session_id != session_id:
                    return True

                full_ws_url = self._build_ws_url(ws_url, stream_token)
                use_ssl = self._ssl_ctx if full_ws_url.startswith("wss") else None
                try:
                    ws = await asyncio.wait_for(
                        websockets.connect(full_ws_url, ssl=use_ssl, ping_interval=20.0, ping_timeout=20.0),
                        timeout=WS_CONNECT_TIMEOUT,
                    )
                except Exception as conn_err:
                    # Endpoint WS chưa deploy (404/rejected) -> tắt WS, chuyển hẳn sang blocking.
                    if isinstance(conn_err, getattr(websockets.exceptions, "InvalidStatus", ())) \
                            or "404" in str(conn_err) or "rejected" in str(conn_err).lower():
                        if not self._ws_warned:
                            logger.bind(tag=TAG).warning(
                                "Oriagent WS realtime không khả dụng (HTTP 404) — chuyển sang blocking /tts/generate."
                            )
                            self._ws_warned = True
                        self._ws_disabled = True
                        _WS_DEAD_BASES.add(self.api_base)
                    raise

            start_msg = {
                "type": "start",
                "text": text,
                "language": self.language,
                "control_instruction": self.control_instruction or "",
                "cfg_value": self.cfg_value,
                # Segment đầu ưu tiên tốc độ (TTFB), segment sau ưu tiên chất lượng.
                "dit_steps": self.dit_steps_first if idx == 0 else self.dit_steps,
                "streaming_mode": self.streaming_mode,
            }
            t_send = time.perf_counter()
            await ws.send(json.dumps(start_msg))

            ttfb_recorded = False
            while True:
                if self.conn.client_abort or self.current_session_id != session_id:
                    return True
                message = await asyncio.wait_for(ws.recv(), timeout=WS_RECV_TIMEOUT)

                if isinstance(message, (bytes, bytearray)):
                    if not message:
                        continue
                    if not ttfb_recorded and t_send is not None:
                        perf_metrics.record(
                            "oriagent_voice_ttfb_ms",
                            (time.perf_counter() - t_send) * 1000,
                            attempt=attempt, text_len=len(text), session=str(session_id),
                        )
                        ttfb_recorded = True
                    await seg_queue.put(bytes(message))
                else:
                    data = json.loads(message)
                    mtype = data.get("type")
                    if mtype == "start":
                        sr = data.get("sample_rate")
                        if sr and int(sr) != int(self.conn.sample_rate):
                            logger.bind(tag=TAG).warning(
                                f"Oriagent sample_rate={sr} khác device={self.conn.sample_rate} "
                                f"(có thể méo cao độ)."
                            )
                        continue
                    if mtype == "done":
                        if t_send is not None:
                            perf_metrics.record(
                                "oriagent_voice_total_ms",
                                (time.perf_counter() - t_send) * 1000,
                                text_len=len(text),
                            )
                        return True
                    if mtype == "error":
                        logger.bind(tag=TAG).warning(
                            f"Oriagent WS error segment #{idx}: {data.get('message')}"
                        )
                        return False
                    # các event khác -> bỏ qua
        except Exception as e:
            perf_metrics.record(
                "oriagent_voice_exception",
                (time.perf_counter() - t_send) * 1000 if t_send else 0,
                attempt=attempt, error=type(e).__name__,
            )
            logger.bind(tag=TAG).warning(f"_do_fetch segment #{idx} exception: {e}")
            return False
        finally:
            if ws is not None:
                try:
                    await ws.close()
                except Exception:
                    pass

    @staticmethod
    def _sniff_format(audio_bytes: bytes) -> str:
        """Đoán định dạng theo magic bytes (server có thể trả WAV dù đuôi .mp3)."""
        if audio_bytes[:4] == b"RIFF":
            return "wav"
        if audio_bytes[:3] == b"ID3" or (len(audio_bytes) > 1 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0):
            return "mp3"
        if audio_bytes[:4] == b"OggS":
            return "ogg"
        return "wav"

    def _decode_to_pcm(self, audio_bytes: bytes) -> bytes:
        """Decode wav/mp3/ogg -> PCM16 mono @ device sample_rate (blocking -> chạy trong executor)."""
        from io import BytesIO
        from pydub import AudioSegment

        fmt = self._sniff_format(audio_bytes)
        audio = AudioSegment.from_file(BytesIO(audio_bytes), format=fmt, parameters=["-nostdin"])
        audio = audio.set_channels(1).set_frame_rate(self.conn.sample_rate).set_sample_width(2)
        return audio.raw_data

    async def _do_fetch_blocking(self, idx, text, session_id, attempt=0) -> bool:
        """Fallback: POST /tts/generate -> audio_url (mp3) -> decode PCM -> đẩy seg_queue.
        Vẫn chạy song song theo segment nên TTFA thấp dù không phải stream thật."""
        task_id = f"{session_id}_{idx}"
        seg_queue = self.segment_queues.get(task_id)
        if not seg_queue:
            return False
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=TOKEN_TIMEOUT, verify=self._verify_ssl, follow_redirects=True)
        t_send = time.perf_counter()
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            body = {"text": text, "language": self.language, "format": "wav"}
            r = await self._http.post(self.generate_url, json=body, headers=headers, timeout=30.0)
            if r.status_code != 200:
                logger.bind(tag=TAG).warning(f"generate lỗi {r.status_code}: {r.text[:200]}")
                return False
            payload = r.json()
            if not payload.get("ok"):
                logger.bind(tag=TAG).warning(f"generate từ chối: {payload.get('error')}")
                return False
            data = payload.get("data") or {}
            audio_url = data.get("audio_url")
            if not audio_url:
                logger.bind(tag=TAG).warning("generate không trả audio_url")
                return False
            if self.conn.client_abort or self.current_session_id != session_id:
                return True

            a = await self._http.get(audio_url, timeout=30.0)
            if a.status_code != 200 or not a.content:
                logger.bind(tag=TAG).warning(f"tải audio_url lỗi {a.status_code}")
                return False

            pcm = await self.conn.loop.run_in_executor(None, self._decode_to_pcm, a.content)
            if not pcm:
                return False
            perf_metrics.record(
                "oriagent_voice_blocking_ms", (time.perf_counter() - t_send) * 1000,
                text_len=len(text), pcm_bytes=len(pcm),
            )

            CHUNK = 8000  # ~166ms PCM16@24k mỗi lần đẩy
            for i in range(0, len(pcm), CHUNK):
                if self.conn.client_abort or self.current_session_id != session_id:
                    return True
                await seg_queue.put(pcm[i:i + CHUNK])
            return True
        except Exception as e:
            logger.bind(tag=TAG).warning(f"_do_fetch_blocking segment #{idx} exception: {e}")
            return False

    def _schedule_fetch(self, idx, text, session_id, is_last=False):
        async def _tracked():
            task = asyncio.current_task()
            self._fetch_tasks.add(task)
            try:
                await self._fetch_with_retry(idx, text, session_id, is_last)
            finally:
                self._fetch_tasks.discard(task)

        asyncio.run_coroutine_threadsafe(_tracked(), self.conn.loop)

    # ── Thread chính: nhận token text -> cắt câu -> schedule fetch song song ──
    def tts_text_priority_thread(self):
        logger.bind(tag=TAG).info("Oriagent Voice TTS (WS realtime): thread active.")
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
                    # Đòn #1: mở sẵn token+WS song song với LLM -> segment 0 khỏi chờ.
                    self._schedule_prewarm(self.current_session_id)
                    logger.bind(tag=TAG).info(f"Reset SID: {self.current_session_id}")

                if self.conn.client_abort:
                    continue

                if ContentType.TEXT == message.content_type and message.content_detail:
                    self.tts_text_buff.append(message.content_detail)
                    while True:
                        segment = self._get_smart_segment()
                        if not segment:
                            break
                        # offset cuối segment trong text-vào-TTS (cùng hệ đếm với
                        # connection._tts_emitted_chars) -> để show ảnh đúng lúc segment phát.
                        seg_end_offset = self.processed_chars
                        segment = MarkdownCleaner.clean_markdown(segment)
                        if not segment:
                            continue
                        idx = self.segment_counter
                        self.segment_counter += 1
                        task_id = f"{self.current_session_id}_{idx}"
                        self.segment_queues[task_id] = asyncio.Queue()
                        asyncio.run_coroutine_threadsafe(
                            self.playback_queue.put((idx, idx == 0, segment, self.current_session_id, seg_end_offset)),
                            self.conn.loop,
                        )
                        # KHÔNG prepend khoảng trắng vào segment đầu: VoxCPM (diffusion clone)
                        # có xu hướng "phát âm" padding đầu -> chèn âm lạ đầu câu. Việc chống
                        # clip/dead-air đầu câu đã do LEAD_IN_SILENCE_BYTES (im lặng thật phía
                        # client) đảm nhiệm, không cần padding text.
                        self._schedule_fetch(idx, segment, self.current_session_id, False)

                if message.sentence_type == SentenceType.LAST:
                    full_text = "".join(self.tts_text_buff)
                    remaining = full_text[self.processed_chars:]
                    remaining = MarkdownCleaner.clean_markdown(remaining)
                    if remaining and remaining.strip() and not self.conn.client_abort:
                        idx = self.segment_counter
                        self.segment_counter += 1
                        task_id = f"{self.current_session_id}_{idx}"
                        self.segment_queues[task_id] = asyncio.Queue()
                        asyncio.run_coroutine_threadsafe(
                            self.playback_queue.put((idx, idx == 0, remaining, self.current_session_id, len(full_text))),
                            self.conn.loop,
                        )
                        # Xem chú thích trên: không prepend khoảng trắng đầu câu.
                        self._schedule_fetch(idx, remaining, self.current_session_id, True)
                    target_q = self.tts_audio_queue
                    self.conn.executor.submit(self._wait_for_all_and_finish, message.content_detail, self.current_session_id, target_q)
            except queue.Empty:
                continue
            except Exception as e:
                logger.bind(tag=TAG).error(f"Master error: {e}")

    def _get_smart_segment(self):
        """Cắt câu cho TTS theo 3 mức ưu tiên (giống Blaze v2):
        1) Hard stop (. ! ? 。 ！ ？ \\n)               — cắt ngay
        2) Soft stop (, ; : ， ； ：) nếu đoạn ≥ 40 ký tự — cắt theo nhịp tự nhiên
        3) Force      nếu đoạn ≥ 80 ký tự               — chống buffer overflow
        """
        full_text = "".join(self.tts_text_buff)
        text_to_process = full_text[self.processed_chars:]
        if not text_to_process:
            return None

        hard_stops = (".", "!", "?", "\n", "。", "！", "？")
        soft_stops = (",", ";", ":", "，", "；", "：")
        MIN_SOFT_LEN = 40
        FORCE_SEG_LEN = 80
        FORCE_LIMIT = 60
        MIN_SEG_CHARS = 5

        soft_idx = -1
        for i, char in enumerate(text_to_process):
            if char in hard_stops:
                seg = text_to_process[: i + 1].strip()
                if seg and len(seg) >= MIN_SEG_CHARS:
                    self.processed_chars += i + 1
                    return seg
            elif soft_idx < 0 and char in soft_stops and (i + 1) >= MIN_SOFT_LEN:
                soft_idx = i

        if soft_idx >= 0:
            seg = text_to_process[: soft_idx + 1].strip()
            if seg:
                self.processed_chars += soft_idx + 1
                return seg

        if len(text_to_process) >= FORCE_SEG_LEN:
            last_space = text_to_process.rfind(" ", 0, FORCE_LIMIT)
            if last_space == -1:
                last_space = FORCE_LIMIT
            seg = text_to_process[:last_space].strip()
            if seg:
                self.processed_chars += last_space
                return seg
        return None

    def _wait_for_all_and_finish(self, content_detail, session_id=None, target_q=None):
        if session_id and session_id != getattr(self, "current_session_id", None):
            return
        if target_q is None:
            target_q = self.tts_audio_queue
        async def wait_loop():
            if self.playback_queue:
                await self.playback_queue.put("END_OF_SESSION")
                try:
                    await asyncio.wait_for(self.playback_queue.join(), timeout=PLAYBACK_JOIN_TIMEOUT)
                except Exception:
                    pass
                await asyncio.sleep(0.2)

        future = asyncio.run_coroutine_threadsafe(wait_loop(), self.conn.loop)
        try:
            future.result(timeout=PLAYBACK_JOIN_TIMEOUT + 2)
        except Exception:
            pass
        target_q.put((SentenceType.LAST, [], content_detail))

    def text_to_speak(self, text, _):
        pass

    def to_tts(self, text: str) -> list:
        return [{"type": "tts", "text": text}]

    async def close(self):
        self._playback_active = False
        if self._prewarmed:
            ws = self._prewarmed[0]
            self._prewarmed = None
            await self._safe_close_ws(ws)
        for task in list(self._fetch_tasks):
            if not task.done():
                task.cancel()
        if self.playback_task:
            self.playback_task.cancel()
        if self._http is not None:
            try:
                await self._http.aclose()
            except Exception:
                pass
