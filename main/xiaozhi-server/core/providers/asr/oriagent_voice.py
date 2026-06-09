import os
import time
import requests
from config.logger import setup_logging
from typing import Optional, Tuple, List
from core.providers.asr.dto.dto import InterfaceType
from core.providers.asr.base import ASRProviderBase

TAG = __name__
logger = setup_logging()


def _normalize_language(value, default="vi"):
    """Chuẩn hóa (Vietnamese, vi-VN, English, auto...) về 'vi' / 'en' / 'auto'."""
    v = (value or "").strip().lower()
    if v == "auto":
        return "auto"
    if v.startswith("vi") or v in ("vietnamese", "tiếng việt", "vn"):
        return "vi"
    if v.startswith("en") or v == "english":
        return "en"
    return default


class ASRProvider(ASRProviderBase):
    """Oriagent self-hosted voice (sherpa-onnx) STT.

    API: POST {base}/stt/transcribe  multipart audio=<WAV 16k mono 16-bit> + language -> {text,...}
    Auth: Authorization: Bearer <api_key>
    The base class already writes a 16kHz mono WAV at artifacts.file_path.
    """

    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()
        self.interface_type = InterfaceType.NON_STREAM
        base = (config.get("api_url") or "https://voice.oriagent.com/api/public/v1").rstrip("/")
        if base.endswith("/stt/transcribe"):
            self.api_url = base
        else:
            self.api_url = f"{base}/stt/transcribe"
        self.api_key = config.get("api_key", "")
        self.language = _normalize_language(config.get("language"), default="vi")
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file

        os.makedirs(self.output_dir, exist_ok=True)

    def requires_file(self) -> bool:
        return True

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, audio_format="opus", artifacts=None
    ) -> Tuple[Optional[str], Optional[str]]:
        file_path = None
        try:
            if artifacts is None or not artifacts.file_path:
                return "", None
            file_path = artifacts.file_path

            if not self.api_key:
                raise Exception("Oriagent Voice STT: api_key chưa được cấu hình")

            headers = {"Authorization": f"Bearer {self.api_key}"}
            data = {"language": self.language}

            start_time = time.time()
            with open(file_path, "rb") as audio_file:
                files = {"audio": (os.path.basename(file_path), audio_file, "audio/wav")}
                response = requests.post(
                    self.api_url, files=files, data=data, headers=headers, timeout=30
                )
            logger.bind(tag=TAG).debug(
                f"Oriagent STT耗时: {time.time() - start_time:.3f}s | 结果: {response.text[:300]}"
            )

            if response.status_code == 200:
                text = (response.json().get("text") or "").strip()
                return text, file_path
            raise Exception(
                f"Oriagent Voice STT lỗi {response.status_code}: {response.text[:300]}"
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"Oriagent Voice STT thất bại: {e}")
            return "", None
