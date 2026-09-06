"""Regression tests for bounded, offline test execution infrastructure."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import run_tests_isolated as runner


class _Worker:
    def __init__(self, returncode: int = 0, timed_out: bool = False):
        self.pid = 4242
        self.returncode = returncode
        self.timed_out = timed_out

    def wait(self, timeout=None):
        if self.timed_out:
            raise runner.subprocess.TimeoutExpired(["pytest"], timeout)
        return self.returncode

    def poll(self):
        return None if self.timed_out else self.returncode

    def kill(self):
        self.timed_out = False
        self.returncode = 124


def test_iter_batches_is_deterministic_and_singletons_heavy_files():
    files = [
        Path("tests/test_a.py"),
        Path("tests/test_b.py"),
        Path("tests/test_topology.py"),
        Path("tests/test_c.py"),
    ]
    assert list(runner.iter_batches(files, 2)) == [
        [Path("tests/test_a.py"), Path("tests/test_b.py")],
        [Path("tests/test_topology.py")],
        [Path("tests/test_c.py")],
    ]


def test_runner_writes_machine_readable_summary_and_log_paths(tmp_path, monkeypatch):
    workers = []

    def fake_popen(*args, **kwargs):
        worker = _Worker()
        workers.append((args, kwargs))
        return worker

    monkeypatch.setattr(runner, "_pytest_timeout_available", lambda: True)
    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    result = runner.run_batches(
        [Path("tests/test_a.py"), Path("tests/test_b.py")],
        batch_size=2,
        timeout_s=1,
        report_dir=tmp_path,
    )
    assert result == 0
    summary = json.loads((tmp_path / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary["completed"] is True
    assert summary["exit_code"] == 0
    entry = summary["batches"][0]
    assert entry["batch_number"] == 1
    assert entry["test_files"] == ["tests/test_a.py", "tests/test_b.py"]
    assert entry["exit_code"] == 0
    assert entry["timed_out"] is False
    assert Path(entry["stdout_path"]).is_file()
    assert Path(entry["stderr_path"]).is_file()
    assert workers[0][1]["env"]["MPLBACKEND"] == "Agg"
    if os.name == "nt":
        assert workers[0][1]["creationflags"] == runner.subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert workers[0][1]["start_new_session"] is True


def test_runner_continues_after_failure_and_records_every_batch(tmp_path, monkeypatch):
    workers = iter([_Worker(returncode=3), _Worker(returncode=0)])
    monkeypatch.setattr(runner, "_pytest_timeout_available", lambda: True)
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: next(workers))
    result = runner.run_batches(
        [Path("tests/test_a.py"), Path("tests/test_b.py")],
        batch_size=1,
        timeout_s=1,
        report_dir=tmp_path,
    )
    assert result == 3
    summary = json.loads((tmp_path / "batch_summary.json").read_text(encoding="utf-8"))
    assert [item["exit_code"] for item in summary["batches"]] == [3, 0]
    assert summary["completed"] is True


def test_timeout_is_recorded_and_does_not_block_later_batches(tmp_path, monkeypatch):
    workers = iter([_Worker(timed_out=True), _Worker(returncode=0)])
    monkeypatch.setattr(runner, "_pytest_timeout_available", lambda: True)
    monkeypatch.setattr(runner, "_terminate_worker", lambda worker: None)
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: next(workers))
    result = runner.run_batches(
        [Path("tests/test_a.py"), Path("tests/test_b.py")],
        batch_size=1,
        timeout_s=1,
        report_dir=tmp_path,
    )
    assert result == 124
    summary = json.loads((tmp_path / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary["batches"][0]["timeout_status"] == "timeout"
    assert summary["batches"][0]["exit_code"] == 124
    assert summary["batches"][1]["exit_code"] == 0


def test_missing_timeout_plugin_is_explicit(monkeypatch):
    monkeypatch.setattr(runner, "_pytest_timeout_available", lambda: False)
    with pytest.raises(RuntimeError, match="pytest-timeout"):
        runner.run_batches([], batch_size=1, timeout_s=1)


def test_invalid_limits_are_rejected_before_worker_creation():
    with pytest.raises(ValueError, match="positive"):
        runner.run_batches([], batch_size=0, timeout_s=1)
    with pytest.raises(ValueError, match="positive"):
        runner.run_batches([], batch_size=1, timeout_s=0)
