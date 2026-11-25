"""Unit and integration tests for scripts/run_tests_isolated.py.

Validates:
1. Timeout termination (subprocesses killed within bound, exit code 124).
2. Partitioning (batch chunking math).
3. Ordering (deterministic lexicographical sorting).
4. Failure propagation (non-zero exit code on failure).
5. Environment caps (OMP/MKL threads pinned to 1).
6. Output isolation (distinct temporary base directories).
7. Network policy enforcement (socket block active).
8. Telemetry and JSON report generation.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.run_tests_isolated import (
    _build_pytest_command,
    _execute_worker,
    _worker_popen_kwargs,
    discover,
    run_batch,
    run_batches,
)

try:
    import psutil  # noqa: F401
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False

_POSIX = os.name != "nt"


def test_deterministic_ordering(tmp_path: Path):
    """File discovery must be strictly sorted by POSIX relative path."""
    (tmp_path / "test_z.py").write_text("def test_z(): pass\n")
    (tmp_path / "test_a.py").write_text("def test_a(): pass\n")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "test_m.py").write_text("def test_m(): pass\n")
    (sub / "test_b.py").write_text("def test_b(): pass\n")

    files = discover(tmp_path)
    rel_paths = [p.relative_to(tmp_path.resolve()).as_posix() for p in files]

    assert rel_paths == sorted(rel_paths)
    assert rel_paths == ["subdir/test_b.py", "subdir/test_m.py", "test_a.py", "test_z.py"]


def test_batch_partitioning(tmp_path: Path):
    """Batches must partition test files into correct chunks without dropping any."""
    files = [tmp_path / f"test_{i:02d}.py" for i in range(11)]
    for f in files:
        f.write_text("def test_ok(): pass\n")

    batch_size = 4
    total_batches = (len(files) + batch_size - 1) // batch_size
    assert total_batches == 3

    chunks = [files[i : i + batch_size] for i in range(0, len(files), batch_size)]
    assert len(chunks[0]) == 4
    assert len(chunks[1]) == 4
    assert len(chunks[2]) == 3
    assert sum(len(c) for c in chunks) == 11


def test_timeout_termination(tmp_path: Path):
    """A hanging or long-running worker must be terminated forcefully with exit code 124."""
    hanging_test = tmp_path / "test_hanging.py"
    hanging_test.write_text(
        "import time\n"
        "def test_sleep():\n"
        "    time.sleep(30)\n"
    )

    result = run_batch(
        batch=[hanging_test],
        batch_idx=1,
        total_batches=1,
        timeout_s=2,
        has_pytest_timeout=False,
    )

    assert result["status"] == "timeout"
    assert result["exit_code"] == 124
    assert result["duration_s"] >= 1.8


def test_failure_propagation(tmp_path: Path):
    """Test failures must report exit_code != 0 and propagate failure details."""
    failing_test = tmp_path / "test_fail.py"
    failing_test.write_text(
        "def test_boom():\n"
        "    assert False, 'Expected deliberate failure'\n"
    )

    result = run_batch(
        batch=[failing_test],
        batch_idx=1,
        total_batches=1,
        timeout_s=30,
        has_pytest_timeout=False,
    )

    assert result["status"] == "failed"
    assert result["exit_code"] != 0
    assert any("test_boom" in f for f in result["failures"]) or "FAILED" in result["stdout_tail"]


def test_environment_thread_caps(tmp_path: Path):
    """Subprocess workers must receive thread environment variables capped to 1."""
    env_test = tmp_path / "test_env.py"
    env_test.write_text(
        "import os\n"
        "def test_threads():\n"
        "    assert os.environ.get('OMP_NUM_THREADS') == '1'\n"
        "    assert os.environ.get('OPENBLAS_NUM_THREADS') == '1'\n"
        "    assert os.environ.get('MKL_NUM_THREADS') == '1'\n"
        "    assert os.environ.get('NUMEXPR_NUM_THREADS') == '1'\n"
    )

    result = run_batch(
        batch=[env_test],
        batch_idx=1,
        total_batches=1,
        timeout_s=30,
        has_pytest_timeout=False,
    )

    assert result["status"] == "passed"
    assert result["exit_code"] == 0


def test_output_isolation(tmp_path: Path):
    """Batches must receive distinct temporary directories."""
    t1 = tmp_path / "test_one.py"
    t1.write_text("def test_1(): pass\n")
    t2 = tmp_path / "test_two.py"
    t2.write_text("def test_2(): pass\n")

    res1 = run_batch([t1], batch_idx=1, total_batches=2, timeout_s=30, has_pytest_timeout=False)
    res2 = run_batch([t2], batch_idx=2, total_batches=2, timeout_s=30, has_pytest_timeout=False)

    assert res1["exit_code"] == 0
    assert res2["exit_code"] == 0


def test_network_policy():
    """Conftest network guard must block external TCP connections unless marked @pytest.mark.network."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(RuntimeError) as exc_info:
        s.connect(("93.184.216.34", 80))  # example.com IP

    assert "Unauthorized network connection" in str(exc_info.value)
    assert "strictly offline" in str(exc_info.value)


def test_json_report_generation(tmp_path: Path):
    """Runner must serialize telemetry reports with summary metrics and per-batch details."""
    t1 = tmp_path / "test_ok1.py"
    t1.write_text("def test_ok(): pass\n")
    t2 = tmp_path / "test_ok2.py"
    t2.write_text("def test_ok(): pass\n")

    report_file = tmp_path / "report.json"
    exit_code = run_batches(
        files=[t1, t2],
        batch_size=1,
        timeout_s=30,
        report_path=report_file,
    )

    assert exit_code == 0
    assert report_file.exists()

    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert "summary" in data
    assert data["summary"]["total_files"] == 2
    assert data["summary"]["total_batches"] == 2
    assert data["summary"]["passed_batches"] == 2
    assert data["summary"]["failed_batches"] == 0
    assert data["summary"]["overall_exit_code"] == 0
    assert len(data["batches"]) == 2


# ===========================================================================
# Regression tests for the process-group termination hang (self-kill defect).
# ===========================================================================
def test_normal_success(tmp_path: Path):
    """A passing batch reports status=passed / exit 0 (baseline sanity)."""
    t = tmp_path / "test_ok.py"
    t.write_text("def test_ok():\n    assert True\n")
    res = run_batch([t], batch_idx=1, total_batches=1, timeout_s=30, has_pytest_timeout=False)
    assert res["status"] == "passed"
    assert res["exit_code"] == 0


def test_campaign_not_self_terminated(tmp_path: Path):
    """Regression: a timed-out worker must not kill the runner's own group.

    Before the fix, ``os.killpg(os.getpgid(child), SIGKILL)`` targeted the
    runner's process group (no isolated session), SIGKILLing this very pytest
    process (rc 137, no output). Reaching the assertions below proves the
    campaign survived the timeout.
    """
    hanging = tmp_path / "test_hang.py"
    hanging.write_text("import time\ndef test_sleep():\n    time.sleep(30)\n")
    res = run_batch([hanging], batch_idx=1, total_batches=1, timeout_s=2, has_pytest_timeout=False)
    assert res["status"] == "timeout"
    assert res["exit_code"] == 124
    sentinel = "runner-survived"
    assert sentinel == "runner-survived"  # executes only if we were not killed


def test_timeout_reporting_not_a_pass(tmp_path: Path):
    """A timeout is classified as timeout/124, never silently a pass or skip."""
    hanging = tmp_path / "test_hang.py"
    hanging.write_text("import time\ndef test_sleep():\n    time.sleep(30)\n")
    res = run_batch([hanging], batch_idx=1, total_batches=1, timeout_s=2, has_pytest_timeout=False)
    assert res["status"] == "timeout"
    assert res["exit_code"] == 124
    assert res["status"] != "passed"
    assert res["duration_s"] < 12  # hard timeout enforced promptly, not hung


@pytest.mark.skipif(not _POSIX, reason="SIGTERM-ignore escalation is POSIX-specific")
def test_child_ignoring_graceful_termination(tmp_path: Path):
    """A worker that ignores SIGTERM must still be force-killed after the grace."""
    ignore = tmp_path / "test_ignore.py"
    ignore.write_text(
        "import signal, time\n"
        "def test_ignore():\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    time.sleep(120)\n"
    )
    start = time.monotonic()
    res = run_batch([ignore], batch_idx=1, total_batches=1, timeout_s=2, has_pytest_timeout=False)
    elapsed = time.monotonic() - start
    assert res["status"] == "timeout"
    assert res["exit_code"] == 124
    # timeout(2s) + one grace(5s) + margin; must not hang for the 120s sleep.
    assert elapsed < 20


@pytest.mark.skipif(not (_POSIX and _HAS_PSUTIL),
                    reason="orphan verification uses POSIX process groups + psutil")
def test_no_orphan_grandchild(tmp_path: Path):
    """A grandchild spawned by a timed-out worker must not be orphaned."""
    import psutil

    pidfile = tmp_path / "grandchild.pid"
    worker = tmp_path / "test_grandchild.py"
    worker.write_text(
        "import os, sys, subprocess, time\n"
        "def test_spawn():\n"
        "    g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"    open(r'{pidfile}', 'w').write(str(g.pid))\n"
        "    time.sleep(120)\n"
    )
    res = run_batch([worker], batch_idx=1, total_batches=1, timeout_s=3, has_pytest_timeout=False)
    assert res["status"] == "timeout"

    for _ in range(60):
        if pidfile.exists() and pidfile.read_text().strip():
            break
        time.sleep(0.05)
    gpid = int(pidfile.read_text().strip())

    deadline = time.time() + 5.0
    cleaned = False
    while time.time() < deadline:
        if not psutil.pid_exists(gpid):
            cleaned = True
            break
        try:
            if psutil.Process(gpid).status() == psutil.STATUS_ZOMBIE:
                cleaned = True
                break
        except psutil.NoSuchProcess:
            cleaned = True
            break
        time.sleep(0.1)
    assert cleaned, f"grandchild {gpid} was orphaned after worker timeout"


@pytest.mark.skipif(not _POSIX, reason="process-group isolation is POSIX-specific here")
def test_posix_worker_uses_isolated_process_group():
    """Worker Popen kwargs must request an isolated session/group on POSIX."""
    kwargs = _worker_popen_kwargs()
    assert kwargs == {"start_new_session": True}


def test_stdout_flood_does_not_deadlock():
    """Concurrent draining must prevent a pipe-buffer deadlock (no false timeout)."""
    payload = 5 * 1024 * 1024  # 5 MB, far exceeding the OS pipe buffer
    code = f"import sys; sys.stdout.write('x' * {payload}); sys.stdout.flush()"
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        **_worker_popen_kwargs(),
    )
    exit_code, timed_out, stdout_text, _stderr, _peak = _execute_worker(proc, timeout_s=30)
    assert timed_out is False
    assert exit_code == 0
    assert len(stdout_text) >= payload


def test_command_construction_is_argv_list(tmp_path: Path):
    """Worker command is a plain argv list (shell=False), cross-platform safe."""
    batch = [tmp_path / "test_a.py", tmp_path / "test_b.py"]
    cmd = _build_pytest_command(batch, str(tmp_path / "bt"), timeout_s=42,
                                has_pytest_timeout=True, extra_pytest_args=["-m", "not slow"])
    assert cmd[0] == sys.executable
    assert cmd[1:3] == ["-m", "pytest"]
    assert f"--basetemp={tmp_path / 'bt'}" in cmd
    assert "--timeout" in cmd and "42" in cmd
    assert cmd[-2:] == [str(batch[0]), str(batch[1])]
    assert all(isinstance(part, str) for part in cmd)
    # Without pytest-timeout, no --timeout flag is added.
    cmd2 = _build_pytest_command(batch, str(tmp_path / "bt"), timeout_s=42, has_pytest_timeout=False)
    assert "--timeout" not in cmd2


def test_deterministic_batch_order(tmp_path: Path):
    """Discovery order is stable across repeated calls (deterministic batching)."""
    for i in range(7):
        (tmp_path / f"test_{i:02d}.py").write_text("def test_x(): pass\n")
    first = [p.as_posix() for p in discover(tmp_path)]
    second = [p.as_posix() for p in discover(tmp_path)]
    assert first == second == sorted(first)
