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
# - Fetch parallel using 2 WS connections for 0s network latency.
# - Consumer reads from Strict Ordered Queues -> 100% Thread-safe & No Deadlocks.
# - Smart Segments expanded to 25 words to prevent mid-sentence cutting.
# =============================================================================

INITIAL_BUFFER_BYTES = 38400  # 38.4 KB ≈ 0.8s of audio at 24kHz/16bit/mono
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
        self.ws_pool = [None, None]
        self.ws_locks = [asyncio.Lock(), asyncio.Lock()]
        
        self.emoji_pattern = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)

        # [V5] Async Orchestration
        self.playback_queue = None       # Chứa danh sách Index cần phát theo đúng thứ tự
        self.segment_queues = {}         # Dict chứa {index: asyncio.Queue()} chứa audio của từng đoạn
        self.playback_task = None
        self._playback_active = False

    async def _ensure_connection(self, pool_idx):
        """Reuse or create a WS connection."""
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
        """Khởi tạo luồng phát Audio nếu chưa có."""
        if self.playback_queue is None:
            self.playback_queue = asyncio.Queue()
            self._playback_active = True
            self.playback_task = self.conn.loop.create_task(self._playback_loop())

    async def _playback_loop(self):
        """Worker tuần tự lấy Index -> Lấy Audio của Index đó -> Đẩy ra loa"""
        initial_buffer = bytearray()
        buffer_flushed = False # Chỉ đệm 0.5s ở câu ĐẦU TIÊN để siêu mượt
        
        while self._playback_active:
            try:
                # 1. Lấy Index cần phát tiếp theo
                idx = await self.playback_queue.get()
                
                # Tín hiệu kết thúc lượt nói của AI
                if idx == 'END_OF_SESSION':
                    if initial_buffer:
                        self.opus_encoder.encode_pcm_to_opus_stream(bytes(initial_buffer), False, self.handle_opus)
                        initial_buffer.clear()
                    buffer_flushed = False
                    self.playback_queue.task_done()
                    continue

                if self.conn.client_abort:
                    self.playback_queue.task_done()
                    continue

                # 2. Lấy Audio của Index đó (Chờ song song tải về)
                seg_queue = self.segment_queues.get(idx)
                if not seg_queue:
                    self.playback_queue.task_done()
                    continue

                while True:
                    if self.conn.client_abort: break
                    
                    pcm_chunk = await seg_queue.get()
                    if pcm_chunk == b'END_OF_SEGMENT':
                        seg_queue.task_done()
                        break
                    
                    # 3. Quản lý Jitter Buffer cho câu đầu tiên
                    if not buffer_flushed:
                        initial_buffer.extend(pcm_chunk)
                        if len(initial_buffer) >= INITIAL_BUFFER_BYTES:
                            self.opus_encoder.encode_pcm_to_opus_stream(bytes(initial_buffer), False, self.handle_opus)
                            initial_buffer.clear()
                            buffer_flushed = True
                    else:
                        self.opus_encoder.encode_pcm_to_opus_stream(pcm_chunk, False, self.handle_opus)
                    
                    seg_queue.task_done()

                # Dọn dẹp RAM
                self.segment_queues.pop(idx, None)
                self.playback_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.bind(tag=TAG).error(f"Playback Loop Error: {e}")
                await asyncio.sleep(0.5)

    def _empty_queues(self):
        """Dọn sạch hàng đợi ngay lập tức khi Barge-in"""
        if self.playback_queue:
            while not self.playback_queue.empty():
                try: self.playback_queue.get_nowait()
                except queue.Empty: break
        self.segment_queues.clear()

    # =========================================================================
    # PRODUCER: TẢI SONG SONG (DUAL FETCH)
    # =========================================================================
    async def _fetch_segment(self, idx, text, is_last=False):
        """Tải Audio từ Blaze và tống vào Hàng đợi riêng của từng Index"""
        pool_idx = idx % 2
        seg_queue = self.segment_queues[idx]

        # Tiền xử lý
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
                "audio_speed": self.audio_speed, "speaker_id": self.speaker_id, "model": self.model
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
                            
            except Exception as e:
                logger.bind(tag=TAG).error(f"Blaze WS[{pool_idx}] Fetch Error: {e}")
                self.ws_pool[pool_idx] = None
            finally:
                # BẮT BUỘC gửi cờ END để Consumer không bị treo vĩnh viễn
                await seg_queue.put(b'END_OF_SEGMENT')

    # =========================================================================
    # MASTER THREAD: QUẢN LÝ DÒNG CHẢY TEXT
    # =========================================================================
    def tts_text_priority_thread(self):
        logger.bind(tag=TAG).info("Blaze Speed TTS: V5 Master Pipeline active.")
        # Khởi động Consumer Worker
        asyncio.run_coroutine_threadsafe(self._start_playback_worker(), self.conn.loop)
        
        while not self.conn.stop_event.is_set():
            try:
                message = self.tts_text_queue.get(timeout=1)
                
                if message.sentence_type == SentenceType.FIRST:
                    self.conn.client_abort = False
                    self.tts_text_buff = []
                    self.processed_chars = 0
                    self.segment_counter = 0
                    self._empty_queues()
                    logger.bind(tag=TAG).info("Blaze Speed TTS: Session Reset.")
                
                if self.conn.client_abort: continue

                if ContentType.TEXT == message.content_type and message.content_detail:
                    self.tts_text_buff.append(message.content_detail)
                    segment = self._get_smart_segment()
                    if segment:
                        idx = self.segment_counter
                        self.segment_counter += 1
                        
                        # Cấp phát hàng đợi cho Index và Báo cho Playback Worker
                        self.segment_queues[idx] = asyncio.Queue()
                        asyncio.run_coroutine_threadsafe(self.playback_queue.put(idx), self.conn.loop)
                        
                        # Kích hoạt fetch song song
                        asyncio.run_coroutine_threadsafe(self._fetch_segment(idx, segment, False), self.conn.loop)

                if message.sentence_type == SentenceType.LAST:
                    full_text = "".join(self.tts_text_buff)
                    remaining = full_text[self.processed_chars:]
                    if remaining.strip() and not self.conn.client_abort:
                        idx = self.segment_counter
                        self.segment_counter += 1
                        
                        self.segment_queues[idx] = asyncio.Queue()
                        asyncio.run_coroutine_threadsafe(self.playback_queue.put(idx), self.conn.loop)
                        asyncio.run_coroutine_threadsafe(self._fetch_segment(idx, remaining, True), self.conn.loop)
                    
                    self.conn.executor.submit(self._wait_for_all_and_finish, message.content_detail)

            except queue.Empty: continue
            except Exception as e:
                logger.bind(tag=TAG).error(f"Blaze Speed Thread Error: {e}")

    def _get_smart_segment(self):
        """
        [FIX BUG CẮT CÂU NON] Nâng giới hạn Word Count.
        Hard Stops -> Phóng luôn.
        Soft Stops -> > 8 từ.
        Safety Net -> > 25 từ (Thay vì 15 từ để không cắt nát câu dài của AI).
        """
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

        if word_count >= 25: # Nâng mức an toàn lên 25 từ
            last_space = text_to_process.rfind(" ")
            if last_space != -1:
                seg = text_to_process[:last_space].strip()
                if seg:
                    self.processed_chars += (last_space + 1)
                    return seg

        return None

    def _wait_for_all_and_finish(self, content_detail):
        """[FIX BUG CÚP ĐIỆN SỚM] Bắt buộc chờ Consumer phát cạn Queue rồi mới Stop"""
        async def wait_loop():
            if self.playback_queue:
                # 1. Ném cờ hiệu kết thúc xuống cho Consumer
                await self.playback_queue.put('END_OF_SESSION')
                
                # 2. BẮT BUỘC: Đợi Consumer xử lý xong toàn bộ các Ticket trong Queue
                # playback_queue.join() sẽ block cho đến khi mọi task_done() được gọi
                await self.playback_queue.join() 
                
                # 3. Buffer an toàn một chút cho loa kịp dội âm cuối
                await asyncio.sleep(0.5) 
                
        # Tăng timeout lên 60s để AI thoải mái nói các câu siêu dài
        future = asyncio.run_coroutine_threadsafe(wait_loop(), self.conn.loop)
        try: 
            future.result(timeout=60) 
        except: 
            logger.bind(tag=TAG).warning("Blaze Speed TTS: Wait loop timeout!")
            
        # 4. Lúc này âm thanh đã ra loa hết, mới an toàn chốt sổ với XiaoZhi
        self.tts_audio_queue.put((SentenceType.LAST, [], content_detail))

    def text_to_speak(self, text, _):
        pass # Not used in V5 directly

    def to_tts(self, text: str) -> list:
        return [{"type": "tts", "text": text}]

    async def close(self):
        self._playback_active = False
        if self.playback_task: self.playback_task.cancel()
        for ws in self.ws_pool:
            if ws:
                try: await ws.close()
                except: pass