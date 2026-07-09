import os
import time
import asyncio
import json
import requests
from config.logger import setup_logging
from typing import Optional, Tuple, List, Any
from core.providers.asr.dto.dto import InterfaceType
from core.providers.asr.base import ASRProviderBase

TAG = __name__
logger = setup_logging()


def _normalize_language(value, default="auto"):
    v = (value or "").strip().lower()
    if v == "auto":
        return "auto"
    if v.startswith("vi") or v in ("vietnamese", "tiếng việt", "vn"):
        return "vi"
    if v.startswith("en") or v == "english":
        return "en"
    return default


def _safe_preview(value: Any, limit: int = 120) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except Exception:
            text = str(value)
    text = text.replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def _extract_text_from_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()

    if isinstance(payload, list):
        parts = []
        for item in payload:
            item_text = _extract_text_from_payload(item)
            if item_text:
                parts.append(item_text)
        return " ".join(parts).strip()

    if not isinstance(payload, dict):
        return ""

    for key in ("text", "transcript", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key in ("result", "data"):
        nested_text = _extract_text_from_payload(payload.get(key))
        if nested_text:
            return nested_text

    segments = payload.get("segments")
    if isinstance(segments, list):
        segment_text = _extract_text_from_payload(segments)
        if segment_text:
            return segment_text

    return ""


def _debug_enabled() -> bool:
    return os.environ.get("DEBUG_QWEN_ASR", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


class ASRProvider(ASRProviderBase):
    """Oriagent Voice - STT Qwen3-ASR qua endpoint INTERNAL của voice.oriagent.com.

    LƯU Ý: dùng endpoint nội bộ /api/internal/stt/test (provider=qwen3_asr_vllm), phụ thuộc
    vLLM server của họ đang chạy. Không phải public API. Chữ trả về đẹp hơn sherpa (có hoa/thường + dấu câu).

    API: POST {base}/api/internal/stt/test  multipart file=<WAV 16k mono> + language_mode + provider -> {text,...}

    Concurrency note:
    - speech_to_text() chạy trong asyncio pipeline của xiaozhi-server.
    - requests.post() là blocking I/O, nên phải chạy trong worker thread bằng asyncio.to_thread().
    - Như vậy nhiều thiết bị có thể gọi Qwen STT cùng lúc mà không chặn event loop chung.
    - Không đặt semaphore/lock nội bộ ở provider này; giới hạn thực tế chỉ còn ở upstream API/rate limit
      hoặc threadpool mặc định của Python runtime.
    """

    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()
        self.interface_type = InterfaceType.NON_STREAM
        url = (config.get("api_url") or "https://voice.oriagent.com/api/internal/stt/test").rstrip("/")
        if not url.endswith("/stt/test"):
            # nhận cả khi cấu hình là base/root hoặc nhầm prefix public
            if url.endswith("/api/public/v1"):
                url = url[: -len("/api/public/v1")]
            url = f"{url}/api/internal/stt/test"
        self.api_url = url
        self.api_key = config.get("api_key", "")
        self.language_mode = _normalize_language(config.get("language"), default="auto")
        self.provider = config.get("provider", "qwen3_asr_vllm")
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file
        self.timeout = float(config.get("timeout", 60))
        os.makedirs(self.output_dir, exist_ok=True)

    def requires_file(self) -> bool:
        return True

    def _post_stt_sync(self, file_path: str) -> requests.Response:
        """Blocking HTTP call, isolated in worker thread by speech_to_text()."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"language_mode": self.language_mode, "provider": self.provider}
        with open(file_path, "rb") as audio_file:
            files = {"file": (os.path.basename(file_path), audio_file, "audio/wav")}
            return requests.post(
                self.api_url,
                files=files,
                data=data,
                headers=headers,
                timeout=self.timeout,
            )

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, audio_format="opus", artifacts=None
    ) -> Tuple[Optional[str], Optional[str]]:
        file_path = None
        try:
            if artifacts is None or not artifacts.file_path:
                return "", None
            file_path = artifacts.file_path

            if not self.api_key:
                raise Exception("Oriagent Qwen STT: api_key chưa được cấu hình")

            start_time = time.perf_counter()
            logger.bind(tag=TAG).info(
                f"[QWEN_ASR_START] session={session_id} file={os.path.basename(file_path)}"
            )
            if _debug_enabled():
                logger.bind(tag=TAG).info(
                    "[QWEN_ASR_REQUEST] session={} endpoint={} field=file mime=audio/wav language_mode={} provider={}",
                    session_id,
                    self.api_url,
                    self.language_mode,
                    self.provider,
                )

            # Quan trọng: không gọi requests.post trực tiếp trong async function,
            # nếu không event loop sẽ bị block và nhiều thiết bị sẽ bị xử lý tuần tự.
            response = await asyncio.to_thread(self._post_stt_sync, file_path)

            elapsed = time.perf_counter() - start_time
            logger.bind(tag=TAG).info(
                f"[QWEN_ASR_DONE] session={session_id} status={response.status_code} cost={elapsed:.3f}s"
            )
            if _debug_enabled():
                logger.bind(tag=TAG).debug(
                    f"Oriagent Qwen STT result: {response.text[:300]}"
                )

            if response.status_code == 200:
                try:
                    payload = response.json()
                except Exception:
                    payload = response.text

                keys = list(payload.keys())[:10] if isinstance(payload, dict) else []
                text = _extract_text_from_payload(payload)
                if _debug_enabled():
                    logger.bind(tag=TAG).info(
                        "[QWEN_ASR_RESPONSE] status={} type={} keys={} text_len={} preview={}",
                        response.status_code,
                        type(payload).__name__,
                        keys,
                        len(text),
                        _safe_preview(text or payload),
                    )
                else:
                    logger.bind(tag=TAG).info(
                        "[QWEN_ASR_RESPONSE] status={} type={} text_len={}",
                        response.status_code,
                        type(payload).__name__,
                        len(text),
                    )
                return text, file_path
            if response.status_code == 429:
                raise Exception(
                    f"Oriagent Qwen STT rate limited 429: {response.text[:300]}"
                )
            raise Exception(
                f"Oriagent Qwen STT lỗi {response.status_code}: {response.text[:300]}"
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"Oriagent Qwen STT thất bại: {e}")
            return "", None
