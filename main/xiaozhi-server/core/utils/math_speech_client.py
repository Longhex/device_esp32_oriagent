"""Synchronous, fail-safe client for the optional MathCAT sidecar."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


class MathSpeechClient:
    """Keep formula conversion out of the server's Python 3.10 process.

    ``ConnectionHandler.chat`` is synchronous, so this client deliberately uses
    a pooled synchronous ``httpx.Client``. A small circuit breaker prevents a
    broken sidecar from adding a timeout to every formula.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        enabled: bool | None = None,
        timeout_seconds: float | None = None,
        failure_threshold: int | None = None,
        cooldown_seconds: float | None = None,
        http_client: Any | None = None,
        clock=time.monotonic,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("MATH_SPEECH_API", "http://math-speech:8100")
        ).rstrip("/")
        self.enabled = (
            _env_bool("MATH_SPEECH_ENABLED", False) if enabled is None else enabled
        )
        timeout = timeout_seconds or float(
            os.getenv("MATH_SPEECH_TIMEOUT_SECONDS", "1.5")
        )
        self.failure_threshold = failure_threshold or int(
            os.getenv("MATH_SPEECH_FAILURE_THRESHOLD", "3")
        )
        self.cooldown_seconds = cooldown_seconds or float(
            os.getenv("MATH_SPEECH_COOLDOWN_SECONDS", "30")
        )
        self._clock = clock
        self._failure_count = 0
        self._circuit_opened_at = 0.0
        self._lock = threading.Lock()
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 0.5))
        )

    def speak(self, formula: str, source: str = "latex") -> str | None:
        if not self.enabled or source not in {"latex", "mathml"}:
            return None

        now = self._clock()
        with self._lock:
            if (
                self._failure_count >= self.failure_threshold
                and now - self._circuit_opened_at < self.cooldown_seconds
            ):
                return None

        try:
            response = self._http.post(
                f"{self.base_url}/speak",
                json={source: formula},
            )
            response.raise_for_status()
            payload = response.json()
            text = payload.get("text", "") if payload.get("ok") else ""
            if not isinstance(text, str) or not text.strip():
                raise ValueError("math-speech returned an empty response")
        except Exception:
            with self._lock:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._circuit_opened_at = now
            return None

        with self._lock:
            self._failure_count = 0
            self._circuit_opened_at = 0.0
        return text.strip()

    def close(self) -> None:
        if self._owns_client:
            self._http.close()
