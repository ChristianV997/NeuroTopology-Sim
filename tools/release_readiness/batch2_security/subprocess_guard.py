"""Allowlisted subprocess execution with isolation bounds."""
from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from threading import Event, Thread
from typing import Any, Dict, List, Optional, Sequence

from tools.release_readiness.batch2_security.schema import (
    REMEDIATION_OWNERS,
    Finding,
    ThreatClass,
)


class SubprocessGuardError(RuntimeError):
    """Raised when a subprocess violates allowlist / isolation policy."""


@dataclass(frozen=True)
class SubprocessPolicy:
    allowlist: frozenset[str]
    timeout_seconds: float = 5.0
    max_stdout_bytes: int = 64 * 1024
    max_stderr_bytes: int = 64 * 1024
    max_workers: int = 2
    shell_forbidden: bool = True


DEFAULT_POLICY = SubprocessPolicy(
    allowlist=frozenset({os.path.normcase(os.path.realpath(sys.executable))}),
    timeout_seconds=5.0,
    max_stdout_bytes=64 * 1024,
    max_stderr_bytes=64 * 1024,
    max_workers=2,
)


def _binary_name(argv: Sequence[str]) -> str:
    if not argv:
        raise SubprocessGuardError("empty argv")
    return os.fsdecode(argv[0])


def _allowlisted_binary(binary: str, allowlist: frozenset[str]) -> bool:
    # Path-qualified commands must match an explicitly trusted path. Basename
    # matching alone would allow an arbitrary executable named "python3".
    if os.path.isabs(binary) or os.path.dirname(binary):
        candidate = os.path.normcase(os.path.realpath(binary))
        return any(
            (os.path.isabs(entry) or os.path.dirname(entry))
            and candidate == os.path.normcase(os.path.realpath(entry))
            for entry in allowlist
        )

    name = os.path.basename(binary)
    if name in allowlist:
        return True
    # Accept CPython versioned interpreters when `python` / `python3` are allowlisted.
    if name.startswith("python3.") and "python3" in allowlist:
        return True
    if name.startswith("python2.") and "python" in allowlist:
        return True
    return False


def validate_invocation(
    argv: Sequence[str],
    *,
    shell: bool,
    timeout: Optional[float],
    policy: SubprocessPolicy = DEFAULT_POLICY,
    active_workers: int = 0,
) -> List[Finding]:
    """Static validation of a proposed subprocess invocation (no execution)."""
    findings: List[Finding] = []
    if shell and policy.shell_forbidden:
        findings.append(
            Finding(
                threat_class=ThreatClass.SHELL_TRUE.value,
                severity="critical",
                message="shell=True is forbidden",
                remediation_owners=list(REMEDIATION_OWNERS[ThreatClass.SHELL_TRUE.value]),
            )
        )
    try:
        binary = _binary_name(argv)
    except SubprocessGuardError as exc:
        findings.append(
            Finding(
                threat_class=ThreatClass.UNSAFE_SUBPROCESS.value,
                severity="critical",
                message=str(exc),
                remediation_owners=list(REMEDIATION_OWNERS[ThreatClass.UNSAFE_SUBPROCESS.value]),
            )
        )
        return findings
    if not _allowlisted_binary(binary, policy.allowlist):
        findings.append(
            Finding(
                threat_class=ThreatClass.UNSAFE_SUBPROCESS.value,
                severity="critical",
                message=f"binary {binary!r} not in allowlist",
                remediation_owners=list(REMEDIATION_OWNERS[ThreatClass.UNSAFE_SUBPROCESS.value]),
            )
        )
    if timeout is None or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        findings.append(
            Finding(
                threat_class=ThreatClass.MISSING_TIMEOUT.value,
                severity="error",
                message="subprocess timeout missing or non-positive",
                remediation_owners=list(REMEDIATION_OWNERS[ThreatClass.MISSING_TIMEOUT.value]),
            )
        )
    if (
        not isinstance(policy.max_stdout_bytes, int)
        or not isinstance(policy.max_stderr_bytes, int)
        or policy.max_stdout_bytes < 0
        or policy.max_stderr_bytes < 0
    ):
        findings.append(
            Finding(
                threat_class=ThreatClass.UNBOUNDED_PROCESS_IO.value,
                severity="error",
                message="stdout/stderr byte limits must be nonnegative integers",
                remediation_owners=list(
                    REMEDIATION_OWNERS[ThreatClass.UNBOUNDED_PROCESS_IO.value]
                ),
            )
        )
    if active_workers >= policy.max_workers:
        findings.append(
            Finding(
                threat_class=ThreatClass.WORKER_LIMIT_EXCEEDED.value,
                severity="error",
                message=f"active_workers={active_workers} exceeds max_workers={policy.max_workers}",
                remediation_owners=list(REMEDIATION_OWNERS[ThreatClass.WORKER_LIMIT_EXCEEDED.value]),
            )
        )
    return findings


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    """Best-effort process-tree termination (POSIX group kill, then child kill)."""
    # The group may still contain descendants after its leader exits, so do not
    # gate killpg on proc.poll(). Popen uses start_new_session on POSIX below.
    if hasattr(os, "killpg") and proc.pid:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    if proc.poll() is None:
        try:
            proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.wait(timeout=1.0)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _capture_bounded_stream(
    stream: Any,
    limit: int,
    state: Dict[str, Any],
    overflow: Event,
) -> None:
    """Drain one pipe while retaining at most ``limit`` bytes."""
    chunks: List[bytes] = []
    total = 0
    try:
        while True:
            read_size = min(8192, max(1, limit - total + 1))
            chunk = stream.read1(read_size)
            if not chunk:
                break
            retained = min(len(chunk), max(0, limit - total))
            if retained:
                chunks.append(chunk[:retained])
            total += len(chunk)
            state["observed"] = total
            if total > limit:
                state["overflow"] = True
                overflow.set()
                break
    except (OSError, ValueError):
        pass
    state["chunks"] = chunks


def run_allowlisted(
    argv: Sequence[str],
    *,
    policy: SubprocessPolicy = DEFAULT_POLICY,
    shell: bool = False,
    timeout: Optional[float] = None,
    active_workers: int = 0,
) -> tuple[int, bytes, bytes, List[Finding]]:
    """Execute an allowlisted command with timeout and streaming IO bounds."""
    effective_timeout = policy.timeout_seconds if timeout is None else timeout
    findings = validate_invocation(
        argv,
        shell=shell,
        timeout=effective_timeout,
        policy=policy,
        active_workers=active_workers,
    )
    if findings:
        raise SubprocessGuardError("; ".join(f.message for f in findings))

    # Start a new session so timeout/overflow cleanup can kill the POSIX tree.
    proc = subprocess.Popen(  # noqa: S603 — argv allowlisted, shell=False
        list(argv),
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert proc.stdout is not None and proc.stderr is not None
    overflow = Event()
    stdout_state: Dict[str, Any] = {"chunks": [], "observed": 0, "overflow": False}
    stderr_state: Dict[str, Any] = {"chunks": [], "observed": 0, "overflow": False}
    readers = [
        Thread(
            target=_capture_bounded_stream,
            args=(proc.stdout, policy.max_stdout_bytes, stdout_state, overflow),
            daemon=True,
        ),
        Thread(
            target=_capture_bounded_stream,
            args=(proc.stderr, policy.max_stderr_bytes, stderr_state, overflow),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + effective_timeout
    timed_out = False
    while True:
        if overflow.is_set():
            _terminate_process_tree(proc)
            break
        process_done = proc.poll() is not None
        readers_done = all(not reader.is_alive() for reader in readers)
        if process_done and readers_done:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            _terminate_process_tree(proc)
            break
        if process_done:
            time.sleep(min(0.01, remaining))
        else:
            try:
                proc.wait(timeout=min(0.05, remaining))
            except subprocess.TimeoutExpired:
                pass

    for reader in readers:
        reader.join(timeout=1.0)
    proc.stdout.close()
    proc.stderr.close()

    if timed_out:
        raise SubprocessGuardError(f"subprocess timed out after {effective_timeout}s")
    if overflow.is_set():
        raise SubprocessGuardError(
            "process IO exceeded bounds "
            f"stdout={stdout_state['observed']}/{policy.max_stdout_bytes} "
            f"stderr={stderr_state['observed']}/{policy.max_stderr_bytes}"
        )

    stdout = b"".join(stdout_state["chunks"])
    stderr = b"".join(stderr_state["chunks"])
    return int(proc.returncode or 0), stdout, stderr, findings
