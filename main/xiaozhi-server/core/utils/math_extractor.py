"""Streaming LaTeX delimiter extractor used before text reaches TTS."""

from __future__ import annotations

import re
from typing import Protocol


class MathSpeaker(Protocol):
    def speak(self, formula: str, source: str = "latex") -> str | None: ...


_PURE_NUMBER_RE = re.compile(r"^[\d\s.,]+$")
_SINGLE_IDENTIFIER_RE = re.compile(
    r"^[A-Za-z\u0370-\u03ff](?:[A-Za-z0-9\u0370-\u03ff]|_[A-Za-z0-9]+)*$"
)
_MATH_SIGNAL_RE = re.compile(
    r"\\[A-Za-z]+|[=+\-*/^_<>≤≥≠≈√∫∑∏()]|"
    r"\d[A-Za-z\u0370-\u03ff]|[A-Za-z\u0370-\u03ff]\d"
)


def _is_escaped(text: str, index: int) -> bool:
    slashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        slashes += 1
        index -= 1
    return slashes % 2 == 1


def _looks_like_formula(value: str) -> bool:
    value = value.strip()
    if not value or _PURE_NUMBER_RE.fullmatch(value):
        return False
    if _SINGLE_IDENTIFIER_RE.fullmatch(value):
        return True
    return bool(_MATH_SIGNAL_RE.search(value))


class StreamingMathExtractor:
    """Replace complete LaTeX spans with spoken text across arbitrary chunks.

    Supported delimiters: ``$...$``, ``$$...$$``, ``\\(...\\)`` and
    ``\\[...\\]``. Incomplete and non-mathematical spans are preserved exactly.
    """

    MAX_HOLD = 4096

    def __init__(self, speaker: MathSpeaker):
        self._speaker = speaker
        self._buf = ""

    @staticmethod
    def _next_opener(text: str) -> tuple[int, str] | None:
        index = 0
        while index < len(text):
            if (
                text.startswith("\\(", index) or text.startswith("\\[", index)
            ) and not _is_escaped(text, index):
                return index, text[index : index + 2]
            if text[index] == "$" and not _is_escaped(text, index):
                opener = "$$" if text.startswith("$$", index) else "$"
                return index, opener
            index += 1
        return None

    @staticmethod
    def _closing_index(text: str, opener: str) -> int:
        close = {"$$": "$$", "$": "$", "\\(": "\\)", "\\[": "\\]"}[opener]
        index = len(opener)
        while True:
            index = text.find(close, index)
            if index < 0:
                return -1
            if not _is_escaped(text, index):
                if opener == "$" and "\n" in text[len(opener) : index]:
                    return -2
                return index
            index += len(close)

    @staticmethod
    def _obvious_currency_prefix(text: str) -> bool:
        # Avoid holding ordinary prose such as "$5 một chiếc" until stream end.
        return bool(re.match(r"^\$\d+(?:[.,]\d+)?(?=\s|[,!?])", text))

    def _drain(self, final: bool) -> str:
        output: list[str] = []
        while self._buf:
            found = self._next_opener(self._buf)
            if found is None:
                if not final and self._buf.endswith("\\") and not _is_escaped(
                    self._buf, len(self._buf) - 1
                ):
                    output.append(self._buf[:-1])
                    self._buf = "\\"
                else:
                    output.append(self._buf)
                    self._buf = ""
                break

            start, opener = found
            if start:
                output.append(self._buf[:start])
                self._buf = self._buf[start:]
                continue

            close_at = self._closing_index(self._buf, opener)
            if close_at == -2:
                output.append(opener)
                self._buf = self._buf[len(opener) :]
                continue
            if close_at < 0:
                if opener == "$" and self._obvious_currency_prefix(self._buf):
                    output.append("$")
                    self._buf = self._buf[1:]
                    continue
                if final:
                    output.append(self._buf)
                    self._buf = ""
                elif len(self._buf) > self.MAX_HOLD:
                    output.append(opener)
                    self._buf = self._buf[len(opener) :]
                break

            closer = {"$$": "$$", "$": "$", "\\(": "\\)", "\\[": "\\]"}[
                opener
            ]
            end = close_at + len(closer)
            source = self._buf[len(opener) : close_at]
            original = self._buf[:end]
            if _looks_like_formula(source):
                spoken = self._speaker.speak(source, source="latex")
                output.append(spoken if spoken else original)
            else:
                output.append(original)
            self._buf = self._buf[end:]

        return "".join(output)

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)
