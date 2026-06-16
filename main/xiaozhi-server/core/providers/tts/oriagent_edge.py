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
        # ngôn ngữ mặc định / nền (lấy từ field Language của agent)
        self.default_language = "vi" if str(config.get("language", "")).lower().startswith("vi") else "en"
        # Giọng "Multilingual" của Edge tự chuyển ngôn ngữ TRONG câu -> KHÔNG ép vi/en theo từng câu,
        # chỉ gửi 1 ngôn ngữ nền cố định để giọng tự xử lý câu trộn (vd "Cơm là Rice").
        self.is_multilingual = "multilingual" in self.voice.lower()
        # Chế độ Auto song ngữ (Language = "auto"): mỗi câu tự chọn GIỌNG đúng theo ngôn ngữ
        # -> câu Việt đọc giọng Việt chuẩn, câu Anh đọc giọng Anh chuẩn. Cặp giọng cấu hình được.
        self.auto_bilingual = str(config.get("language", "")).strip().lower() == "auto"
        self.auto_voice_vi = config.get("auto_voice_vi") or "vi-VN-HoaiMyNeural"
        self.auto_voice_en = config.get("auto_voice_en") or "en-US-AvaMultilingualNeural"
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

        if self.auto_bilingual:
            # Auto song ngữ: detect ngôn ngữ từng câu -> chọn GIỌNG đúng (Việt/Anh) cho câu đó.
            language = _detect_text_lang(text)
            voice = self.auto_voice_vi if language == "vi" else self.auto_voice_en
        else:
            # Thực nghiệm: giọng Multilingual đọc đúng cả Việt lẫn Anh khi gửi language="en"
            # (gửi "vi" thì tiếng Việt bị méo). Giọng đơn ngữ: detect vi/en theo câu.
            voice = self.voice
            language = "en" if self.is_multilingual else _detect_text_lang(text)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "language": language,
            "model": self.tts_model,
            "voice": voice,
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
