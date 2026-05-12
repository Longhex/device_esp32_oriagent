"""
Lightweight perf metrics logger — JSON-line format cho dễ grep / pipe sang
log aggregator (ELK, Loki, Vector...).

Pattern:
    from core.utils import perf_metrics
    perf_metrics.record("oriagent_ttft_ms", 1287.0, session=sid, conv=convid)
    perf_metrics.record("blaze_ttfb_ms",   1102.3, text_len=145)

Output (đi qua loguru, vào file log của xiaozhi-server):
    PERF {"metric":"oriagent_ttft_ms","value_ms":1287.0,"ts":1700000000,"session":"abc..."}

Mỗi `dump_every` events, dump 1 dòng stats kèm theo:
    PERF {"metric":"oriagent_ttft_ms_stats","n":50,"min_ms":...,"med_ms":...,"p95_ms":...}
"""

from __future__ import annotations

import json
import statistics
import time
from collections import deque
from threading import Lock
from typing import Any, Dict, Optional

from config.logger import setup_logging

TAG = "perf"
logger = setup_logging()


class _Recorder:
    __slots__ = ("name", "values", "lock", "dump_every", "_count_since_dump")

    def __init__(self, name: str, window: int = 200, dump_every: int = 50):
        self.name = name
        self.values: deque[float] = deque(maxlen=window)
        self.lock = Lock()
        self.dump_every = dump_every
        self._count_since_dump = 0

    def record(self, value_ms: float, extra: Optional[Dict[str, Any]] = None) -> None:
        snapshot: Optional[list[float]] = None
        with self.lock:
            self.values.append(value_ms)
            self._count_since_dump += 1
            if self._count_since_dump >= self.dump_every:
                self._count_since_dump = 0
                snapshot = list(self.values)

        event: Dict[str, Any] = {
            "metric": self.name,
            "value_ms": round(value_ms, 1),
            "ts": int(time.time()),
        }
        if extra:
            event.update(extra)
        logger.bind(tag=TAG).info(f"PERF {json.dumps(event, ensure_ascii=False)}")

        if snapshot is not None:
            self._dump_stats(snapshot)

    def _dump_stats(self, snapshot: list[float]) -> None:
        if not snapshot:
            return
        n = len(snapshot)
        sorted_v = sorted(snapshot)
        p95_idx = min(int(n * 0.95), n - 1)
        stats = {
            "metric": f"{self.name}_stats",
            "n": n,
            "min_ms": round(sorted_v[0], 1),
            "med_ms": round(statistics.median(snapshot), 1),
            "mean_ms": round(statistics.mean(snapshot), 1),
            "p95_ms": round(sorted_v[p95_idx], 1),
            "max_ms": round(sorted_v[-1], 1),
            "ts": int(time.time()),
        }
        logger.bind(tag=TAG).info(f"PERF {json.dumps(stats)}")


_recorders: Dict[str, _Recorder] = {}
_recorders_lock = Lock()


def _get(name: str) -> _Recorder:
    rec = _recorders.get(name)
    if rec is not None:
        return rec
    with _recorders_lock:
        rec = _recorders.get(name)
        if rec is None:
            rec = _Recorder(name)
            _recorders[name] = rec
        return rec


def record(metric: str, value_ms: float, **extra: Any) -> None:
    """Ghi 1 event + (mỗi 50 events) dump rolling stats."""
    try:
        _get(metric).record(value_ms, extra or None)
    except Exception as e:
        # Không bao giờ làm crash caller vì metric logging
        logger.bind(tag=TAG).debug(f"perf.record failed: {e}")


def snapshot(metric: str) -> Optional[Dict[str, Any]]:
    """Lấy stats hiện tại của 1 metric, dùng để health-check (Task 3.1)."""
    rec = _recorders.get(metric)
    if rec is None:
        return None
    with rec.lock:
        values = list(rec.values)
    if not values:
        return None
    sorted_v = sorted(values)
    n = len(values)
    p95_idx = min(int(n * 0.95), n - 1)
    return {
        "n": n,
        "min_ms": sorted_v[0],
        "med_ms": statistics.median(values),
        "mean_ms": statistics.mean(values),
        "p95_ms": sorted_v[p95_idx],
        "max_ms": sorted_v[-1],
    }
