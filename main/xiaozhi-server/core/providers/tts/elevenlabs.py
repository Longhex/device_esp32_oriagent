import httpx
import os
from core.providers.tts.base import TTSProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_key = config.get("api_key")
        self.voice_id = config.get("voice_id", "21m00Tcm4lPqWRM9sxW1")
        self.model_id = config.get("model_id", "eleven_flash_v2_5")
        self.api_url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        self.output_format = config.get("format", "mp3_44100_128")
        self.stability = float(config.get("stability", 0.5))
        self.similarity_boost = float(config.get("similarity_boost", 0.75))
        self.use_speaker_boost = bool(config.get("use_speaker_boost", True))
        self.speed = float(config.get("speed", 1.0))
        self.style = float(config.get("style", 0.0))

    async def text_to_speak(self, text, output_file):
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        params = {
            "output_format": self.output_format,
        }

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "use_speaker_boost": self.use_speaker_boost,
                "speed": self.speed,
                "style": self.style,
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                logger.bind(tag=TAG).info(
                    f"ElevenLabs streaming TTS | VoiceID: {self.voice_id} | Text: {text[:50]}..."
                )

                async with client.stream(
                    "POST",
                    self.api_url,
                    headers=headers,
                    params=params,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        error_msg = await response.aread()
                        logger.bind(tag=TAG).error(
                            f"ElevenLabs API Error: {response.status_code} - {error_msg.decode(errors='ignore')}"
                        )
                        raise Exception(f"ElevenLabs streaming request failed (HTTP {response.status_code})")

                    if output_file:
                        os.makedirs(os.path.dirname(output_file), exist_ok=True)
                        with open(output_file, "wb") as f:
                            async for chunk in response.aiter_bytes():
                                if chunk:
                                    f.write(chunk)
                        return output_file

                    audio_bytes = bytearray()
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            audio_bytes.extend(chunk)
                    return bytes(audio_bytes)

            except Exception as e:
                logger.bind(tag=TAG).error(f"ElevenLabs TTS Exception: {str(e)}")
                raise