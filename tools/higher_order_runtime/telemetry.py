"""Telemetry for the bounded higher-order runtime benchmark.

Provides tracemalloc peak measurement, a safe child-process executor with a hard
timeout and optional child RSS sampling (psutil), and JSON-safety helpers.
Self-contained: does not import tools/streaming or any process-runner code.
Unavailable metrics are reported as ``None`` (never zero/fabricated).
"""
from __future__ import annotations

import math
import os
import signal
import subprocess
import threading
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

_IS_WINDOWS = os.name == "nt"
_GRACE_S = 5.0


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

    return json.dumps(json_safe(obj), indent=indent, allow_nan=False)


class MemoryTelemetry:
    """Context manager for the transient ``tracemalloc`` peak of a code block."""

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


def _popen_kwargs() -> Dict[str, Any]:
    if _IS_WINDOWS:  # pragma: no cover - Windows path not exercised on POSIX CI
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _wait_or(proc: subprocess.Popen, seconds: float) -> bool:
    try:
        proc.wait(timeout=seconds)
        return True
    except subprocess.TimeoutExpired:
        return False


def _terminate_tree(proc: subprocess.Popen, grace_s: float = _GRACE_S) -> None:
    if proc.poll() is not None:
        return
    if _IS_WINDOWS:  # pragma: no cover
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception:
            pass
        if not _wait_or(proc, grace_s):
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=False, timeout=10)
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
    exit_code: Optional[int]
    timed_out: bool
    elapsed_s: float
    stdout: str
    stderr: str
    peak_rss_bytes: Optional[int]
    term_signal: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


def execute_child(argv: Sequence[str], *, timeout_s: float, cwd: Optional[str] = None,
                  env: Optional[Dict[str, str]] = None, sample_rss: bool = True,
                  capture_limit: int = 200_000) -> ChildResult:
    """Run ``argv`` (shell=False) in its own process group with a hard timeout.

    Drains output on threads (no deadlock), samples child-tree RSS with psutil when
    available (``None`` otherwise), and terminates the whole tree on timeout. Never
    signals the parent.
    """
    if timeout_s <= 0:
        raise ValueError("timeout_s must be > 0")
    start = time.perf_counter()
    proc = subprocess.Popen(list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=cwd, env=env, **_popen_kwargs())
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

    stop = threading.Event()
    sampled: Dict[str, Optional[int]] = {"peak": None}
    sampler: Optional[threading.Thread] = None
    if sample_rss:
        def _sample():
            try:
                import psutil
            except Exception:
                sampled["peak"] = None
                return
            try:
                p = psutil.Process(proc.pid)
            except Exception:
                sampled["peak"] = None
                return
            peak = 0
            while not stop.is_set():
                try:
                    total = p.memory_info().rss
                    for ch in p.children(recursive=True):
                        try:
                            total += ch.memory_info().rss
                        except Exception:
                            pass
                    peak = max(peak, total)
                except Exception:
                    break
                stop.wait(0.02)
            sampled["peak"] = peak if peak > 0 else sampled.get("peak")
        sampler = threading.Thread(target=_sample, daemon=True)
        sampler.start()

    timed_out = not _wait_or(proc, timeout_s)
    if timed_out:
        _terminate_tree(proc)
        if not _wait_or(proc, 10.0):
            _terminate_tree(proc)
            _wait_or(proc, 5.0)
    stop.set()
    if sampler is not None:
        sampler.join(timeout=2.0)
    t_out.join(timeout=5.0)
    t_err.join(timeout=5.0)

    rc = proc.returncode if proc.returncode is not None else -1
    term_signal = -rc if rc < 0 else None
    exit_code = rc if rc >= 0 else None
    return ChildResult(
        exit_code=exit_code, timed_out=timed_out, elapsed_s=time.perf_counter() - start,
        stdout="".join(out)[-capture_limit:], stderr="".join(err)[-capture_limit:],
        peak_rss_bytes=sampled.get("peak"), term_signal=term_signal,
    )
