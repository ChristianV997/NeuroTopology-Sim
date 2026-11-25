"""Safe, process-isolated subprocess runner for benchmark configurations.

Each benchmark configuration runs in its own child process so that peak-RSS and
timeouts are attributable per configuration and a hung or crashing child cannot
take down the parent or leak into sibling measurements. This module is generic:
it launches an arbitrary child *command* (argv), enforces a hard timeout, cleans
up the whole process group, captures stdout/stderr/exit/elapsed, parses the
child's telemetry JSON (tolerantly), optionally samples the child tree's RSS from
the parent, classifies the outcome, and writes atomic JSON reports.

It imports no streaming/kernel/benchmark code and runs no scientific workload.

Key guarantees:

* **Hard timeout + clean termination.** On timeout the child's process group is
  terminated (SIGTERM then SIGKILL on POSIX; CTRL_BREAK/terminate/taskkill tree
  on Windows), so grandchildren do not orphan.
* **Bounded parallelism.** A configuration matrix runs with a capped number of
  concurrent children; a sequential mode (``max_workers=1``) gives deterministic
  diagnosis order.
* **Honest telemetry.** Unavailable metrics are ``None`` (never ``0``); a timeout
  or crash is classified as such and never reported as a valid result.
* **Finite, atomic JSON.** :func:`json_safe` removes NaN/Inf; reports are written
  via a temp file + ``os.replace``.

Outcomes are one of :class:`Outcome`: ``pass``, ``correctness_failure``,
``timeout``, ``child_crash``, ``missing_metric``, ``infrastructure_failure``.
"""
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

try:  # pragma: no cover - availability is environment dependent
    import psutil  # type: ignore

    _PSUTIL = psutil
except Exception:  # pragma: no cover
    _PSUTIL = None

_IS_WINDOWS = os.name == "nt"

__all__ = [
    "Outcome",
    "ChildResult",
    "json_safe",
    "run_one",
    "run_matrix",
    "write_atomic_json",
    "build_python_command",
]


class Outcome(str, Enum):
    PASS = "pass"
    CORRECTNESS_FAILURE = "correctness_failure"
    TIMEOUT = "timeout"
    CHILD_CRASH = "child_crash"
    MISSING_METRIC = "missing_metric"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"


def json_safe(value: Any) -> Any:
    """Recursively convert to a JSON-safe structure (NaN/Inf -> None)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def write_atomic_json(path: str | Path, obj: Any, *, indent: Optional[int] = 2) -> str:
    """Write ``obj`` as JSON atomically (temp file in same dir + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(json_safe(obj), indent=indent, allow_nan=False)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return str(path)


def build_python_command(script: str, args: Optional[Sequence[str]] = None) -> List[str]:
    """Build a cross-platform ``argv`` to run a Python ``script`` with the same
    interpreter. Using an argv list (``shell=False``) avoids POSIX-vs-PowerShell
    quoting differences; callers who must go through PowerShell can wrap the
    result with ``["powershell", "-NoProfile", "-Command", ...]`` themselves.
    """
    return [sys.executable, str(script), *([str(a) for a in args] if args else [])]


@dataclass
class ChildResult:
    config: Dict[str, Any]
    outcome: Outcome
    exit_code: Optional[int]
    term_signal: Optional[int]
    timed_out: bool
    elapsed_s: float
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    checksum: Optional[float]
    tracemalloc_peak_bytes: Optional[int]
    peak_rss_bytes: Optional[int]
    parent_sampled_peak_rss_bytes: Optional[int]
    correctness_ok: Optional[bool]
    missing_metrics: List[str]
    parse_error: Optional[str]
    telemetry: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


# --------------------------------------------------------------------------- #
# Telemetry parsing
# --------------------------------------------------------------------------- #
def _parse_last_json(text: str) -> Any:
    """Return the parsed JSON from ``text`` (whole blob, else last JSON line)."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("no output to parse")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    for line in reversed(stripped.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise ValueError("no JSON object found in output")


def _num_or_none(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _int_or_none(value: Any) -> Optional[int]:
    n = _num_or_none(value)
    return int(n) if n is not None else None


# --------------------------------------------------------------------------- #
# Process-tree RSS sampling (best-effort)
# --------------------------------------------------------------------------- #
def _sample_tree_rss(pid: int, stop: threading.Event, out: Dict[str, Optional[int]],
                     interval_s: float) -> None:
    if _PSUTIL is None:  # pragma: no cover - depends on environment
        out["peak"] = None
        return
    peak = 0
    try:
        proc = _PSUTIL.Process(pid)
    except Exception:
        out["peak"] = None
        return
    while not stop.is_set():
        try:
            total = proc.memory_info().rss
            for child in proc.children(recursive=True):
                try:
                    total += child.memory_info().rss
                except Exception:
                    continue
            peak = max(peak, total)
        except Exception:
            break
        stop.wait(interval_s)
    out["peak"] = int(peak) if peak > 0 else out.get("peak")


# --------------------------------------------------------------------------- #
# Termination
# --------------------------------------------------------------------------- #
def _popen_kwargs() -> Dict[str, Any]:
    if _IS_WINDOWS:  # pragma: no cover - Windows path not exercised on CI here
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}  # new process group/session for group kill


def _terminate_tree(proc: subprocess.Popen, grace_s: float = 5.0) -> None:
    """Terminate the child and its whole group/tree without leaving orphans."""
    if proc.poll() is not None:
        return
    if _IS_WINDOWS:  # pragma: no cover - not exercised here
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception:
            pass
        _wait_or(proc, grace_s)
        if proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, check=False)
            _wait_or(proc, grace_s)
        return
    # POSIX: signal the whole session/process group.
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    for sig, wait in ((signal.SIGTERM, grace_s), (signal.SIGKILL, grace_s)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        if _wait_or(proc, wait):
            return


def _wait_or(proc: subprocess.Popen, seconds: float) -> bool:
    try:
        proc.wait(timeout=seconds)
        return True
    except subprocess.TimeoutExpired:
        return False


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if text is None:
        return "", False
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]", True


# --------------------------------------------------------------------------- #
# Single child
# --------------------------------------------------------------------------- #
def run_one(
    argv: Sequence[str],
    config: Dict[str, Any],
    *,
    timeout_s: float,
    required_metrics: Sequence[str] = ("checksum",),
    poll_interval_s: float = 0.02,
    capture_limit: int = 10_000,
    sample_rss: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> ChildResult:
    """Run one child ``argv`` for ``config`` with a hard ``timeout_s``."""
    if timeout_s <= 0:
        raise ValueError("timeout_s must be > 0")

    start = time.perf_counter()
    stop = threading.Event()
    sampled: Dict[str, Optional[int]] = {"peak": None}
    sampler: Optional[threading.Thread] = None
    timed_out = False
    launch_error: Optional[str] = None

    try:
        proc = subprocess.Popen(
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            **_popen_kwargs(),
        )
    except (OSError, ValueError) as exc:
        elapsed = time.perf_counter() - start
        return ChildResult(
            config=config, outcome=Outcome.INFRASTRUCTURE_FAILURE, exit_code=None,
            term_signal=None, timed_out=False, elapsed_s=elapsed, stdout="",
            stderr=f"launch failed: {exc}", stdout_truncated=False, stderr_truncated=False,
            checksum=None, tracemalloc_peak_bytes=None, peak_rss_bytes=None,
            parent_sampled_peak_rss_bytes=None, correctness_ok=None, missing_metrics=[],
            parse_error=None, telemetry=None,
        )

    if sample_rss:
        sampler = threading.Thread(target=_sample_tree_rss,
                                   args=(proc.pid, stop, sampled, poll_interval_s), daemon=True)
        sampler.start()

    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=5.0)
        except subprocess.TimeoutExpired:  # pragma: no cover - extreme case
            stdout, stderr = "", "timed out and could not drain output"
    finally:
        stop.set()
        if sampler is not None:
            sampler.join(timeout=2.0)

    elapsed = time.perf_counter() - start
    returncode = proc.returncode
    term_signal = -returncode if (returncode is not None and returncode < 0) else None
    exit_code = returncode if (returncode is not None and returncode >= 0) else None

    stdout_t, stdout_trunc = _truncate(stdout or "", capture_limit)
    stderr_t, stderr_trunc = _truncate(stderr or "", capture_limit)

    telemetry: Optional[Dict[str, Any]] = None
    parse_error: Optional[str] = None
    checksum = tracemalloc_peak = peak_rss = None
    correctness_ok: Optional[bool] = None
    if not timed_out and (stdout or "").strip():
        try:
            parsed = _parse_last_json(stdout)
            if isinstance(parsed, dict):
                telemetry = parsed
                checksum = _num_or_none(parsed.get("checksum"))
                tracemalloc_peak = _int_or_none(parsed.get("tracemalloc_peak_bytes"))
                peak_rss = _int_or_none(parsed.get("peak_rss_bytes"))
                if isinstance(parsed.get("correctness_ok"), bool):
                    correctness_ok = parsed["correctness_ok"]
            else:
                parse_error = "telemetry JSON was not an object"
        except (ValueError, json.JSONDecodeError) as exc:
            parse_error = str(exc)

    metric_values = {
        "checksum": checksum,
        "tracemalloc_peak_bytes": tracemalloc_peak,
        "peak_rss_bytes": peak_rss,
    }
    missing_metrics = [m for m in required_metrics if metric_values.get(m) is None]

    # ---- Classification (mutually exclusive) --------------------------------
    if timed_out:
        outcome = Outcome.TIMEOUT
    elif term_signal is not None or (exit_code is not None and exit_code != 0):
        outcome = Outcome.CHILD_CRASH
    elif telemetry is None:
        outcome = Outcome.INFRASTRUCTURE_FAILURE          # ran but no parseable result
    elif correctness_ok is False:
        outcome = Outcome.CORRECTNESS_FAILURE
    elif missing_metrics:
        outcome = Outcome.MISSING_METRIC
    else:
        outcome = Outcome.PASS

    return ChildResult(
        config=config,
        outcome=outcome,
        exit_code=exit_code,
        term_signal=term_signal,
        timed_out=timed_out,
        elapsed_s=elapsed,
        stdout=stdout_t,
        stderr=stderr_t,
        stdout_truncated=stdout_trunc,
        stderr_truncated=stderr_trunc,
        checksum=checksum,
        tracemalloc_peak_bytes=tracemalloc_peak,
        peak_rss_bytes=peak_rss,
        parent_sampled_peak_rss_bytes=sampled.get("peak"),
        correctness_ok=correctness_ok,
        missing_metrics=missing_metrics,
        parse_error=parse_error,
        telemetry=telemetry,
    )


# --------------------------------------------------------------------------- #
# Matrix
# --------------------------------------------------------------------------- #
def run_matrix(
    command_builder: Callable[[Dict[str, Any]], Sequence[str]],
    configs: Sequence[Dict[str, Any]],
    *,
    timeout_s: float,
    max_workers: int = 1,
    sequential: bool = False,
    required_metrics: Sequence[str] = ("checksum",),
    output_path: Optional[str | Path] = None,
    sample_rss: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Run every configuration in its own child process with bounded parallelism.

    ``command_builder(config) -> argv`` builds each child command. Results are
    returned in the same order as ``configs``. ``sequential=True`` forces
    ``max_workers=1`` for deterministic diagnosis. If ``output_path`` is given,
    the aggregate report is written atomically.
    """
    if timeout_s <= 0:
        raise ValueError("timeout_s must be > 0")
    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")
    effective_workers = 1 if sequential else min(max_workers, max(len(configs), 1))

    def _task(index_config):
        index, config = index_config
        argv = command_builder(config)
        result = run_one(argv, config, timeout_s=timeout_s,
                         required_metrics=required_metrics, sample_rss=sample_rss, env=env)
        return index, result

    results: List[Optional[ChildResult]] = [None] * len(configs)
    if effective_workers == 1:
        for item in enumerate(configs):
            index, result = _task(item)
            results[index] = result
    else:
        with ThreadPoolExecutor(max_workers=effective_workers) as pool:
            for index, result in pool.map(_task, list(enumerate(configs))):
                results[index] = result

    child_dicts = [r.to_dict() for r in results if r is not None]
    summary: Dict[str, int] = {}
    for r in results:
        if r is not None:
            summary[r.outcome.value] = summary.get(r.outcome.value, 0) + 1

    report = {
        "schema": "process_isolated_benchmark/v1",
        "evidence_class": "performance_only",
        "runner": {
            "timeout_s": timeout_s,
            "max_workers": effective_workers,
            "sequential": bool(sequential or effective_workers == 1),
            "required_metrics": list(required_metrics),
            "platform": sys.platform,
            "psutil_available": _PSUTIL is not None,
        },
        "num_configs": len(configs),
        "summary": summary,
        "all_passed": all(r is not None and r.outcome == Outcome.PASS for r in results),
        "results": child_dicts,
        "notes": [
            "A timeout or crash is an infrastructure/operational outcome, not a "
            "scientific result.",
            "peak_rss_bytes includes interpreter and imported-library memory and "
            "is not the chunk working set; compare like-for-like on the same host.",
        ],
    }
    if output_path is not None:
        write_atomic_json(output_path, report)
    return report
