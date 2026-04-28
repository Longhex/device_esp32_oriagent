import os
import io
import json
import asyncio
import websockets
import ssl
import threading
import queue

from config.logger import setup_logging
from core.utils.tts import MarkdownCleaner
from core.providers.tts.dto.dto import SentenceType, ContentType, InterfaceType
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()

class TTSProvider(TTSProviderBase):
    """
    Blaze.vn Realtime TTS provider - SUPER SPEED STREAMING VERSION.
    - Uses 'streaming' strategy instead of 'request'.
    - Uses 'pcm' format to play audio instantly without buffering.
    - Maintains a Persistent WebSocket Connection.
    - Chops sentences faster.
    """

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.config = config
        self.interface_type = InterfaceType.DUAL_STREAM
        self.api_key = config.get("api_key")
        
        self.model = "2.0-realtime"
        self.speaker_id = "HN-Nu-ThuHuyenDeThuong"
        self.audio_speed = "1.2"
        self.audio_format = "wav"
        self.sample_rate = 24000
        self.audio_quality = 128

        domain = config.get("domain") or "api.blaze.vn"
        self.ws_url = f"wss://{domain}/v1/tts/realtime"

        self.processed_chars = 0
        self.ws_connection = None
        self.ws_lock = asyncio.Lock()

    async def _ensure_connection(self):
        # Reuse existing connection if open
        if self.ws_connection and getattr(self.ws_connection, "open", False):
            return self.ws_connection
            
        ssl_context = ssl.create_default_context()
        if self.config.get("verify_ssl") is False:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        try:
            ws = await websockets.connect(self.ws_url, ssl=ssl_context)
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            
            # Authenticate with TRUE STREAMING STRATEGY
            await ws.send(json.dumps({"token": self.api_key, "strategy": "streaming"}))
            auth_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            
            if "successful-authentication" not in auth_msg:
                logger.bind(tag=TAG).error(f"Blaze Speed TTS: auth failed: {auth_msg}")
                await ws.close()
                return None
            
            logger.bind(tag=TAG).info("Blaze Speed TTS: Persistent connection established!")
            self.ws_connection = ws
            return ws
        except Exception as e:
            logger.bind(tag=TAG).error(f"Blaze Speed TTS Connection Error: {e}")
            return None

    async def _do_tts_request(self, text):
        cleaned = []
        for ch in text:
            if ch.isalnum() or ch.isspace() or ch in ".?!,":
                cleaned.append(ch)
            else:
                cleaned.append(" ")
        text = "".join(cleaned)
        
        if text and text[-1] not in ".?!,":
            text = text + "."

        async with self.ws_lock:
            ws = await self._ensure_connection()
            if not ws:
                return

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
            logger.bind(tag=TAG).info(f"Blaze Speed TTS >> SENDING: {text[:60]}")
            
            try:
                await ws.send(json.dumps(req))
                
                # Receive and Play Instantly (Chunk by Chunk)
                header_skipped = False
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    if isinstance(message, bytes):
                        # Handle WAV header: Skip first 44 bytes of the first chunk
                        data_to_send = message
                        if not header_skipped:
                            if data_to_send.startswith(b'RIFF'):
                                data_to_send = data_to_send[44:]
                            header_skipped = True
                        
                        if data_to_send:
                            # Instantly push binary audio data to Opus encoder and ESP32 queue
                            self.opus_encoder.encode_pcm_to_opus_stream(data_to_send, False, self.handle_opus)
                    else:
                        data = json.loads(message)
                        if data.get("type") == "finished-byte-stream":
                            logger.bind(tag=TAG).info(f"Blaze Speed TTS: Segment finished.")
                            break
            except Exception as e:
                logger.bind(tag=TAG).error(f"Blaze Speed TTS Request Error: {e}")
                # Drop broken connection, will reconnect next phrase
                self.ws_connection = None 

    async def text_to_speak(self, text, _):
        filtered_text = MarkdownCleaner.clean_markdown(text)
        if not filtered_text: return
        await self._do_tts_request(filtered_text)

    def tts_text_priority_thread(self):
        logger.bind(tag=TAG).info("Blaze Speed TTS: worker thread active.")
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
                    
                    # Signal ESP32 that we are completely done
                    self.tts_audio_queue.put((SentenceType.LAST, [], message.content_detail))

            except queue.Empty: continue
            except Exception as e:
                logger.bind(tag=TAG).error(f"Blaze Speed TTS thread error: {e}")

    def _get_smart_segment(self):
        """Split into phrases for better prosody."""
        MIN_LENGTH = 60 # Increased for better quality/prosody
        full_text = "".join(self.tts_text_buff)
        text_to_process = full_text[self.processed_chars:]
        
        if len(text_to_process) < MIN_LENGTH:
            return None
        
        # Split on comma (,) to send text faster!
        breakers = [".", "?", "!", ",", "\n"]
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
        if self.ws_connection:
            try: await self.ws_connection.close()
            except: pass
