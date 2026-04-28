import os
import io
import uuid
import json
import time
import queue
import asyncio
import websockets
import ssl
import threading
from pydub import AudioSegment

from config.logger import setup_logging
from core.utils.tts import MarkdownCleaner
from core.providers.tts.dto.dto import SentenceType, ContentType, InterfaceType
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    """
    Blaze.vn Realtime TTS provider - SEQUENTIAL VERSION.
    Each TTS request uses its own connection, matching the Blaze sample exactly.
    No background monitor - everything is handled sequentially for maximum stability.
    """

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.config = config
        self.interface_type = InterfaceType.DUAL_STREAM
        self.api_key = config.get("api_key")
        
        self.model = "2.0-realtime"
        self.speaker_id = "HN-Nu-ThuHuyenDeThuong"
        self.audio_speed = "1.2"
        self.audio_quality = 64
        self.audio_format = "wav"

        domain = config.get("domain") or "api.blaze.vn"
        self.ws_url = f"wss://{domain}/v1/tts/realtime"

        self._segment_done = threading.Event()
        self.processed_chars = 0
        self.sample_rate = 24000

    async def _do_tts_request(self, text):
        """
        One connection per request, exactly like the Blaze sample script.
        Connect -> Auth -> Send query -> Receive ALL audio -> Play -> Close.
        """
        # Only keep letters, numbers, spaces, and 3 sentence marks (. ? !)
        cleaned = []
        for ch in text:
            if ch.isalnum() or ch.isspace() or ch in ".?!":
                cleaned.append(ch)
            else:
                cleaned.append(" ")
        text = "".join(cleaned)
        
        # Ensure text ends with punctuation so Blaze doesn't hang
        if text and text[-1] not in ".?!":
            text = text + "."

        ws = None
        try:
            ssl_context = ssl.create_default_context()
            if self.config.get("verify_ssl") is False:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            ws = await websockets.connect(self.ws_url, ssl=ssl_context)

            # Step 1: Connection welcome
            await asyncio.wait_for(ws.recv(), timeout=5.0)

            # Step 2: Authenticate
            await ws.send(json.dumps({"token": self.api_key, "strategy": "request"}))
            auth_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            if "successful-authentication" not in auth_msg:
                logger.bind(tag=TAG).error(f"Blaze TTS: auth failed: {auth_msg}")
                return

            # Step 3: Send query
            req = {
                "query": text,
                "normalization": "basic",
                "language": "vi",
                "audio_format": self.audio_format,
                "audio_quality": self.audio_quality,
                "audio_speed": self.audio_speed,
                "speaker_id": self.speaker_id,
                "model": self.model
            }
            logger.bind(tag=TAG).info(f"Blaze TTS >> SENDING: {text[:60]}")
            await ws.send(json.dumps(req))

            # Step 4: Receive ALL audio bytes (exactly like sample script)
            audio_buffer = bytearray()
            while True:
                message = await asyncio.wait_for(ws.recv(), timeout=15.0)
                if isinstance(message, bytes):
                    audio_buffer.extend(message)
                else:
                    data = json.loads(message)
                    if data.get("type") == "finished-byte-stream":
                        break

            # Step 5: Decode WAV (near-instant, just reads header) and play
            if audio_buffer:
                logger.bind(tag=TAG).info(f"Blaze TTS: received {len(audio_buffer)} WAV bytes.")
                audio = AudioSegment.from_file(io.BytesIO(bytes(audio_buffer)), format="wav")
                if audio.frame_rate != self.sample_rate:
                    audio = audio.set_frame_rate(self.sample_rate)
                audio = audio.set_channels(1).set_sample_width(2)
                self.opus_encoder.encode_pcm_to_opus_stream(audio.raw_data, False, self.handle_opus)
                logger.bind(tag=TAG).info(f"Blaze TTS: segment played successfully.")

        except asyncio.TimeoutError:
            logger.bind(tag=TAG).error(f"Blaze TTS: timeout waiting for audio response.")
        except Exception as e:
            logger.bind(tag=TAG).error(f"Blaze TTS: request error: {e}")
        finally:
            if ws:
                try: await ws.close()
                except: pass

    async def text_to_speak(self, text, _):
        filtered_text = MarkdownCleaner.clean_markdown(text)
        if not filtered_text: return
        
        self._segment_done.clear()
        try:
            await self._do_tts_request(filtered_text)
        finally:
            self._segment_done.set()

    def tts_text_priority_thread(self):
        logger.bind(tag=TAG).info("Blaze TTS: worker thread active.")
        while not self.conn.stop_event.is_set():
            try:
                message = self.tts_text_queue.get(timeout=1)
                
                if message.sentence_type == SentenceType.FIRST:
                    self.conn.client_abort = False
                    self.tts_text_buff = []
                    self.processed_chars = 0
                
                if self.conn.client_abort: continue

                if ContentType.TEXT == message.content_type and message.content_detail:
                    self.tts_text_buff.append(message.content_detail)
                    segment = self._get_smart_segment()
                    if segment:
                        if self.conn.client_abort: continue
                        asyncio.run_coroutine_threadsafe(
                            self.text_to_speak(segment, None), self.conn.loop
                        ).result(timeout=20)

                if message.sentence_type == SentenceType.LAST:
                    full_text = "".join(self.tts_text_buff)
                    remaining = full_text[self.processed_chars:]
                    if remaining.strip():
                        if self.conn.client_abort: continue
                        asyncio.run_coroutine_threadsafe(
                            self.text_to_speak(remaining, None), self.conn.loop
                        ).result(timeout=20)
                    self.tts_audio_queue.put((SentenceType.LAST, [], message.content_detail))

            except queue.Empty: continue
            except Exception as e:
                logger.bind(tag=TAG).error(f"Blaze TTS thread error: {e}")

    def _get_smart_segment(self):
        """Only split when text has punctuation AND length > MIN_LENGTH."""
        MIN_LENGTH = 50
        full_text = "".join(self.tts_text_buff)
        text_to_process = full_text[self.processed_chars:]
        
        # Not long enough yet, keep accumulating
        if len(text_to_process) < MIN_LENGTH:
            return None
        
        # Find the LAST punctuation mark (to get the longest possible sentence)
        breakers = [".", "?", "!"]
        last_pos = -1
        for b in breakers:
            pos = text_to_process.rfind(b)
            if pos != -1:
                if pos > last_pos:
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
