"""Tests for base_runner.run_manifest_loop -- the shared resume/checkpoint loop
used by the download/lazy-read streamers (ds006644, ds005917, dandi000458)."""
from __future__ import annotations

import json

from tools.streaming.base_runner import run_manifest_loop


def test_processes_all_items_and_writes_manifest(tmp_path):
    seen = []
    manifest = run_manifest_loop(
        ["a", "b", "c"], tmp_path,
        key_fn=lambda x: x,
        process_fn=lambda x: (seen.append(x), {"val": x.upper()})[1],
    )
    assert seen == ["a", "b", "c"]
    assert set(manifest["processed"]) == {"a", "b", "c"}
    assert manifest["processed"]["b"] == {"val": "B"}
    on_disk = json.loads((tmp_path / "manifest.json").read_text())
    assert on_disk == manifest


def test_resumes_and_skips_already_processed(tmp_path):
    run_manifest_loop(["a", "b"], tmp_path, key_fn=lambda x: x, process_fn=lambda x: {"n": 1})
    seen = []
    manifest = run_manifest_loop(
        ["a", "b", "c"], tmp_path,
        key_fn=lambda x: x,
        process_fn=lambda x: (seen.append(x), {"n": 2})[1],
    )
    assert seen == ["c"]  # a, b already done -> skipped
    assert manifest["processed"]["a"] == {"n": 1}  # untouched
    assert manifest["processed"]["c"] == {"n": 2}


def test_error_is_recorded_not_raised(tmp_path):
    def boom(x):
        if x == "b":
            raise RuntimeError("simulated failure")
        return {"ok": True}

    manifest = run_manifest_loop(["a", "b", "c"], tmp_path, key_fn=lambda x: x, process_fn=boom)
    assert manifest["processed"]["a"] == {"ok": True}
    assert "error" in manifest["processed"]["b"]
    assert "simulated failure" in manifest["processed"]["b"]["error"]
    assert manifest["processed"]["c"] == {"ok": True}  # loop continued past the failure


def test_limit_bounds_this_run(tmp_path):
    manifest = run_manifest_loop(
        ["a", "b", "c", "d"], tmp_path,
        key_fn=lambda x: x, process_fn=lambda x: {"v": x}, limit=2,
    )
    assert len(manifest["processed"]) == 2  # only first 2 this run
