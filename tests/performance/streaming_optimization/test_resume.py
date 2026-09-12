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
