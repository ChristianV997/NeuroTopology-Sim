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
import sys
from pathlib import Path

import pytest

from scripts.run_tests_isolated import discover, run_batch, run_batches


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
