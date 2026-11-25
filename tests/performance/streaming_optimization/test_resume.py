"""Resume skips valid work units; invalid/error units retry."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from tools.streaming import base_runner


def test_manifest_loop_retries_error_entries_not_valid_ones(tmp_path):
    calls = []

    def boom(item):
        calls.append(item)
        if item == "b":
            raise RuntimeError("transient")
        return {"ok": True, "id": item}

    with redirect_stdout(io.StringIO()):
        first = base_runner.run_manifest_loop(
            ["a", "b", "c"], tmp_path, key_fn=lambda x: x, process_fn=boom
        )
    assert first["processed"]["a"]["ok"] is True
    assert "error" in first["processed"]["b"]
    assert first["processed"]["c"]["ok"] is True

    calls.clear()

    def recover(item):
        calls.append(item)
        return {"ok": True, "id": item, "retried": True}

    with redirect_stdout(io.StringIO()):
        second = base_runner.run_manifest_loop(
            ["a", "b", "c"], tmp_path, key_fn=lambda x: x, process_fn=recover
        )
    assert calls == ["b"], f"only the failed unit should rerun, got {calls}"
    assert second["processed"]["a"] == {"ok": True, "id": "a"}
    assert second["processed"]["b"] == {"ok": True, "id": "b", "retried": True}


def test_manifest_loop_retries_empty_and_explicit_incomplete_entries(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"processed": {"empty": {}, "partial": {"status": "PARTIAL"}}}),
        encoding="utf-8",
    )
    calls = []

    def recover(item):
        calls.append(item)
        return {"ok": True, "id": item}

    with redirect_stdout(io.StringIO()):
        result = base_runner.run_manifest_loop(
            ["empty", "partial"], tmp_path, key_fn=lambda x: x, process_fn=recover
        )
    assert calls == ["empty", "partial"]
    assert all(result["processed"][item]["ok"] for item in calls)


def test_metadata_sync_none_timeout_uses_finite_default(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, check=True, timeout=None):
        seen["timeout"] = timeout

    monkeypatch.setattr(base_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(base_runner, "_aws_command", lambda: ["aws"])
    base_runner.sync_s3_dataset_metadata("openneuro.org", "ds000000", tmp_path, timeout_s=None)
    assert seen["timeout"] == base_runner.S3_METADATA_SYNC_TIMEOUT_S


def test_streaming_loop_retries_failed_and_clears_failure_on_success(tmp_path):
    out_path = tmp_path / "out"
    work_path = tmp_path / "work"
    sync_calls = []
    fail_once = {"done": False}

    def sync_fn(subject, dest):
        sync_calls.append(subject)
        root = dest / subject
        root.mkdir(parents=True, exist_ok=True)
        if subject == "sub-bad" and not fail_once["done"]:
            fail_once["done"] = True
            raise RuntimeError("first fail")
        return root

    def process_fn(subject_root, subject, out_path):
        return {"n_rows": 1, "subject": subject}

    with redirect_stdout(io.StringIO()):
        first = base_runner.run_streaming_loop(
            ["sub-bad", "sub-good"], out_path, work_path, sync_fn, process_fn
        )
    assert "sub-good" in first["processed_subjects"]
    assert "sub-bad" in first["failed_subjects"]

    sync_calls.clear()
    with redirect_stdout(io.StringIO()):
        second = base_runner.run_streaming_loop(
            ["sub-bad", "sub-good"], out_path, work_path, sync_fn, process_fn
        )
    assert sync_calls == ["sub-bad"]
    assert "sub-bad" in second["processed_subjects"]
    assert "sub-bad" not in second["failed_subjects"]
    on_disk = json.loads((out_path / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk == second


def test_valid_processed_subject_is_not_rerun(tmp_path):
    out_path = tmp_path / "out"
    work_path = tmp_path / "work"
    seen = []

    def sync_fn(subject, dest):
        seen.append(subject)
        root = dest / subject
        root.mkdir(parents=True, exist_ok=True)
        return root

    def process_fn(subject_root, subject, out_path):
        return {"n_rows": 1}

    with redirect_stdout(io.StringIO()):
        base_runner.run_streaming_loop(["sub-01"], out_path, work_path, sync_fn, process_fn)
        base_runner.run_streaming_loop(["sub-01"], out_path, work_path, sync_fn, process_fn)
    assert seen == ["sub-01"]
