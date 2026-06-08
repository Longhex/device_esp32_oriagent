import os
import uuid
import requests
from datetime import datetime
from core.providers.tts.base import TTSProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

# Các giọng Oriagent hợp lệ + ngôn ngữ tương ứng (theo /tts/voices).
# API bắt buộc voice phải khớp language, nếu không sẽ trả 400 unsupported_voice.
_VOICE_LANG = {
    "vi-medium": "vi",
    "lessac-medium": "en",
    "hfc_male-medium": "en",
    "vcctk-medium-p280": "en",
}
_DEFAULT_VOICE_BY_LANG = {"vi": "vi-medium", "en": "lessac-medium"}


def _normalize_language(value, default="vi"):
    """Chuẩn hóa nhiều dạng (Vietnamese, vi-VN, English...) về 'vi' / 'en'."""
    v = (value or "").strip().lower()
    if v.startswith("vi") or v in ("vietnamese", "tiếng việt", "vn"):
        return "vi"
    if v.startswith("en") or v == "english":
        return "en"
    return default


# Ký tự đặc trưng tiếng Việt (có dấu) để phát hiện ngôn ngữ của từng câu,
# vì LLM Oriagent có thể trả lời lẫn lộn vi/en trong cùng phiên.
_VI_CHARS = set("ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ")


def _detect_text_lang(text):
    """'vi' nếu có ký tự tiếng Việt có dấu, ngược lại 'en'."""
    for ch in (text or "").lower():
        if ch in _VI_CHARS:
            return "vi"
    return "en"


class TTSProvider(TTSProviderBase):
    """Oriagent self-hosted voice (Piper) TTS.

    API: POST {base}/tts/generate  {text, language, voice, format:"wav"} -> WAV (22050Hz mono 16-bit)
    Auth: Authorization: Bearer <api_key>
    Output WAV is resampled to the device sample rate by the base class (pydub).
    """

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        base = (config.get("api_url") or "https://voice.oriagent.com/api/public/v1").rstrip("/")
        # accept either the API base or a full generate URL
        if base.endswith("/tts/generate"):
            self.api_url = base
        else:
            self.api_url = f"{base}/tts/generate"
        self.api_key = config.get("api_key", "")
        self.language = _normalize_language(config.get("language"), default="vi")
        # voice phải khớp language; nếu không hợp lệ hoặc lệch ngôn ngữ (vd còn sót
        # giọng EdgeTTS, hoặc voice mặc định vi-medium khi language=en) -> map lại.
        voice = config.get("voice") or ""
        if _VOICE_LANG.get(voice) != self.language:
            mapped = _DEFAULT_VOICE_BY_LANG.get(self.language, "vi-medium")
            if voice and voice != mapped:
                logger.bind(tag=TAG).warning(
                    f"Oriagent Voice TTS: voice '{voice}' không khớp ngôn ngữ "
                    f"'{self.language}', dùng '{mapped}'"
                )
            voice = mapped
        self.voice = voice
        # API supports wav | pcm; we use wav so the base can decode/resample it
        self.audio_file_type = config.get("format", "wav")

    def generate_filename(self, extension=".wav"):
        return os.path.join(
            self.output_file,
            f"oriagent-tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}",
        )

    async def text_to_speak(self, text, output_file):
        if not self.api_key:
            raise Exception("Oriagent Voice TTS: api_key chưa được cấu hình")

        # Phát hiện ngôn ngữ thực tế của câu này; nếu khớp ngôn ngữ cấu hình thì
        # giữ giọng người dùng chọn, ngược lại dùng giọng mặc định của ngôn ngữ đó.
        lang = _detect_text_lang(text)
        voice = self.voice if lang == self.language else _DEFAULT_VOICE_BY_LANG.get(lang, "vi-medium")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "language": lang,
            "voice": voice,
            "format": "wav",
        }

        response = requests.post(
            self.api_url, json=payload, headers=headers, timeout=30
        )

        if response.status_code != 200:
            raise Exception(
                f"Oriagent Voice TTS lỗi {response.status_code}: {response.text[:300]}"
            )

        audio_content = response.content
        if not audio_content:
            raise Exception("Oriagent Voice TTS: phản hồi rỗng")

        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "wb") as f:
                f.write(audio_content)
            return output_file
        return audio_content
