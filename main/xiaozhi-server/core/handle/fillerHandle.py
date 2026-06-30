"""
Thinking-buffer (câu đệm suy nghĩ) — TOÀN HỆ THỐNG, không phụ thuộc TTS provider.

Khi user nói xong, LLM còn đang nghĩ → nếu sau `delay_ms` vẫn chưa có audio thật,
phát một câu đệm đã pre-render ĐÚNG GIỌNG (vd "Ừm, để mình nghĩ xíu nha…") để che
độ trễ. Câu trả lời thật fetch song song ở nền và phát ngay sau filler (cùng
tts_audio_queue → đúng thứ tự FIFO). Filler còn làm nóng DAC, chống clip âm đầu.

Thiết kế:
  * Config: per-agent (ưu tiên) + default toàn cục (fallback). Chuẩn hoá về
    {enabled, delay_ms, phrases:[...]}.
  * Pre-cache: render mỗi câu MỘT lần qua conn.tts.render_phrase_to_opus(), cache
    ở MỨC PROCESS theo (provider, giọng, sample_rate, câu) → dùng chung mọi kết nối.
  * Trigger ngưỡng: timer trên conn.loop; huỷ nếu có audio thật/abort trước hạn.
  * Barge-in: cancel_filler() trong abort.
"""

import time
import asyncio
import threading

from config.logger import setup_logging
from core.providers.tts.dto.dto import SentenceType

TAG = __name__
logger = setup_logging()

# Default toàn hệ thống (fallback khi agent/sys_params chưa cấu hình).
DEFAULT_PHRASES = [
    "Ừm, để mình nghĩ xíu nha",
    "Câu này hay nè, đợi mình một chút",
    "Để mình xem nào",
    "Hmm, thú vị đấy, chờ mình tí nhé",
    "Ồ, câu hỏi thú vị ghê, đợi mình xíu",
    "Được rồi, để mình tính nhanh nha",
]
DEFAULT_DELAY_MS = 700
MIN_DELAY_MS = 100
MAX_DELAY_MS = 5000

# Cache opus theo (provider_class, voice, sample_rate, phrase) — chia sẻ toàn process.
_filler_cache = {}
_cache_lock = threading.Lock()
# Tránh nhiều luồng cùng prewarm 1 connection.
_prewarming = set()
_prewarm_lock = threading.Lock()


def _as_phrase_list(raw):
    """Chấp nhận list[str] hoặc chuỗi (mỗi câu 1 dòng hoặc ngăn bằng '|')."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw]
    else:
        s = str(raw)
        sep = "|" if "|" in s else "\n"
        items = [x.strip() for x in s.split(sep)]
    return [x for x in items if x]


def build_filler_config(config, private_config=None):
    """
    Gộp config filler: per-agent (private_config / config['filler']) đè default
    toàn cục (config['filler_default']). Trả dict chuẩn hoá hoặc None nếu tắt.
    """
    src = {}
    # default toàn cục trước
    if isinstance(config, dict) and isinstance(config.get("filler_default"), dict):
        src.update(config["filler_default"])
    # per-agent đè lên (ưu tiên private_config nếu có)
    for holder in (config, private_config):
        if isinstance(holder, dict) and isinstance(holder.get("filler"), dict):
            src.update(holder["filler"])

    if not src:
        return None

    enabled = src.get("enabled", False)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return None

    phrases = _as_phrase_list(src.get("phrases")) or list(DEFAULT_PHRASES)
    if not phrases:
        return None

    try:
        delay_ms = int(src.get("delay_ms", DEFAULT_DELAY_MS))
    except (TypeError, ValueError):
        delay_ms = DEFAULT_DELAY_MS
    delay_ms = max(MIN_DELAY_MS, min(MAX_DELAY_MS, delay_ms))

    return {"enabled": True, "delay_ms": delay_ms, "phrases": phrases}


def _voice_key(conn):
    tts = getattr(conn, "tts", None)
    voice = getattr(tts, "speaker_id", None) or getattr(tts, "voice", "")
    return (type(tts).__name__, str(voice), int(getattr(conn, "sample_rate", 16000)))


def get_cached(conn, phrase):
    with _cache_lock:
        return _filler_cache.get(_voice_key(conn) + (phrase,))


def _wait_idle(conn):
    """
    Chờ pipeline TTS rảnh (không có turn đang chạy) trước khi render filler.
    Render dùng CHUNG tts_text_queue/threads với turn thật, nên KHÔNG được render
    khi đang phục vụ một turn (sẽ làm hỏng phiên). conn.client_is_speaking = True
    suốt một turn (từ lúc bắt đầu tới khi phát xong LAST). Trả False nếu connection
    đang đóng.
    """
    stop_event = getattr(conn, "stop_event", None)
    waited = 0.0
    while getattr(conn, "client_is_speaking", False):
        if stop_event is not None and stop_event.is_set():
            return False
        time.sleep(0.2)
        waited += 0.2
        if waited > 120:  # an toàn: không kẹt vĩnh viễn
            return False
    return not (stop_event is not None and stop_event.is_set())


def prewarm_fillers(conn):
    """
    Render + cache mọi câu đệm cho giọng hiện tại (chạy trong thread nền).
    CHỈ render khi pipeline rảnh (giữa các turn) để không đụng turn thật.
    """
    tts = getattr(conn, "tts", None)
    if tts is None or not hasattr(tts, "render_phrase_to_opus"):
        return
    if getattr(conn, "filler", None) is None:
        conn.filler = build_filler_config(getattr(conn, "config", {}) or {})
    cfg = conn.filler
    if not cfg or not cfg.get("enabled"):
        return

    vkey = _voice_key(conn)
    for phrase in cfg["phrases"]:
        key = vkey + (phrase,)
        with _cache_lock:
            if key in _filler_cache:
                continue
        if not _wait_idle(conn):
            return  # connection đóng → dừng
        try:
            frames = tts.render_phrase_to_opus(phrase)
        except Exception as e:
            logger.bind(tag=TAG).warning(f"prewarm filler '{phrase[:20]}' failed: {e}")
            continue
        if frames:
            with _cache_lock:
                _filler_cache[key] = frames
            logger.bind(tag=TAG).info(
                f"Filler cached '{phrase[:24]}' ({len(frames)} opus frames)"
            )


def schedule_prewarm(conn):
    """Kick prewarm nền 1 lần / connection (idempotent nhờ cache).
    Gọi lúc MỞ KẾT NỐI để turn đầu đã có sẵn câu đệm."""
    cid = id(conn)
    with _prewarm_lock:
        if cid in _prewarming:
            return
        _prewarming.add(cid)

    def _run():
        try:
            prewarm_fillers(conn)
        finally:
            with _prewarm_lock:
                _prewarming.discard(cid)

    try:
        conn.executor.submit(_run)
    except Exception:
        with _prewarm_lock:
            _prewarming.discard(cid)


def _next_phrase(conn):
    phrases = conn.filler["phrases"]
    if not phrases:
        return None
    idx = getattr(conn, "_filler_idx", 0) % len(phrases)
    conn._filler_idx = idx + 1
    return phrases[idx]


def start_turn_filler(conn):
    """
    Gọi ở đầu mỗi turn (chat depth==0). Reset cờ, bật timer ngưỡng.
    Lazy-build config + prewarm nền nếu cache chưa sẵn (turn đầu có thể chưa kịp đệm).
    """
    if getattr(conn, "filler", None) is None:
        conn.filler = build_filler_config(getattr(conn, "config", {}) or {})
    conn.tts_first_audio_sent = False

    cfg = conn.filler
    if not cfg or not cfg.get("enabled"):
        return

    cancel_filler(conn)  # dọn timer cũ nếu còn

    # Đảm bảo cache đang/đã được dựng.
    schedule_prewarm(conn)

    delay = cfg["delay_ms"] / 1000.0
    try:
        conn._filler_task = asyncio.run_coroutine_threadsafe(
            _filler_timer(conn, delay), conn.loop
        )
    except Exception as e:
        logger.bind(tag=TAG).warning(f"start_turn_filler failed: {e}")
        conn._filler_task = None


async def _filler_timer(conn, delay):
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    # Câu trả lời thật đã ra hoặc bị ngắt → không đệm.
    if getattr(conn, "client_abort", False) or getattr(conn, "tts_first_audio_sent", False):
        return
    phrase = _next_phrase(conn)
    if not phrase:
        return
    frames = get_cached(conn, phrase)
    if not frames:
        # Chưa render kịp (vd turn đầu) → bỏ qua, lần sau sẽ có.
        logger.bind(tag=TAG).debug(f"Filler '{phrase[:20]}' chưa sẵn cache, bỏ qua turn này")
        return
    # Re-check ngay trước khi đẩy (giảm overlap với audio thật).
    if getattr(conn, "client_abort", False) or getattr(conn, "tts_first_audio_sent", False):
        return
    try:
        conn.tts.tts_audio_queue.put((SentenceType.MIDDLE, frames, None))
        conn.tts_first_audio_sent = True
        logger.bind(tag=TAG).info(f"▶ Filler phát: '{phrase[:30]}' ({len(frames)} frames)")
    except Exception as e:
        logger.bind(tag=TAG).warning(f"enqueue filler failed: {e}")


def cancel_filler(conn):
    task = getattr(conn, "_filler_task", None)
    if task is not None and not task.done():
        task.cancel()
    conn._filler_task = None
