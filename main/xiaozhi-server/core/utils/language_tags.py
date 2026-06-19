"""Xử lý nhãn ngôn ngữ [vi]/[en] dùng chung cho TTS — NGUỒN DUY NHẤT.

LLM gắn nhãn [vi]/[en] để báo đoạn nào tiếng Việt / tiếng Anh.
- Provider TỰ xử lý nhãn (vd Edge TTS song ngữ) đặt thuộc tính lớp
  handles_language_tags = True -> base.py KHÔNG strip, provider nhận nhãn
  nguyên vẹn và tự tách giọng.
- Provider KHÔNG tự xử lý -> base.py gọi strip_language_tags (tránh đọc
  "vi"/"en" thành tiếng).

Đổi định dạng nhãn sau này chỉ cần sửa file này.
"""
import re

MARKER_VI = "[vi]"
MARKER_EN = "[en]"

# Regex CƠ BẢN (tương thích hành vi cũ của main): [xx] hoặc [xxx].
# Dùng cho provider không tự xử lý + lịch sử hội thoại.
_BASIC_TAG_RE = re.compile(r"\[[a-z]{2,3}\]", re.IGNORECASE)


def strip_language_tags(text: str) -> str:
    """Bỏ nhãn [vi]/[en]... khỏi text (giữ y hành vi cũ: xóa nhãn + gộp space đôi)."""
    if not text:
        return text
    return re.sub(r"  +", " ", _BASIC_TAG_RE.sub("", text))


# ===== Phần cho provider TỰ xử lý nhãn (oriagent_edge song ngữ) =====

# Ký tự đặc trưng tiếng Việt để đoán ngôn ngữ khi thiếu nhãn (fallback).
_VI_CHARS = set(
    "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
)


def detect_lang(text: str) -> str:
    for ch in (text or "").lower():
        if ch in _VI_CHARS:
            return "vi"
    return "en"


# Regex RỘNG: xóa MỌI nhãn lạ [xxx] còn sót (hoa/thường, có space) — không để lọt ra TTS.
_BROAD_TAG_RE = re.compile(r"\[\s*[a-zA-Z]{1,12}\s*\]")


def strip_stray_tags(s: str) -> str:
    return _BROAD_TAG_RE.sub(" ", s or "").strip()


# Sửa nhãn bị CỤT do framework streaming nuốt '[' (vd: 'vi]' -> '[vi]').
_BROKEN_RE = re.compile(r"(?<!\[)\b(vi|en)\]", re.IGNORECASE)


def repair_markers(text: str) -> str:
    return _BROKEN_RE.sub(lambda m: "[" + m.group(1).lower() + "]", text or "")


# Ngoặc/nháy KHÔNG phát âm — framework cắt câu hay làm chúng lạc ra đầu/cuối đoạn -> bỏ.
_NOISE_TABLE = {ord(c): " " for c in '"“”«»（）()[]{}【】「」『』《》'}


def clean_chunk(s: str) -> str:
    s = (s or "").translate(_NOISE_TABLE)
    s = re.sub(r"\s+", " ", s).strip()
    # bỏ dấu câu mồ côi ở đầu đoạn do cắt câu (vd: '- What...', ', sad')
    s = re.sub(r"^[\s,.\-:;…•·]+", "", s)
    return s.strip()


# Lưới đỡ khi LLM quên nhãn: bắt cụm tiếng Anh trong ngoặc kép (vd: "happy").
_QUOTED_EN_RE = re.compile(r"[\"“]([A-Za-z][A-Za-z '\-]*?)[\"”]")


def _split_inline_en(chunk):
    parts = []
    pos = 0
    for m in _QUOTED_EN_RE.finditer(chunk):
        pre = chunk[pos:m.start()]
        if pre.strip():
            parts.append((None, pre))
        parts.append(("en", m.group(1)))
        pos = m.end()
    tail = chunk[pos:]
    if tail.strip():
        parts.append((None, tail))
    return parts or [(None, chunk)]


def _parse_markers(text, marker_vi=MARKER_VI, marker_en=MARKER_EN):
    pattern = re.compile(re.escape(marker_vi) + "|" + re.escape(marker_en), re.IGNORECASE)
    mvi = marker_vi.lower()
    segs = []
    pos = 0
    cur = None
    for m in pattern.finditer(text):
        chunk = strip_stray_tags(text[pos:m.start()])
        if chunk:
            segs.append((cur, chunk))
        cur = "vi" if m.group().lower() == mvi else "en"
        pos = m.end()
    tail = strip_stray_tags(text[pos:])
    if tail:
        segs.append((cur, tail))
    return segs


def parse_bilingual(text, marker_vi=MARKER_VI, marker_en=MARKER_EN,
                    detect_quoted_en=True, fallback="auto-detect"):
    """Tách text song ngữ -> list (lang, chunk) đã GỘP đoạn cùng ngôn ngữ liền nhau.
    lang = 'vi' | 'en'. Đã sửa nhãn cụt, xóa nhãn/ngoặc, lưới đỡ ngoặc kép."""
    text = repair_markers(text)
    segments = _parse_markers(text, marker_vi, marker_en)
    if detect_quoted_en:
        expanded = []
        for seg_lang, chunk in segments:
            if seg_lang == "en":
                expanded.append((seg_lang, chunk))
            else:
                # phần ngoài ngoặc kép kế thừa ngôn ngữ NỀN (tránh từ Việt không dấu bị nhầm)
                base_lang = seg_lang or detect_lang(chunk)
                for sub_lang, sub in _split_inline_en(chunk):
                    expanded.append(("en" if sub_lang == "en" else base_lang, sub))
        segments = expanded
    merged = []
    for seg_lang, raw in segments:
        chunk = clean_chunk(raw)
        if not chunk:
            continue
        if seg_lang:
            lang = seg_lang
        else:
            lang = detect_lang(chunk) if fallback == "auto-detect" else fallback
        if merged and merged[-1][0] == lang:
            merged[-1][1] = (merged[-1][1] + " " + chunk).strip()
        else:
            merged.append([lang, chunk])
    return [(lang, chunk) for lang, chunk in merged if chunk]


# ===== Hiển thị: bỏ nhãn + ngoặc/nháy khỏi CHỮ trên UI =====
_DISPLAY_NOISE = {ord(c): "" for c in '"“”«»()[]【】「」『』'}


def strip_display(text: str) -> str:
    """Làm sạch chữ hiển thị: sửa nhãn cụt -> bỏ nhãn [..] -> bỏ ngoặc/nháy."""
    if not text:
        return text
    text = _BROAD_TAG_RE.sub("", repair_markers(text)).translate(_DISPLAY_NOISE)
    return re.sub(r"\s{2,}", " ", text).strip()
