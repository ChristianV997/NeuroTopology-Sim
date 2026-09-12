"""Finite JSON, tracemalloc, optional RSS, disk. Missing metrics stay None."""
from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
import threading
import time
import tracemalloc
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

try:  # pragma: no cover
    import psutil  # type: ignore

    _PSUTIL = psutil
except Exception:  # pragma: no cover
    _PSUTIL = None

_IS_WINDOWS = os.name == "nt"


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

    return json.dumps(json_safe(obj), indent=indent, allow_nan=False, sort_keys=True)


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


def dir_size_bytes(path: str | Path) -> Optional[int]:
    root = Path(path)
    if not root.exists():
        return None
    if root.is_file():
        try:
            return int(root.stat().st_size)
        except OSError:
            return None
    total = 0
    found = False
    for p in root.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
                found = True
        except OSError:
            continue
    return total if found or root.is_dir() else None


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
            "planning_latency_s": None,
            "tracemalloc_peak_bytes": None,
            "rss_after_bytes": None,
            "disk_bytes": None,
            "cache_occupancy_bytes": None,
            "evicted_bytes": None,
            "retry_attempts": None,
            "feature_count": None,
            "repetitions": repetitions,
        }

    times: List[float] = []
    for _ in range(repetitions):
        t0 = time.perf_counter()
        func()
        times.append(time.perf_counter() - t0)

    with MemoryTelemetry() as mem:
        traced = func()
    rss = current_rss_bytes()

    def _opt_int(src: Dict[str, Any], key: str) -> Optional[int]:
        value = src.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _opt_float(src: Dict[str, Any], key: str) -> Optional[float]:
        value = src.get(key)
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    return {
        "ok": True,
        "reason": None,
        "checksum": result.get("checksum"),
        "correctness": result.get("correctness"),
        "status": result.get("status"),
        "error_code": result.get("error_code"),
        "runtime_best_s": min(times) if times else None,
        "runtime_mean_s": (sum(times) / len(times)) if times else None,
        "planning_latency_s": _opt_float(result, "planning_latency_s"),
        "tracemalloc_peak_bytes": mem.peak_bytes,
        "rss_after_bytes": rss,
        "disk_bytes": _opt_int(traced, "disk_bytes") if _opt_int(traced, "disk_bytes") is not None else _opt_int(result, "disk_bytes"),
        "cache_occupancy_bytes": _opt_int(result, "cache_occupancy_bytes"),
        "evicted_bytes": _opt_int(result, "evicted_bytes"),
        "retry_attempts": _opt_int(result, "retry_attempts"),
        "feature_count": result.get("feature_count"),
        "repetitions": repetitions,
        "notes": result.get("notes"),
        "production_module": result.get("production_module"),
        "rejected_full_object": result.get("rejected_full_object"),
    }


@dataclass
class ChildResult:
    exit_code: int
    timed_out: bool
    term_signal: Optional[int]
    stdout: str
    stderr: str
    elapsed_s: float

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


def _popen_kwargs() -> Dict[str, Any]:
    if _IS_WINDOWS:  # pragma: no cover
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _wait_or(proc: subprocess.Popen, seconds: float) -> bool:
    try:
        proc.wait(timeout=seconds)
        return True
    except subprocess.TimeoutExpired:
        return False


def _terminate_tree(proc: subprocess.Popen, grace_s: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError, AttributeError):
        try:
            proc.kill()
        except Exception:
            return
        _wait_or(proc, grace_s)
        return
    for sig, wait in ((signal.SIGTERM, grace_s), (signal.SIGKILL, grace_s)):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, OSError):
            return
        if _wait_or(proc, wait):
            return


def execute_child(
    argv: Sequence[str],
    *,
    timeout_s: float,
    env: Optional[Dict[str, str]] = None,
    capture_limit: int = 200_000,
) -> ChildResult:
    if timeout_s <= 0:
        raise ValueError("timeout_s must be > 0")
    start = time.perf_counter()
    proc = subprocess.Popen(
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        **_popen_kwargs(),
    )
    out: List[str] = []
    err: List[str] = []

    def _drain(stream, sink):
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                sink.append(line)
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_drain, args=(proc.stdout, out), daemon=True)
    t_err = threading.Thread(target=_drain, args=(proc.stderr, err), daemon=True)
    t_out.start()
    t_err.start()
    timed_out = not _wait_or(proc, timeout_s)
    if timed_out:
        _terminate_tree(proc)
        _wait_or(proc, 10.0)
    t_out.join(timeout=5.0)
    t_err.join(timeout=5.0)
    rc = proc.returncode if proc.returncode is not None else -1
    return ChildResult(
        exit_code=rc if rc >= 0 else -1,
        timed_out=timed_out,
        term_signal=-rc if rc < 0 else None,
        stdout="".join(out)[-capture_limit:],
        stderr="".join(err)[-capture_limit:],
        elapsed_s=time.perf_counter() - start,
    )
