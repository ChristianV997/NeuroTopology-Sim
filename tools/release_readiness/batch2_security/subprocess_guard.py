"""Allowlisted subprocess execution with isolation bounds."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

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
    allowlist=frozenset({"python", "python3", "true", "false"}),
    timeout_seconds=5.0,
    max_stdout_bytes=64 * 1024,
    max_stderr_bytes=64 * 1024,
    max_workers=2,
)


def _binary_name(argv: Sequence[str]) -> str:
    if not argv:
        raise SubprocessGuardError("empty argv")
    return os.path.basename(str(argv[0]))


def _allowlisted_binary(binary: str, allowlist: frozenset[str]) -> bool:
    if binary in allowlist:
        return True
    # Accept CPython versioned interpreters when `python` / `python3` are allowlisted.
    if binary.startswith("python3.") and "python3" in allowlist:
        return True
    if binary.startswith("python2.") and "python" in allowlist:
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
    if timeout is None or timeout <= 0:
        findings.append(
            Finding(
                threat_class=ThreatClass.MISSING_TIMEOUT.value,
                severity="error",
                message="subprocess timeout missing or non-positive",
                remediation_owners=list(REMEDIATION_OWNERS[ThreatClass.MISSING_TIMEOUT.value]),
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
    """Best-effort process-tree termination (POSIX group kill, then kill)."""
    if proc.poll() is not None:
        return
    try:
        if hasattr(os, "killpg") and proc.pid:
            os.killpg(proc.pid, signal.SIGKILL)
        else:  # pragma: no cover - non-POSIX
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
    try:
        proc.wait(timeout=1.0)
    except Exception:
        pass


def run_allowlisted(
    argv: Sequence[str],
    *,
    policy: SubprocessPolicy = DEFAULT_POLICY,
    shell: bool = False,
    timeout: Optional[float] = None,
    active_workers: int = 0,
) -> tuple[int, bytes, bytes, List[Finding]]:
    """Execute an allowlisted command with timeout and bounded stdout/stderr."""
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

    # Start a new session so killpg can terminate the tree.
    proc = subprocess.Popen(  # noqa: S603 — argv allowlisted, shell=False
        list(argv),
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=effective_timeout)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(proc)
        raise SubprocessGuardError(f"subprocess timed out after {effective_timeout}s") from None

    if len(stdout) > policy.max_stdout_bytes or len(stderr) > policy.max_stderr_bytes:
        findings.append(
            Finding(
                threat_class=ThreatClass.UNBOUNDED_PROCESS_IO.value,
                severity="error",
                message=(
                    f"process IO exceeded bounds "
                    f"stdout={len(stdout)}/{policy.max_stdout_bytes} "
                    f"stderr={len(stderr)}/{policy.max_stderr_bytes}"
                ),
                remediation_owners=list(REMEDIATION_OWNERS[ThreatClass.UNBOUNDED_PROCESS_IO.value]),
            )
        )
        # Truncate for callers; still report the violation.
        stdout = stdout[: policy.max_stdout_bytes]
        stderr = stderr[: policy.max_stderr_bytes]
        raise SubprocessGuardError(findings[-1].message)

    return int(proc.returncode or 0), stdout, stderr, findings
