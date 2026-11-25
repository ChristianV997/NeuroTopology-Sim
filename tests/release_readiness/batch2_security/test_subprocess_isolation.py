"""Subprocess allowlists, shell=False, timeout, tree kill, IO/worker bounds."""
from __future__ import annotations

import os
import sys
from pathlib import Path

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


def test_default_policy_does_not_trust_path_search_interpreter_names():
    findings = validate_invocation(
        ["python3", "-c", "pass"], shell=False, timeout=1.0
    )
    assert any(f.threat_class == ThreatClass.UNSAFE_SUBPROCESS.value for f in findings)


def test_allowlisted_basename_does_not_trust_an_arbitrary_binary_path(tmp_path: Path):
    fake_python = tmp_path / "python3.12.exe"
    fake_python.write_text("synthetic executable placeholder", encoding="utf-8")
    findings = validate_invocation(
        [str(fake_python), "-c", "pass"], shell=False, timeout=1.0
    )
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
        allowlist=frozenset(
            {str(Path(sys.executable).resolve()), os.path.basename(sys.executable), "python", "python3"}
        ),
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


def test_stdout_limit_terminates_a_still_running_child_before_timeout():
    policy = SubprocessPolicy(
        allowlist=frozenset(
            {str(Path(sys.executable).resolve()), os.path.basename(sys.executable)}
        ),
        timeout_seconds=5.0,
        max_stdout_bytes=16,
        max_stderr_bytes=64,
        max_workers=2,
    )
    code = "import os, time; os.write(1, b'X' * 1024); time.sleep(30)"
    with pytest.raises(SubprocessGuardError, match="IO exceeded"):
        run_allowlisted([sys.executable, "-c", code], policy=policy, timeout=2.0)


@pytest.mark.skipif(
    os.name == "nt" or not Path("/proc").exists(),
    reason="requires POSIX process groups and procfs",
)
def test_timeout_kills_descendant_when_group_leader_exits(tmp_path: Path):
    import signal
    import time

    pid_path = tmp_path / "child.pid"
    child = "import time; time.sleep(30)"
    parent = (
        "import subprocess, sys; "
        f"p = subprocess.Popen([sys.executable, '-c', {child!r}]); "
        f"open({str(pid_path)!r}, 'w', encoding='utf-8').write(str(p.pid))"
    )
    policy = SubprocessPolicy(
        allowlist=frozenset(
            {str(Path(sys.executable).resolve()), os.path.basename(sys.executable)}
        )
    )
    with pytest.raises(SubprocessGuardError, match="timed out"):
        run_allowlisted([sys.executable, "-c", parent], policy=policy, timeout=0.5)

    child_pid = int(pid_path.read_text(encoding="utf-8"))
    try:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            stat = Path(f"/proc/{child_pid}/stat")
            if stat.exists() and stat.read_text(encoding="utf-8").split()[2] == "Z":
                break
            time.sleep(0.02)
        else:
            pytest.fail("timed-out subprocess left its descendant running")
    finally:
        try:
            os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
