"""Isolated subprocess execution for a single matrix case."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from tools.benchmark_orchestration.schema import CaseResult, CaseSpec, CaseStatus


def check_optional_deps(deps: Sequence[str]) -> Optional[str]:
    """Return the first missing importable module name, or ``None`` if all present."""
    for name in deps:
        if importlib.util.find_spec(name) is None:
            return name
    return None


def _terminate_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":  # pragma: no cover - Windows CI rare here
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _checksum_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _write_log(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def classify_exit(exit_code: Optional[int], timed_out: bool) -> CaseStatus:
    """Map process outcome to a :class:`CaseStatus` (never maps timeout → PASS)."""
    if timed_out:
        return CaseStatus.TIMEOUT
    if exit_code is None:
        return CaseStatus.CHILD_CRASH
    if exit_code == 0:
        return CaseStatus.PASS
    # Conventional shell signals: 128+N; pytest often uses 1 for failures.
    if exit_code < 0 or exit_code >= 128:
        return CaseStatus.CHILD_CRASH
    return CaseStatus.CORRECTNESS_FAILURE


def run_case_once(
    spec: CaseSpec,
    *,
    timeout_s: int,
    work_dir: Path,
    attempt: int,
    env: Optional[dict] = None,
) -> CaseResult:
    """Run ``spec.command`` once in an isolated subprocess."""
    work_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = work_dir / f"{spec.case_id}.attempt{attempt}.stdout.txt"
    stderr_path = work_dir / f"{spec.case_id}.attempt{attempt}.stderr.txt"

    missing = check_optional_deps(spec.optional_deps)
    if missing is not None:
        return CaseResult(
            case_id=spec.case_id,
            command=list(spec.command),
            input_configuration=dict(spec.config),
            status=CaseStatus.OPTIONAL_DEPENDENCY_MISSING,
            duration_s=0.0,
            exit_code=None,
            timed_out=False,
            stdout_ref=None,
            stderr_ref=None,
            checksum=None,
            memory_telemetry_ref=spec.memory_telemetry_ref,
            attempts=attempt,
            retries_used=max(0, attempt - 1),
            error_message=f"optional dependency missing: {missing}",
        )

    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    # Bound BLAS/OpenMP pools in every worker (same discipline as isolated runner).
    for var in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        run_env[var] = "1"

    cwd = spec.cwd
    start = time.monotonic()
    timed_out = False
    exit_code: Optional[int] = None
    stdout_text = ""
    stderr_text = ""
    error_message: Optional[str] = None

    try:
        popen_kwargs = {
            "args": list(spec.command),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "env": run_env,
            "cwd": cwd,
        }
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        else:
            # Abort/crash probes must remain headless on Windows.  Without
            # this flag the CRT may surface a modal error dialog, leaving the
            # pipe reader waiting until the per-case timeout instead of
            # reporting CHILD_CRASH and honoring the retry budget.
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(**popen_kwargs)
        try:
            stdout_text, stderr_text = proc.communicate(timeout=timeout_s)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_tree(proc)
            try:
                out2, err2 = proc.communicate(timeout=5)
                stdout_text = (stdout_text or "") + (out2 or "")
                stderr_text = (stderr_text or "") + (err2 or "")
            except Exception:
                pass
            exit_code = 124
            error_message = f"per-case timeout exceeded ({timeout_s}s)"
    except FileNotFoundError as exc:
        exit_code = 127
        error_message = f"executable not found: {exc}"
        status = CaseStatus.INFRASTRUCTURE_BLOCKED
        duration = time.monotonic() - start
        stdout_ref = _write_log(stdout_path, stdout_text)
        stderr_ref = _write_log(stderr_path, stderr_text + f"\n{error_message}\n")
        return CaseResult(
            case_id=spec.case_id,
            command=list(spec.command),
            input_configuration=dict(spec.config),
            status=status,
            duration_s=round(duration, 6),
            exit_code=exit_code,
            timed_out=False,
            stdout_ref=stdout_ref,
            stderr_ref=stderr_ref,
            checksum=_checksum_text(stdout_text + "\n" + stderr_text),
            memory_telemetry_ref=spec.memory_telemetry_ref,
            attempts=attempt,
            retries_used=max(0, attempt - 1),
            error_message=error_message,
        )
    except OSError as exc:
        exit_code = None
        error_message = f"OS error launching child: {exc}"
        status = CaseStatus.INFRASTRUCTURE_BLOCKED
        duration = time.monotonic() - start
        stdout_ref = _write_log(stdout_path, stdout_text)
        stderr_ref = _write_log(stderr_path, stderr_text + f"\n{error_message}\n")
        return CaseResult(
            case_id=spec.case_id,
            command=list(spec.command),
            input_configuration=dict(spec.config),
            status=status,
            duration_s=round(duration, 6),
            exit_code=exit_code,
            timed_out=False,
            stdout_ref=stdout_ref,
            stderr_ref=stderr_ref,
            checksum=_checksum_text(stdout_text + "\n" + stderr_text),
            memory_telemetry_ref=spec.memory_telemetry_ref,
            attempts=attempt,
            retries_used=max(0, attempt - 1),
            error_message=error_message,
        )

    duration = time.monotonic() - start
    status = classify_exit(exit_code, timed_out)
    stdout_ref = _write_log(stdout_path, stdout_text or "")
    stderr_ref = _write_log(stderr_path, stderr_text or "")
    checksum = _checksum_text((stdout_text or "") + "\n---\n" + (stderr_text or ""))

    return CaseResult(
        case_id=spec.case_id,
        command=list(spec.command),
        input_configuration=dict(spec.config),
        status=status,
        duration_s=round(duration, 6),
        exit_code=exit_code,
        timed_out=timed_out,
        stdout_ref=stdout_ref,
        stderr_ref=stderr_ref,
        checksum=checksum,
        memory_telemetry_ref=spec.memory_telemetry_ref,
        attempts=attempt,
        retries_used=max(0, attempt - 1),
        error_message=error_message,
    )


def run_case_with_retries(
    spec: CaseSpec,
    *,
    timeout_s: int,
    max_retries: int,
    work_dir: Path,
) -> CaseResult:
    """Execute a case with a bounded retry budget.

    Retries apply only to ``CHILD_CRASH`` and ``INFRASTRUCTURE_BLOCKED``.
    ``TIMEOUT`` and ``CORRECTNESS_FAILURE`` are never retried (timeouts must
    remain visible; correctness must not be masked by repetition).
    """
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    attempt = 0
    last: Optional[CaseResult] = None
    while attempt <= max_retries:
        attempt += 1
        last = run_case_once(spec, timeout_s=timeout_s, work_dir=work_dir, attempt=attempt)
        if last.status in {
            CaseStatus.PASS,
            CaseStatus.CORRECTNESS_FAILURE,
            CaseStatus.TIMEOUT,
            CaseStatus.OPTIONAL_DEPENDENCY_MISSING,
        }:
            return last
        # CHILD_CRASH / INFRASTRUCTURE_BLOCKED may retry until budget exhausted.
        if attempt > max_retries:
            return last
    assert last is not None
    return last
