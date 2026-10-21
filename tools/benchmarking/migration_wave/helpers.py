"""Stdlib telemetry for isolated variant children.

Missing RSS/disk stay None. Never fabricate 0 for unavailable metrics.
Loaded either as a package relative import or via spec_from_file_location.
"""
from __future__ import annotations

import math
import os
import sys
import time
import tracemalloc
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:  # pragma: no cover
    import psutil  # type: ignore

    _PSUTIL = psutil
except Exception:  # pragma: no cover
    _PSUTIL = None


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    import json

    return json.dumps(json_safe(obj), indent=indent, allow_nan=False, sort_keys=False)


def current_rss_bytes() -> Optional[int]:
    if _PSUTIL is not None:
        try:
            value = int(_PSUTIL.Process().memory_info().rss)
            return value if value > 0 else None
        except Exception:
            return None
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/statm", "r", encoding="ascii") as handle:
                resident_pages = int(handle.read().split()[1])
            value = resident_pages * os.sysconf("SC_PAGE_SIZE")
            return value if value > 0 else None
        except (OSError, ValueError, IndexError):
            return None
    return None


def dir_size_bytes(path: str | Path) -> int:
    root = Path(path)
    if root.is_file():
        return root.stat().st_size
    total = 0
    if not root.exists():
        return 0
    for p in root.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def _optional_int(result: Dict[str, Any], key: str) -> Optional[int]:
    if key not in result:
        return None
    value = result.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class MemoryTelemetry:
    def __init__(self) -> None:
        self.peak_bytes: Optional[int] = None
        self._started_here = False

    def __enter__(self) -> "MemoryTelemetry":
        self._started_here = not tracemalloc.is_tracing()
        if self._started_here:
            tracemalloc.start()
        tracemalloc.reset_peak()
        return self

    def __exit__(self, *exc: object) -> None:
        _, peak = tracemalloc.get_traced_memory()
        self.peak_bytes = int(peak)
        if self._started_here:
            tracemalloc.stop()


def measure(func: Callable[[], Dict[str, Any]], *, repetitions: int = 1) -> Dict[str, Any]:
    if repetitions < 1:
        raise ValueError("repetitions must be >= 1")
    result = func()
    if not isinstance(result, dict) or "checksum" not in result:
        return {
            "ok": False,
            "reason": "malformed_result",
            "checksum": None,
            "runtime_best_s": None,
            "runtime_mean_s": None,
            "tracemalloc_peak_bytes": None,
            "rss_after_bytes": None,
            "disk_bytes": None,
            "input_size": None,
            "worker_count": None,
            "repetitions": repetitions,
            "payload": result if isinstance(result, dict) else None,
        }
    times: List[float] = []
    for _ in range(repetitions):
        t0 = time.perf_counter()
        func()
        times.append(time.perf_counter() - t0)
    with MemoryTelemetry() as mem:
        traced = func()
    rss = current_rss_bytes()
    disk = _optional_int(traced, "disk_bytes")
    if disk is None:
        disk = _optional_int(result, "disk_bytes")
    return {
        "ok": True,
        "reason": None,
        "checksum": result.get("checksum"),
        "disk_bytes": disk,
        "runtime_best_s": min(times) if times else None,
        "runtime_mean_s": (sum(times) / len(times)) if times else None,
        "tracemalloc_peak_bytes": mem.peak_bytes,
        "rss_after_bytes": rss,
        "repetitions": repetitions,
        "feature_count": result.get("feature_count"),
        "input_size": result.get("input_size"),
        "worker_count": result.get("worker_count", 1),
        "production_module": result.get("production_module"),
        "production_available": result.get("production_available"),
        "status": result.get("status"),
        "surface": result.get("surface"),
        "planning_latency_s": result.get("planning_latency_s"),
        "eviction_latency_s": result.get("eviction_latency_s"),
        "retry_attempts": result.get("retry_attempts"),
        "cache_occupancy_bytes": result.get("cache_occupancy_bytes"),
        "duplicate_work": result.get("duplicate_work"),
        "partial_state": result.get("partial_state"),
        "payload": result,
    }
