import os
import uuid
import requests
from datetime import datetime
from core.providers.tts.base import TTSProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

# Ký tự đặc trưng tiếng Việt để phát hiện ngôn ngữ từng câu (LLM có thể trả lời lẫn vi/en).
# API /tts/generate chỉ nhận language = vi | en (voice nào cũng dùng được với 1 trong 2).
_VI_CHARS = set("ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ")


def _detect_text_lang(text):
    for ch in (text or "").lower():
        if ch in _VI_CHARS:
            return "vi"
    return "en"


class TTSProvider(TTSProviderBase):
    """Oriagent Voice - Microsoft Edge TTS (cloud) qua voice.oriagent.com.

    API: POST {base}/tts/generate {text, language(vi|en), model:"edge-tts", voice, format:"mp3"} -> MP3
    Auth: Authorization: Bearer <api_key>
    Voice là 1 nhãn edge bất kỳ (vd en-US-AvaMultilingualNeural); language gửi vi/en theo nội dung câu.
    MP3 trả về được base class decode/resample sang opus bằng pydub.
    """

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        base = (config.get("api_url") or "https://voice.oriagent.com/api/public/v1").rstrip("/")
        self.api_url = base if base.endswith("/tts/generate") else f"{base}/tts/generate"
        self.api_key = config.get("api_key", "")
        self.voice = config.get("voice", "en-US-AvaMultilingualNeural")
        # ngôn ngữ mặc định khi không phát hiện được; vẫn ưu tiên detect theo text
        self.default_language = "vi" if str(config.get("language", "")).lower().startswith("vi") else "en"
        self.tts_model = config.get("model", "edge-tts")
        # prosody (chỉ edge-tts mới áp dụng); để trống thì không gửi
        self.rate = config.get("rate") or None
        self.pitch = config.get("pitch") or None
        self.volume = config.get("volume") or None
        self.audio_file_type = config.get("format", "mp3")

    def generate_filename(self, extension=".mp3"):
        return os.path.join(
            self.output_file,
            f"oriagent-edge-{datetime.now().date()}@{uuid.uuid4().hex}{extension}",
        )

    async def text_to_speak(self, text, output_file):
        if not self.api_key:
            raise Exception("Oriagent Edge TTS: api_key chưa được cấu hình")

        language = _detect_text_lang(text) or self.default_language
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "language": language,
            "model": self.tts_model,
            "voice": self.voice,
            "format": self.audio_file_type,
        }
        for key, val in (("rate", self.rate), ("pitch", self.pitch), ("volume", self.volume)):
            if val:
                payload[key] = val

        response = requests.post(self.api_url, json=payload, headers=headers, timeout=40)
        if response.status_code != 200:
            raise Exception(
                f"Oriagent Edge TTS lỗi {response.status_code}: {response.text[:300]}"
            )

        audio_content = response.content
        if not audio_content:
            raise Exception("Oriagent Edge TTS: phản hồi rỗng")

        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "wb") as f:
                f.write(audio_content)
            return output_file
        return audio_content
