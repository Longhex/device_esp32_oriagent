"""Image Resizer & Re-host Utility

Download ảnh từ URL gốc (kể cả signed URL không có extension),
detect format, resize, lưu với tên file có extension rõ ràng,
và trả về URL public để firmware download.

Flow:
  1. Check cache (md5 hash URL gốc) → hit thì trả ngay
  2. HTTP GET URL gốc → lấy bytes + Content-Type
  3. Detect format từ Content-Type hoặc magic bytes (Pillow)
  4. Resize (skip GIF animated để giữ animation)
  5. Save data/image_cache/{hash}.{ext}
  6. Trả URL: http://<server>:<port>/images/{hash}.{ext}
"""

import hashlib
import os
import time
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

import httpx

from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

# Content-Type → extension mapping
_MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/svg+xml": ".svg",
}

# Pillow format name → extension
_PIL_FORMAT_TO_EXT = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "GIF": ".gif",
    "WEBP": ".webp",
    "BMP": ".bmp",
    "TIFF": ".tiff",
}


class ImageResizer:
    """Download, resize, cache, và serve ảnh với extension đúng."""

    def __init__(self, config: dict):
        """
        Args:
            config: dict từ config.yaml, ví dụ:
                image_display:
                    enabled: true
                    max_width: 320
                    max_height: 240
                    quality: 85
                    cache_dir: data/image_cache
                    cache_ttl_hours: 24
                    public_url_base: http://103.143.207.89:8003
        """
        img_config = config.get("image_display", {})
        self.enabled = img_config.get("enabled", True)
        self.max_width = int(img_config.get("max_width", 320))
        self.max_height = int(img_config.get("max_height", 240))
        self.quality = int(img_config.get("quality", 85))
        self.cache_ttl_hours = int(img_config.get("cache_ttl_hours", 24))

        # Cache directory
        cache_dir = img_config.get("cache_dir", "data/image_cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Public URL base cho firmware download (phải reachable từ device)
        # Nếu không set → dùng server config
        server_config = config.get("server", {})
        default_base = f"http://0.0.0.0:{server_config.get('http_port', 8003)}"
        self.public_url_base = img_config.get(
            "public_url_base",
            default_base
        ).rstrip("/")

        # HTTP client (reuse pool)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

        logger.bind(tag=TAG).info(
            f"ImageResizer ready — max={self.max_width}x{self.max_height} "
            f"quality={self.quality} cache={self.cache_dir} "
            f"public_base={self.public_url_base}"
        )

    async def process(self, original_url: str) -> Optional[str]:
        """Xử lý ảnh: download → detect → resize → cache → trả public URL.

        Args:
            original_url: URL ảnh gốc (có thể signed, không có extension)

        Returns:
            Public URL có extension đúng (e.g. http://server:8003/images/abc123.jpg)
            hoặc None nếu xử lý thất bại.
        """
        if not self.enabled:
            return original_url  # Bypass — gửi URL gốc

        try:
            # 1. Hash URL gốc → cache key
            url_hash = hashlib.md5(original_url.encode()).hexdigest()[:12]
            logger.bind(tag=TAG).info(
                f"Processing image: len={len(original_url)} url={original_url[:250]}"
            )

            # 2. Check cache (bất kỳ file nào match hash prefix)
            cached = self._find_cached(url_hash)
            if cached:
                logger.bind(tag=TAG).debug(f"Cache hit: {cached.name}")
                return f"{self.public_url_base}/images/{cached.name}"

            # 3. Download
            image_bytes, content_type = await self._download(original_url)
            if image_bytes is None:
                return None

            # 4. Detect format + resize
            result_bytes, ext = self._resize(image_bytes, content_type)
            if result_bytes is None:
                return None

            # 5. Save
            filename = f"{url_hash}{ext}"
            save_path = self.cache_dir / filename
            save_path.write_bytes(result_bytes)
            logger.bind(tag=TAG).info(
                f"Image cached: {filename} ({len(result_bytes)} bytes)"
            )

            # 6. Cleanup old cache (non-blocking, best-effort)
            self._cleanup_old()

            return f"{self.public_url_base}/images/{filename}"

        except Exception as e:
            logger.bind(tag=TAG).error(f"Image process failed: {e} | URL: {original_url[:80]}")
            return None

    def _find_cached(self, url_hash: str) -> Optional[Path]:
        """Tìm file trong cache có tên bắt đầu bằng url_hash."""
        for f in self.cache_dir.iterdir():
            if f.is_file() and f.stem == url_hash:
                # Check TTL
                age_hours = (time.time() - f.stat().st_mtime) / 3600
                if age_hours < self.cache_ttl_hours:
                    return f
                else:
                    # Expired → xoá
                    f.unlink(missing_ok=True)
                    return None
        return None

    async def _download(self, url: str) -> Tuple[Optional[bytes], str]:
        """Download ảnh, trả (bytes, content_type)."""
        try:
            logger.bind(tag=TAG).debug(f"Downloading image: {url}")
            resp = await self._client.get(url)
            if resp.status_code != 200:
                logger.bind(tag=TAG).warning(
                    f"Download failed: HTTP {resp.status_code} | URL_LEN={len(url)} | {url[:200]}"
                )
                return None, ""
            content_type = resp.headers.get("content-type", "").split(";")[0].strip()
            return resp.content, content_type
        except Exception as e:
            logger.bind(tag=TAG).warning(f"Download error: {e} | {url[:80]}")
            return None, ""

    def _resize(self, image_bytes: bytes, content_type: str) -> Tuple[Optional[bytes], str]:
        """Resize ảnh, trả (output_bytes, extension).

        GIF → skip resize (giữ animation), chỉ passthrough.
        Các format khác → resize fit trong max_width x max_height.
        """
        try:
            from PIL import Image

            img = Image.open(BytesIO(image_bytes))
            pil_format = img.format or ""
            ext = _PIL_FORMAT_TO_EXT.get(pil_format, "")

            # Fallback extension từ content-type nếu Pillow không detect được
            if not ext:
                ext = _MIME_TO_EXT.get(content_type.lower(), ".jpg")

            # GIF animated → skip resize, giữ nguyên bytes gốc
            if pil_format == "GIF":
                n_frames = getattr(img, "n_frames", 1)
                if n_frames > 1:
                    logger.bind(tag=TAG).debug(
                        f"GIF animated ({n_frames} frames) — skip resize"
                    )
                    return image_bytes, ".gif"

            # Resize nếu lớn hơn max
            w, h = img.size
            if w > self.max_width or h > self.max_height:
                img.thumbnail((self.max_width, self.max_height), Image.LANCZOS)
                logger.bind(tag=TAG).debug(
                    f"Resized: {w}x{h} → {img.size[0]}x{img.size[1]}"
                )

            # Encode output
            output = BytesIO()
            if pil_format in ("JPEG", "") or ext == ".jpg":
                # Convert RGBA/P → RGB cho JPEG
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(output, format="JPEG", quality=self.quality, optimize=True)
                ext = ".jpg"
            elif pil_format == "PNG":
                img.save(output, format="PNG", optimize=True)
                ext = ".png"
            elif pil_format == "WEBP":
                img.save(output, format="WEBP", quality=self.quality)
                ext = ".webp"
            elif pil_format == "GIF":
                # Single-frame GIF
                img.save(output, format="GIF")
                ext = ".gif"
            else:
                # Unknown format → encode as JPEG
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(output, format="JPEG", quality=self.quality, optimize=True)
                ext = ".jpg"

            return output.getvalue(), ext

        except Exception as e:
            logger.bind(tag=TAG).warning(f"Resize failed: {e}")
            # Fallback: trả bytes gốc với extension từ content-type
            ext = _MIME_TO_EXT.get(content_type.lower(), ".jpg")
            return image_bytes, ext

    def _cleanup_old(self):
        """Best-effort xoá file cũ hơn TTL. Non-blocking."""
        try:
            now = time.time()
            max_age = self.cache_ttl_hours * 3600
            count = 0
            for f in self.cache_dir.iterdir():
                if f.is_file() and (now - f.stat().st_mtime) > max_age:
                    f.unlink(missing_ok=True)
                    count += 1
            if count > 0:
                logger.bind(tag=TAG).debug(f"Cache cleanup: removed {count} expired files")
        except Exception:
            pass  # Best-effort

    async def close(self):
        """Đóng HTTP client pool."""
        await self._client.aclose()
