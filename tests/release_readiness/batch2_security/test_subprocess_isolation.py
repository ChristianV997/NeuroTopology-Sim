"""Subprocess allowlists, shell=False, timeout, tree kill, IO/worker bounds."""
from __future__ import annotations

import os
import sys

import pytest

from tools.release_readiness.batch2_security.schema import ThreatClass
from tools.release_readiness.batch2_security.subprocess_guard import (
    DEFAULT_POLICY,
    SubprocessGuardError,
    SubprocessPolicy,
    run_allowlisted,
    validate_invocation,
)


def test_shell_true_is_rejected():
    findings = validate_invocation(["python3", "-c", "print(1)"], shell=True, timeout=1.0)
    assert any(f.threat_class == ThreatClass.SHELL_TRUE.value for f in findings)


def test_non_allowlisted_binary_rejected():
    findings = validate_invocation(["curl", "https://example.com"], shell=False, timeout=1.0)
    assert any(f.threat_class == ThreatClass.UNSAFE_SUBPROCESS.value for f in findings)


def test_missing_timeout_rejected():
    findings = validate_invocation(["python3", "-c", "print(1)"], shell=False, timeout=None)
    assert any(f.threat_class == ThreatClass.MISSING_TIMEOUT.value for f in findings)


def test_worker_limit_rejected():
    findings = validate_invocation(
        ["python3", "-c", "print(1)"],
        shell=False,
        timeout=1.0,
        active_workers=DEFAULT_POLICY.max_workers,
    )
    assert any(f.threat_class == ThreatClass.WORKER_LIMIT_EXCEEDED.value for f in findings)


def test_allowlisted_execution_ok():
    code, stdout, stderr, findings = run_allowlisted(
        [sys.executable, "-c", "print('ok')"],
        timeout=5.0,
    )
    assert code == 0
    assert b"ok" in stdout
    assert findings == []


def test_timeout_terminates_process_tree():
    with pytest.raises(SubprocessGuardError, match="timed out"):
        run_allowlisted(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            timeout=0.2,
        )


def test_bounded_stdout_rejects_flood():
    policy = SubprocessPolicy(
        allowlist=frozenset({os.path.basename(sys.executable), "python", "python3"}),
        timeout_seconds=5.0,
        max_stdout_bytes=16,
        max_stderr_bytes=64 * 1024,
        max_workers=2,
    )
    with pytest.raises(SubprocessGuardError, match="IO exceeded"):
        run_allowlisted(
            [sys.executable, "-c", "print('X' * 1000)"],
            policy=policy,
            timeout=5.0,
        )
