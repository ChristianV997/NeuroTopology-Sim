"""Subprocess command construction, execution guards, and child-process tree termination.

Features:
- Platform-aware command construction (executable resolution, python prefixing).
- Process tree termination preventing leaked children on Windows and POSIX.
- Guarded execution with timeout enforcement and structured ProcessResult outputs.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from .paths import IS_WINDOWS
from .types import ProcessResult


def build_subprocess_cmd(cmd: Sequence[str] | str) -> list[str]:
    """Construct a robust, platform-neutral command list for subprocess.Popen."""
    if isinstance(cmd, str):
        import shlex
        parts = shlex.split(cmd, posix=not IS_WINDOWS)
    else:
        parts = [str(arg) for arg in cmd]

    if not parts:
        raise ValueError("Cannot construct subprocess command from empty argument list.")

    first = parts[0]
    # If invoking a python script directly (e.g. 'foo.py'), prefix with current sys.executable
    if first.endswith(".py") and not any(parts[0].lower().startswith(p) for p in ("python", "py")):
        parts = [sys.executable] + parts

    return parts


def terminate_process_tree(proc: subprocess.Popen, timeout: float = 3.0) -> list[int]:
    """Terminate a process and all its child processes to prevent orphaned tasks."""
    terminated_pids: list[int] = []
    pid = proc.pid

    if proc.poll() is not None:
        return terminated_pids

    terminated_pids.append(pid)

    if IS_WINDOWS:
        # On Windows, taskkill /F /T /PID kills the entire child process tree
        try:
            kill_cmd = ["taskkill", "/F", "/T", "/PID", str(pid)]
            subprocess.run(kill_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        except Exception:
            try:
                proc.kill()
            except OSError:
                pass
    else:
        # On POSIX, terminate process group if possible
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(0.1)
            if proc.poll() is None:
                os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            try:
                proc.kill()
            except OSError:
                pass

    try:
        proc.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        pass

    return terminated_pids


def run_guarded_subprocess(
    cmd: Sequence[str] | str,
    timeout: float = 30.0,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    """Run a subprocess with guarded timeout enforcement and child-process cleanup."""
    cmd_list = build_subprocess_cmd(cmd)
    cwd_str = str(cwd) if cwd else None

    # Merge custom env with os.environ
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    start_time = time.perf_counter()
    timed_out = False
    stdout_text = ""
    stderr_text = ""
    returncode: int | None = None
    terminated: list[int] = []

    # Process group creation on POSIX for clean process group kill
    kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": cwd_str,
        "env": proc_env,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }

    if not IS_WINDOWS:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd_list, **kwargs)

    try:
        stdout_text, stderr_text = proc.communicate(timeout=timeout)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        terminated = terminate_process_tree(proc, timeout=2.0)
        # Capture whatever output was produced before timing out
        try:
            out, err = proc.communicate(timeout=1.0)
            stdout_text = out or ""
            stderr_text = err or ""
        except Exception:
            pass
        returncode = None
    finally:
        duration = max(0.0, time.perf_counter() - start_time)

    return ProcessResult(
        command=cmd_list,
        returncode=returncode,
        stdout=stdout_text,
        stderr=stderr_text,
        duration_seconds=duration,
        timed_out=timed_out,
        terminated_children=terminated,
    )
