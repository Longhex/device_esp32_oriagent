import re

# Form ảnh markdown hoàn chỉnh: ![alt](http(s)://...) — chỉ nhận URL http/https,
# URL không chứa khoảng trắng/`)` (khớp quy ước MarkdownCleaner trong core/utils/tts.py).
_IMG_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")

# Prefix dở dang của form ảnh nằm ở CUỐI buffer (do LLM stream cắt token giữa chừng):
#   "!", "![alt đang gõ", "![alt]", "![alt](https://đang-tải-dở"
# Phần này phải giữ lại chờ token sau, không được đẩy xuống TTS ngay.
_PARTIAL_RE = re.compile(r"!(?:\[[^\]]*(?:\](?:\([^)\s]*)?)?)?$")


class StreamingImageExtractor:
    """Lọc ảnh markdown ra khỏi text stream của LLM, theo từng token/chunk.

    Dùng 1 instance cho mỗi turn hội thoại (tạo mới ở chat() depth==0):
      - feed(chunk)  -> (text_cho_tts, [(alt, url), ...])
      - flush()      -> (text_còn_giữ, [(alt, url), ...])  gọi khi hết stream

    Vì LLM nhả token nhỏ, form ``![alt](url)`` có thể bị cắt giữa chừng qua nhiều
    chunk — extractor giữ lại phần đuôi "có thể là ảnh đang gõ dở" và chỉ nhả text
    chắc chắn không thuộc form ảnh. URL trùng trong cùng turn chỉ báo 1 lần.
    """

    # Giữ tối đa chừng này ký tự chờ form hoàn chỉnh; quá thì coi như không phải
    # ảnh và nhả xuống TTS (MarkdownCleaner phía sau vẫn dọn mảnh URL thừa).
    MAX_HOLD = 512

    def __init__(self):
        self._buf = ""
        self._seen_urls = set()

    def _extract_complete(self, text, images):
        def _sub(m):
            alt, url = m.group(1), m.group(2)
            if url not in self._seen_urls:
                self._seen_urls.add(url)
                images.append((alt, url))
            return ""

        return _IMG_RE.sub(_sub, text)

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
