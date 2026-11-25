"""Telemetry primitives: finite JSON, tracemalloc, optional RSS, disk, child exec.

Self-contained stdlib plus optional ``psutil``. Missing metrics stay ``None``
(never fabricated ``0``). No remote I/O.
"""
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

try:  # pragma: no cover - environment dependent
    import psutil  # type: ignore

    _PSUTIL = psutil
except Exception:  # pragma: no cover
    _PSUTIL = None

_IS_WINDOWS = os.name == "nt"


def json_safe(value: Any) -> Any:
    """Recursively convert to JSON-safe form (NaN/Inf -> None; Enum -> value)."""
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


class MemoryTelemetry:
    """Context manager reporting the transient tracemalloc peak of its block."""

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
    """Current process RSS in bytes, or None if no provider is available."""
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
    """Total size in bytes of all files under ``path`` (0 for empty/missing)."""
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
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n


def measure(func: Callable[[], Dict[str, Any]], *, repetitions: int = 3) -> Dict[str, Any]:
    """Run ``func`` collecting runtime/memory/disk telemetry.

    Timing and the tracemalloc window are separate passes so tracing overhead
    does not distort wall time. Missing RSS/disk stay ``None``.
    """
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
    worker = _optional_int(result, "worker_count")
    if worker is None:
        worker = 1
    input_size = result.get("input_size")
    if input_size is not None and not isinstance(input_size, dict):
        try:
            input_size = {"n_items": int(input_size), "bytes": None}
        except (TypeError, ValueError):
            input_size = {"n_items": None, "bytes": None}

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
        "input_size": input_size,
        "worker_count": worker,
        "production_module": result.get("production_module"),
        "production_available": result.get("production_available"),
    }


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
    if _IS_WINDOWS:  # pragma: no cover
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception:
            pass
        if not _wait_or(proc, grace_s):
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=10,
                )
            except Exception:
                pass
            _wait_or(proc, grace_s)
        return
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        return
    for sig, wait in ((signal.SIGTERM, grace_s), (signal.SIGKILL, grace_s)):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, OSError):
            return
        if _wait_or(proc, wait):
            return


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


def execute_child(
    argv: Sequence[str],
    *,
    timeout_s: float,
    env: Optional[Dict[str, str]] = None,
    capture_limit: int = 200_000,
) -> ChildResult:
    """Run ``argv`` (shell=False) in its own group with a hard timeout."""
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
        if not _wait_or(proc, 10.0):
            _terminate_tree(proc)
            _wait_or(proc, 5.0)
    t_out.join(timeout=5.0)
    t_err.join(timeout=5.0)

    rc = proc.returncode if proc.returncode is not None else -1
    term_signal = -rc if rc < 0 else None
    exit_code = rc if rc >= 0 else -1
    return ChildResult(
        exit_code=exit_code,
        timed_out=timed_out,
        term_signal=term_signal,
        stdout="".join(out)[-capture_limit:],
        stderr="".join(err)[-capture_limit:],
        elapsed_s=time.perf_counter() - start,
    )
