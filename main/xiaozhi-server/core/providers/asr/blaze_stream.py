import json
import uuid
import asyncio
import websockets
import opuslib_next
import ssl
import time

from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.interface_type = InterfaceType.STREAM
        self.config = config
        self.text = ""
        self.decoder = opuslib_next.Decoder(16000, 1)
        self.asr_ws = None
        self.forward_task = None
        self.is_processing = False
        self.server_ready = False
        self.output_dir = config.get("output_dir", "tmp/")

        self.api_key = config.get("api_key")
        self.model = config.get("model") or "v2.0"
        self.language = config.get("language") or "vi"
        
        domain = config.get("domain") or "api.blaze.vn"
        self.ws_url = f"wss://{domain}/v1/stt/realtime"

    async def receive_audio(self, conn: "ConnectionHandler", audio: bytes, audio_have_voice: bool):
        await super().receive_audio(conn, audio, audio_have_voice)
        
        # Universal health check
        is_open = self.asr_ws and (self.asr_ws.open if hasattr(self.asr_ws, 'open') else (not self.asr_ws.closed if hasattr(self.asr_ws, 'closed') else True))
        
        if audio_have_voice and not self.is_processing and (not self.asr_ws or not is_open):
            try:
                await self._start_recognition(conn)
            except Exception as e:
                logger.bind(tag=TAG).error(f"Blaze ASR start failed: {e}")
                await self._cleanup()
                return

        is_open = self.asr_ws and (self.asr_ws.open if hasattr(self.asr_ws, 'open') else (not self.asr_ws.closed if hasattr(self.asr_ws, 'closed') else True))
        if self.asr_ws and is_open and self.is_processing and self.server_ready:
            try:
                pcm_frame = self.decoder.decode(audio, 960)
                await self.asr_ws.send(pcm_frame)
            except Exception as e:
                logger.bind(tag=TAG).warning(f"Blaze ASR send audio error: {e}")
                await self._cleanup()

    async def _start_recognition(self, conn: "ConnectionHandler"):
        logger.bind(tag=TAG).debug(f"Connecting to Blaze ASR ({self.ws_url})...")
        
        ssl_context = ssl.create_default_context()
        if self.config.get("verify_ssl") is False:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        self.asr_ws = await websockets.connect(
            self.ws_url,
            ssl=ssl_context,
            ping_interval=30
        )

        self.is_processing = True
        self.server_ready = False
        self.forward_task = asyncio.create_task(self._forward_results(conn))

        # 1. Send Init JSON
        init_req = {
            "token": self.api_key,
            "model": self.model,
            "language": self.language
        }
        await self.asr_ws.send(json.dumps(init_req))

    async def _forward_results(self, conn: "ConnectionHandler"):
        try:
            async for message in self.asr_ws:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "ready":
                    self.server_ready = True
                    logger.bind(tag=TAG).debug("Blaze ASR server ready.")
                
                elif msg_type == "partial" or msg_type == "final":
                    res_text = data.get("text", "")
                    if res_text:
                        self.text = res_text
                        if msg_type == "final":
                            logger.bind(tag=TAG).info(f"Blaze ASR Final: {res_text}")
                            await self.handle_voice_stop(conn, conn.asr_audio)
                            break
                        else:
                            logger.bind(tag=TAG).debug(f"Blaze ASR Partial: {res_text}")
                
                elif msg_type == "error":
                    logger.bind(tag=TAG).error(f"Blaze ASR Error: {data.get('message')}")
                    break

        except Exception as e:
            if not isinstance(e, asyncio.CancelledError):
                logger.bind(tag=TAG).error(f"Blaze ASR monitor error: {e}")
        finally:
            await self._cleanup()

    async def _cleanup(self):
        self.is_processing = False
        self.server_ready = False
        if self.asr_ws:
            try:
                await self.asr_ws.close()
            except:
                pass
            self.asr_ws = None
        self.forward_task = None

    async def speech_to_text(self, opus_data, session_id, audio_format, artifacts=None):
        result = self.text
        self.text = ""
        return result, None

    async def close(self):
        await self._cleanup()
