import os
import io
import uuid
import asyncio
import requests
from datetime import datetime
from pydub import AudioSegment
from core.providers.tts.base import TTSProviderBase
from core.utils.language_tags import (
    parse_bilingual,
    clean_chunk,
    strip_stray_tags,
    detect_lang,
)
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    """Oriagent Voice - Microsoft Edge TTS (cloud) qua voice.oriagent.com.

    Provider TỰ xử lý nhãn [vi]/[en] (handles_language_tags=True) -> base.py KHÔNG
    strip nhãn trước, để provider tách giọng theo nhãn.

    3 chế độ theo field Language:
      - "vi"/"en": 1 giọng cố định (Voice Type). Giọng Multilingual luôn gửi language=en.
      - "auto": SONG NGỮ. Ưu tiên nhãn [vi]/[en] do LLM gắn -> mỗi đoạn đọc bằng giọng đúng,
        tổng hợp SONG SONG rồi GHÉP theo thứ tự gốc. Câu thuần 1 ngôn ngữ -> 1 request.
        Thiếu nhãn -> lưới đỡ (ngoặc kép) + fallback auto-detect.
    """

    # Provider tự bóc/tách nhãn -> báo base.py đừng strip nhãn trước.
    handles_language_tags = True

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        base = (config.get("api_url") or "https://voice.oriagent.com/api/public/v1").rstrip("/")
        self.api_url = base if base.endswith("/tts/generate") else f"{base}/tts/generate"
        self.api_key = config.get("api_key", "")
        self.voice = config.get("voice", "en-US-AvaMultilingualNeural")
        self.default_language = "vi" if str(config.get("language", "")).lower().startswith("vi") else "en"
        self.is_multilingual = "multilingual" in self.voice.lower()
        self.auto_bilingual = str(config.get("language", "")).strip().lower() == "auto"
        # cặp giọng cho chế độ Auto (cấu hình được)
        self.auto_voice_vi = config.get("auto_voice_vi") or "vi-VN-HoaiMyNeural"
        self.auto_voice_en = config.get("auto_voice_en") or "en-US-AvaMultilingualNeural"
        # nhãn ngôn ngữ
        self.marker_vi = config.get("marker_vi") or "[vi]"
        self.marker_en = config.get("marker_en") or "[en]"
        # khoảng lặng (ms) chèn giữa 2 đoạn khi ghép; 0 = không chèn (latency thấp nhất)
        try:
            self.gap_ms = int(config.get("gap_ms", 0) or 0)
        except (TypeError, ValueError):
            self.gap_ms = 0
        # số đoạn tổng hợp song song tối đa /câu
        try:
            self.max_parallel = max(1, int(config.get("max_parallel", 4) or 4))
        except (TypeError, ValueError):
            self.max_parallel = 4
        # khi thiếu nhãn: "auto-detect" (đổi giọng theo câu) hoặc "vi"/"en" (ép 1 ngôn ngữ)
        self.fallback = (config.get("fallback") or "auto-detect").strip().lower()
        # lưới đỡ: tự tách từ tiếng Anh trong ngoặc kép khi LLM quên nhãn (mặc định bật)
        self.detect_quoted_en = str(config.get("detect_quoted_en", "true")).strip().lower() not in ("false", "0", "no", "")
        self.tts_model = config.get("model", "edge-tts")
        self.rate = config.get("rate") or None
        self.pitch = config.get("pitch") or None
        self.volume = config.get("volume") or None
        self.audio_file_type = config.get("format", "mp3")

    def generate_filename(self, extension=".mp3"):
        return os.path.join(
            self.output_file,
            f"oriagent-edge-{datetime.now().date()}@{uuid.uuid4().hex}{extension}",
        )

    def _synth(self, text, language, voice):
        """Gọi API tổng hợp 1 đoạn -> bytes audio (blocking; gọi qua asyncio.to_thread)."""
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
            raise Exception(f"Oriagent Edge TTS lỗi {response.status_code}: {response.text[:300]}")
        if not response.content:
            raise Exception("Oriagent Edge TTS: phản hồi rỗng")
        return response.content

    def _concat(self, parts):
        """Ghép các đoạn audio THEO THỨ TỰ gốc (decode -> nối -> export)."""
        gap = AudioSegment.silent(duration=self.gap_ms) if self.gap_ms > 0 else None
        combined = None
        for b in parts:
            seg = AudioSegment.from_file(io.BytesIO(b), format=self.audio_file_type)
            if combined is None:
                combined = seg
            else:
                if gap is not None:
                    combined += gap
                combined += seg
        buf = io.BytesIO()
        combined.export(buf, format=self.audio_file_type)
        return buf.getvalue()

    async def _render(self, text):
        # Chế độ 1 giọng cố định (vi/en) — vẫn xóa nhãn lạ phòng khi lọt vào
        if not self.auto_bilingual:
            clean = clean_chunk(strip_stray_tags(text))
            voice = self.voice
            language = "en" if self.is_multilingual else detect_lang(clean)
            return await asyncio.to_thread(self._synth, clean or text, language, voice)

        # Chế độ Auto song ngữ — tách theo nhãn (module language_tags lo: repair/parse/clean/merge)
        segments = parse_bilingual(
            text, self.marker_vi, self.marker_en, self.detect_quoted_en, self.fallback
        )

        # Fast path: thuần 1 ngôn ngữ -> 1 request, không ghép
        if len(segments) <= 1:
            lang, chunk = segments[0] if segments else (self.default_language, clean_chunk(strip_stray_tags(text)))
            voice = self.auto_voice_vi if lang == "vi" else self.auto_voice_en
            return await asyncio.to_thread(self._synth, chunk or text, lang, voice)

        # Nhiều đoạn: tổng hợp SONG SONG (giới hạn max_parallel) -> ghép THEO THỨ TỰ gốc
        sem = asyncio.Semaphore(self.max_parallel)

        async def one(seg):
            lang, chunk = seg
            voice = self.auto_voice_vi if lang == "vi" else self.auto_voice_en
            async with sem:
                return await asyncio.to_thread(self._synth, chunk, lang, voice)

        parts = await asyncio.gather(*[one(s) for s in segments])
        return await asyncio.to_thread(self._concat, parts)

    async def text_to_speak(self, text, output_file):
        if not self.api_key:
            raise Exception("Oriagent Edge TTS: api_key chưa được cấu hình")

        audio_content = await self._render(text)
        if not audio_content:
            raise Exception("Oriagent Edge TTS: phản hồi rỗng")

        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "wb") as f:
                f.write(audio_content)
            return output_file
        return audio_content
