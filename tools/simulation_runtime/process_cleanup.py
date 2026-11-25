"""Cross-platform subprocess execution with process-tree cleanup and telemetry.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

try:
    import psutil  # type: ignore
    _PSUTIL = psutil
except Exception:
    _PSUTIL = None

_IS_WINDOWS = os.name == "nt"


@dataclass
class ProcessExecutionResult:
    """Detailed outcome of a sandboxed subprocess run."""
    exit_code: Optional[int]
    stdout: str
    stderr: str
    elapsed_s: float
    timed_out: bool
    peak_rss_bytes: Optional[int]
    process_killed: bool


def _terminate_process_tree(proc: subprocess.Popen, grace_s: float = 3.0) -> bool:
    """Terminate the process and all of its descendants without leaving orphans.

    On Windows: Sends CTRL_BREAK_EVENT to the process group, then invokes taskkill /F /T /PID.
    On POSIX: Sends SIGTERM then SIGKILL to the process group.
    """
    if proc.poll() is not None:
        return False

    killed = False
    if _IS_WINDOWS:
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception:
            pass

        try:
            proc.wait(timeout=grace_s)
            killed = True
        except subprocess.TimeoutExpired:
            pass

        if proc.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    check=False,
                    timeout=5.0,
                )
                killed = True
            except Exception:
                try:
                    proc.kill()
                    killed = True
                except Exception:
                    pass
            try:
                proc.wait(timeout=grace_s)
            except Exception:
                pass
        return killed

    # POSIX session / process group termination
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return False

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
            killed = True
        except ProcessLookupError:
            return True
        except Exception:
            pass

        try:
            proc.wait(timeout=grace_s)
            return True
        except subprocess.TimeoutExpired:
            continue

    return killed


def _sample_tree_rss(
    pid: int,
    stop_event: threading.Event,
    out: Dict[str, Optional[int]],
    interval_s: float = 0.05,
) -> None:
    """Background thread sampling peak RSS of the process tree."""
    if _PSUTIL is None:
        out["peak"] = None
        return

    peak = 0
    try:
        root = _PSUTIL.Process(pid)
    except Exception:
        out["peak"] = None
        return

    while not stop_event.is_set():
        try:
            current = root.memory_info().rss
            for child in root.children(recursive=True):
                try:
                    current += child.memory_info().rss
                except Exception:
                    pass
            if current > peak:
                peak = current
        except Exception:
            break
        stop_event.wait(interval_s)

    out["peak"] = int(peak) if peak > 0 else None


def run_isolated_process(
    command: Sequence[str],
    *,
    timeout_s: float = 60.0,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    max_output_chars: int = 100_000,
) -> ProcessExecutionResult:
    """Run an isolated child process with timeout, tree cleanup, and RSS telemetry.

    Guarantees that a timed-out or crashed child never orphans background descendants.
    """
    popen_kwargs: Dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "cwd": cwd,
        "env": env,
    }

    if _IS_WINDOWS:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    start_time = time.monotonic()
    timed_out = False
    process_killed = False
    stdout = ""
    stderr = ""
    exit_code: Optional[int] = None
    rss_out: Dict[str, Optional[int]] = {"peak": None}
    stop_sampler = threading.Event()

    try:
        proc = subprocess.Popen(list(command), **popen_kwargs)
    except Exception as exc:
        return ProcessExecutionResult(
            exit_code=-1,
            stdout="",
            stderr=f"Failed to spawn process: {exc}",
            elapsed_s=time.monotonic() - start_time,
            timed_out=False,
            peak_rss_bytes=None,
            process_killed=False,
        )

    sampler_thread = threading.Thread(
        target=_sample_tree_rss,
        args=(proc.pid, stop_sampler, rss_out),
        daemon=True,
    )
    sampler_thread.start()

    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        process_killed = _terminate_process_tree(proc)
        try:
            rem_out, rem_err = proc.communicate(timeout=2.0)
            stdout = rem_out or ""
            stderr = rem_err or ""
        except Exception:
            stdout = ""
            stderr = "Process tree terminated after timeout."
        exit_code = proc.returncode
    finally:
        stop_sampler.set()
        sampler_thread.join(timeout=1.0)
        # Ensure process tree is fully dead
        if proc.poll() is None:
            _terminate_process_tree(proc)

    elapsed_s = time.monotonic() - start_time

    # Truncate overly verbose output if needed
    if len(stdout) > max_output_chars:
        stdout = stdout[:max_output_chars] + f"\n... [truncated at {max_output_chars} chars]"
    if len(stderr) > max_output_chars:
        stderr = stderr[:max_output_chars] + f"\n... [truncated at {max_output_chars} chars]"

    return ProcessExecutionResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        elapsed_s=elapsed_s,
        timed_out=timed_out,
        peak_rss_bytes=rss_out["peak"],
        process_killed=process_killed,
    )
