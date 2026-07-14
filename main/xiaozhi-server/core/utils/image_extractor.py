import re

# Match cả 2 form:
#   - ![alt](url)   — markdown image chuẩn
#   - [alt](url)    — markdown link (Oriagent/Dify thường trả link ảnh dạng này)
# Chỉ nhận URL http/https, URL không chứa khoảng trắng/`)`.
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\((https?://[^)\s]+)\)")

# Prefix dở dang nằm ở CUỐI buffer (LLM stream cắt token giữa chừng):
#   "!", "![alt đang gõ", "[alt đang gõ", "[alt]", "[alt](https://đang-tải-dở"
# Phần này phải giữ lại chờ token sau, không được đẩy xuống TTS ngay.
# Match cả trường hợp có "!" phía trước lẫn không có.
_PARTIAL_RE = re.compile(r"!?\[(?:[^\]]*(?:\](?:\([^)\s]*)?)?)?\s*$")

# ── Filter: chỉ coi URL là ảnh nếu thoả 1 trong các điều kiện ──────────────
_IMAGE_EXT_RE = re.compile(
    r"\.(jpe?g|png|gif|webp|bmp|svg|tiff?)(\?.*)?$", re.IGNORECASE
)
_IMAGE_PATH_KEYWORDS = re.compile(
    r"/(image|img|photo|files|media|upload|picture|content)[-/]", re.IGNORECASE
)
_IMAGE_CONTENT_HINT = re.compile(
    r"(image-preview|image_preview|thumbnail|avatar)", re.IGNORECASE
)


def _is_image_url(url: str) -> bool:
    """Kiểm tra URL có vẻ là ảnh hay không (dựa trên extension hoặc path keyword).

    Mục đích: tránh false positive khi LLM trả markdown link đến HTML page/docs.
    """
    # Có extension ảnh rõ ràng
    if _IMAGE_EXT_RE.search(url.split("?")[0].split("#")[0]):
        return True
    # Path chứa keyword liên quan ảnh
    if _IMAGE_PATH_KEYWORDS.search(url):
        return True
    # URL chứa hint là ảnh (image-preview, thumbnail...)
    if _IMAGE_CONTENT_HINT.search(url):
        return True
    return False


class StreamingImageExtractor:
    """Lọc ảnh markdown ra khỏi text stream của LLM, theo từng token/chunk.

    Dùng 1 instance cho mỗi turn hội thoại (tạo mới ở chat() depth==0):
      - feed(chunk)  -> (text_cho_tts, [(alt, url), ...])
      - flush()      -> (text_còn_giữ, [(alt, url), ...])  gọi khi hết stream

    Match cả ``![alt](url)`` và ``[alt](url)`` — nhưng chỉ extract nếu URL
    thoả filter _is_image_url() (có extension ảnh hoặc path keyword ảnh).
    Nếu URL không giống ảnh (HTML page, docs...) → giữ nguyên text, không strip.

    Vì LLM nhả token nhỏ, form có thể bị cắt giữa chừng qua nhiều chunk —
    extractor giữ lại phần đuôi "có thể là link đang gõ dở" và chỉ nhả text
    chắc chắn không thuộc form link. URL trùng trong cùng turn chỉ báo 1 lần.
    """

    # Giữ tối đa chừng này ký tự chờ form hoàn chỉnh; quá thì coi như không phải
    # ảnh và nhả xuống TTS (MarkdownCleaner phía sau vẫn dọn mảnh URL thừa).
    MAX_HOLD = 512

    def __init__(self):
        self._buf = ""
        self._seen_urls = set()

    def _extract_complete(self, text, images):
        """Tìm và strip các link markdown chứa URL ảnh."""

        def _sub(m):
            alt, url = m.group(1), m.group(2)
            # Chỉ extract nếu URL trông giống ảnh
            if not _is_image_url(url):
                return m.group(0)  # Giữ nguyên link text, không strip
            if url not in self._seen_urls:
                self._seen_urls.add(url)
                images.append((alt, url))
            return ""  # Strip khỏi text (không đọc lên TTS)

        return _LINK_RE.sub(_sub, text)

    def feed(self, chunk):
        images = []
        self._buf += chunk
        cleaned = self._extract_complete(self._buf, images)

        m = _PARTIAL_RE.search(cleaned)
        if m and (len(cleaned) - m.start()) <= self.MAX_HOLD:
            emit = cleaned[: m.start()]
            self._buf = cleaned[m.start():]
        else:
            emit = cleaned
            self._buf = ""
        return emit, images

    def flush(self):
        images = []
        emit = self._extract_complete(self._buf, images)
        self._buf = ""
        return emit, images
