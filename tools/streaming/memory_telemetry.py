"""Cross-platform process-memory telemetry for performance benchmarking.

PR #211's streaming benchmark reported ``tracemalloc`` peaks, which only track
Python-level allocations, not total process resident set size (RSS). This module
adds *process-level* memory evidence (RSS and, where the OS supports it, peak
RSS) alongside the ``tracemalloc`` peak, wall-clock and CPU time, and a
deterministic checksum, so memory claims can be cross-checked.

Design constraints (see ``docs/performance_memory_telemetry.md``):

* **Robust fallbacks, never fabricate.** RSS comes from ``psutil`` when
  installed, otherwise from a platform API (``/proc`` on Linux, ``resource`` for
  peak on POSIX, ``psutil`` ``peak_wset`` on Windows). When a metric cannot be
  obtained it is reported as ``None`` -- never guessed or zero-filled.
* **JSON-safe.** :func:`json_safe` / :func:`dumps` replace any non-finite float
  (NaN/Inf) with ``None`` so emitted JSON is always valid and finite.
* **Determinism first.** The measured workload must return a deterministic
  scalar checksum; timing/RSS are reported but tests should not gate on absolute
  wall-clock values.

This module is pure Python + stdlib, with ``psutil`` as an *optional* enhancer.
It contains no accelerated kernels and imports nothing from the optimized
streaming/kernel code, so it cannot affect their behavior.
"""
from __future__ import annotations

import math
import os
import platform
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Optional

__all__ = [
    "MemoryProviders",
    "TelemetryRecord",
    "get_rss_bytes",
    "get_peak_rss_bytes",
    "provider_availability",
    "json_safe",
    "dumps",
    "measure_workload",
]

# Optional dependency: psutil gives the most portable current-RSS reading.
try:  # pragma: no cover - availability is environment dependent
    import psutil  # type: ignore

    _PSUTIL = psutil
except Exception:  # pragma: no cover
    _PSUTIL = None

# resource is POSIX-only; used for peak RSS (ru_maxrss).
try:  # pragma: no cover
    import resource as _resource
except Exception:  # pragma: no cover
    _resource = None


@dataclass
class MemoryProviders:
    """Which telemetry providers are available in this interpreter/OS."""
    psutil: bool
    resource: bool
    proc_statm: bool
    platform: str


def provider_availability() -> MemoryProviders:
    """Report available providers without raising."""
    proc_statm = sys.platform.startswith("linux") and os.path.exists("/proc/self/statm")
    return MemoryProviders(
        psutil=_PSUTIL is not None,
        resource=_resource is not None,
        proc_statm=proc_statm,
        platform=sys.platform,
    )


def _rss_from_proc() -> Optional[int]:
    """Linux current RSS from /proc/self/statm (resident pages * page size)."""
    try:
        with open("/proc/self/statm", "r", encoding="ascii") as handle:
            fields = handle.read().split()
        resident_pages = int(fields[1])
        page_size = os.sysconf("SC_PAGE_SIZE")
        return resident_pages * page_size
    except (OSError, ValueError, IndexError):
        return None


def get_rss_bytes() -> Optional[int]:
    """Return current process RSS in bytes, or ``None`` if unavailable.

    Order of preference: ``psutil`` (portable) -> Linux ``/proc/self/statm``.
    Never fabricates a value; returns ``None`` when no provider succeeds.
    """
    if _PSUTIL is not None:
        try:
            return int(_PSUTIL.Process().memory_info().rss)
        except Exception:
            pass
    if sys.platform.startswith("linux"):
        return _rss_from_proc()
    return None


def get_peak_rss_bytes() -> Optional[int]:
    """Return peak (high-water-mark) process RSS in bytes, or ``None``.

    Peak RSS is a *process-lifetime* maximum on POSIX (``ru_maxrss``) and cannot
    be reset; callers should interpret it as "largest RSS so far", not the peak
    of a single measured block. Unit handling: Linux reports KiB, macOS reports
    bytes. On Windows, ``psutil`` ``peak_wset`` is used when available.
    """
    if _resource is not None:
        try:
            ru = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == "darwin":
                return int(ru)          # macOS: bytes
            return int(ru) * 1024       # Linux/other POSIX: KiB -> bytes
        except Exception:
            pass
    if _PSUTIL is not None:  # Windows path
        try:
            info = _PSUTIL.Process().memory_info()
            peak = getattr(info, "peak_wset", None)
            if peak is not None:
                return int(peak)
        except Exception:
            pass
    return None


@dataclass
class TelemetryRecord:
    """One measured workload's performance + memory telemetry."""
    label: str
    backend: Optional[str]
    input_dims: Dict[str, int]
    chunk_size: Optional[int]
    repetitions: int
    wall_best_s: float
    wall_mean_s: float
    cpu_time_s: Optional[float]
    tracemalloc_peak_bytes: Optional[int]
    rss_before_bytes: Optional[int]
    rss_after_bytes: Optional[int]
    rss_delta_bytes: Optional[int]
    peak_rss_bytes: Optional[int]
    checksum: float
    providers: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


def json_safe(value: Any) -> Any:
    """Recursively convert a structure to a JSON-safe form.

    Non-finite floats (NaN, +/-Inf) become ``None`` so the emitted JSON is valid
    and contains no ``NaN``/``Infinity`` tokens. ``None`` fields (unavailable
    metrics) are preserved as JSON ``null``.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    """Serialize ``obj`` to JSON with no NaN/Infinity tokens."""
    import json

    return json.dumps(json_safe(obj), indent=indent, allow_nan=False)


def measure_workload(
    func: Callable[[], float],
    *,
    label: str,
    repetitions: int = 3,
    backend: Optional[str] = None,
    input_dims: Optional[Dict[str, int]] = None,
    chunk_size: Optional[int] = None,
    warmup: bool = True,
) -> TelemetryRecord:
    """Run ``func`` and collect timing + memory telemetry.

    ``func`` must be deterministic and return a scalar checksum (float). It is
    called once as warm-up (unless ``warmup=False``), then ``repetitions`` times
    for timing (best and mean wall-clock via :func:`time.perf_counter`), then
    once more inside a ``tracemalloc`` window for the Python-allocation peak.

    RSS is sampled just before and after the tracemalloc window; ``peak_rss`` is
    the process-lifetime high-water mark read afterwards. All memory fields are
    ``None`` when no provider is available. The returned checksum is from the
    final call and is used by callers to assert numerical equivalence.
    """
    if repetitions < 1:
        raise ValueError("repetitions must be >= 1")

    if warmup:
        func()

    wall_times = []
    cpu_start = time.process_time()
    checksum = math.nan
    for _ in range(repetitions):
        t0 = time.perf_counter()
        checksum = float(func())
        wall_times.append(time.perf_counter() - t0)
    cpu_time = time.process_time() - cpu_start

    # Dedicated tracemalloc + RSS window (kept separate from timing so tracing
    # overhead does not contaminate wall-clock numbers).
    rss_before = get_rss_bytes()
    already_tracing = tracemalloc.is_tracing()
    if not already_tracing:
        tracemalloc.start()
    tracemalloc.reset_peak()
    checksum = float(func())
    _, tm_peak = tracemalloc.get_traced_memory()
    if not already_tracing:
        tracemalloc.stop()
    rss_after = get_rss_bytes()
    peak_rss = get_peak_rss_bytes()

    rss_delta = (
        rss_after - rss_before
        if (rss_before is not None and rss_after is not None)
        else None
    )
    best = min(wall_times)
    mean = sum(wall_times) / len(wall_times)

    providers = provider_availability()
    return TelemetryRecord(
        label=label,
        backend=backend,
        input_dims=dict(input_dims or {}),
        chunk_size=chunk_size,
        repetitions=repetitions,
        wall_best_s=best,
        wall_mean_s=mean,
        cpu_time_s=cpu_time if math.isfinite(cpu_time) else None,
        tracemalloc_peak_bytes=int(tm_peak),
        rss_before_bytes=rss_before,
        rss_after_bytes=rss_after,
        rss_delta_bytes=rss_delta,
        peak_rss_bytes=peak_rss,
        checksum=checksum,
        providers=asdict(providers),
    )
