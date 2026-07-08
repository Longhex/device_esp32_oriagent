"""
Nghe thử câu đệm (filler preview) — CHỈ để test trên manager-web.

Browser gọi GET /mcp/filler/preview?mac=<mac>&text=<câu> → server render câu đó
bằng ĐÚNG giọng TTS của agent (theo mac) → trả file audio (wav/mp3) để phát.

Không phụ thuộc phiên WebSocket: dựng tts tạm từ config agent rồi render một câu.
- oriagent_voice (realtime, bám conn) → gọi thẳng API /tts/generate (conn-free).
- provider file-based (edge…) → text_to_speak(text, None) → bytes.
"""

import httpx
from aiohttp import web

from config.logger import setup_logging
from config.manage_api_client import get_agent_models
from core.utils.modules_initialize import initialize_tts

TAG = __name__
logger = setup_logging()

DEFAULT_TEXT = "Ừm, để mình nghĩ xíu nha"
MAX_TEXT = 200


class FillerPreviewHandler:
    def __init__(self, config: dict):
        self.config = config

    async def handle_get(self, request):
        return await self._render(request)

    async def handle_post(self, request):
        return await self._render(request)

    async def _render(self, request):
        try:
            mac = (request.query.get("mac") or "").strip()
            text = (request.query.get("text") or DEFAULT_TEXT).strip()[:MAX_TEXT]
            if not mac:
                return web.json_response({"error": "thiếu mac"}, status=400)
            if not text:
                text = DEFAULT_TEXT

            # Lấy config agent theo mac (đọc DB tươi qua manager-api)
            cfg = await get_agent_models(mac, mac, {})
            if not cfg or not cfg.get("TTS") or not cfg.get("selected_module", {}).get("TTS"):
                return web.json_response({"error": "không lấy được config TTS của agent"}, status=404)
            cfg.setdefault("delete_audio", True)

            tts = initialize_tts(cfg)
            audio, mime = await self._render_audio(tts, text)
            if not audio:
                return web.json_response(
                    {"error": "giọng này chưa hỗ trợ nghe thử"}, status=422
                )
            return web.Response(body=audio, content_type=mime, headers={"Cache-Control": "no-store"})
        except Exception as e:
            logger.bind(tag=TAG).warning(f"filler preview lỗi: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def _render_audio(self, tts, text):
        """Trả (audio_bytes, mime) hoặc (None, None)."""
        # 1) oriagent_voice realtime → gọi thẳng /tts/generate (không cần conn)
        gen_url = getattr(tts, "generate_url", None)
        api_key = getattr(tts, "api_key", "")
        if gen_url and api_key:
            try:
                async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=30.0) as client:
                    r = await client.post(
                        gen_url,
                        json={"text": text, "language": getattr(tts, "language", "auto"), "format": "wav"},
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    )
                    if r.status_code == 200:
                        payload = r.json()
                        if payload.get("ok"):
                            audio_url = (payload.get("data") or {}).get("audio_url")
                            if audio_url:
                                a = await client.get(audio_url, timeout=30.0)
                                if a.status_code == 200 and a.content:
                                    return a.content, "audio/wav"
                    logger.bind(tag=TAG).warning(f"generate preview lỗi: {r.status_code} {r.text[:120]}")
            except Exception as e:
                logger.bind(tag=TAG).warning(f"oriagent generate preview lỗi: {e}")
            return None, None

        # 2) provider file-based → text_to_speak(text, None) → bytes
        if hasattr(tts, "text_to_speak"):
            try:
                audio_bytes = await tts.text_to_speak(text, None)
                if audio_bytes:
                    ftype = str(getattr(tts, "audio_file_type", "wav")).lower()
                    mime = "audio/mpeg" if ftype in ("mp3", "mpeg") else "audio/wav"
                    return audio_bytes, mime
            except Exception as e:
                logger.bind(tag=TAG).warning(f"text_to_speak preview lỗi: {e}")
            return None, None

        return None, None
