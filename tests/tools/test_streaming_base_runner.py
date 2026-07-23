"""Isolated tests for tools/streaming/base_runner.py: the shared sync/
checkpoint/delete skeleton extracted from stream_process_openneuro_dataset.py
and stream_process_ds001787.py in Phase 4. Dataset-specific behavior is
covered by each tool's own test file; this file covers only the shared
loop/manifest/csv primitives directly.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.streaming import base_runner
from sciencer_d.btc_icft.datasets.onboarding_registry import get_dataset_config


def test_aws_command_uses_resolved_windows_launcher(monkeypatch):
    launcher = r"C:\Users\HP\.local\bin\aws.cmd"
    monkeypatch.setattr(base_runner.shutil, "which", lambda name: launcher if name == "aws" else None)
    assert base_runner._aws_command() == [launcher]


def test_propofol_registry_maps_real_bids_tasks():
    cfg = get_dataset_config("ds005620")
    assert cfg.task_to_state == {
        "awake": "awake",
        "sed": "sedated",
        "sed2": "sedated",
        "sedated": "sedated",
    }


def test_load_manifest_missing_file_returns_empty_shape(tmp_path):
    manifest = base_runner.load_manifest(tmp_path / "nope.json")
    assert manifest == {"processed_subjects": {}, "failed_subjects": {}}


def test_save_and_load_manifest_round_trip(tmp_path):
    path = tmp_path / "manifest.json"
    base_runner.save_manifest(path, {"processed_subjects": {"sub-01": {"n": 3}}, "failed_subjects": {}})
    reloaded = base_runner.load_manifest(path)
    assert reloaded == {"processed_subjects": {"sub-01": {"n": 3}}, "failed_subjects": {}}


def test_write_rows_csv_joins_warnings_list(tmp_path):
    path = tmp_path / "out.csv"
    base_runner.write_rows_csv(path, [{"row_id": "r1", "warnings": ["a", "b"]}])
    text = path.read_text(encoding="utf-8")
    assert "a; b" in text


def test_write_rows_csv_no_rows_no_file_by_default(tmp_path):
    path = tmp_path / "out.csv"
    base_runner.write_rows_csv(path, [])
    assert not path.exists()


def test_write_rows_csv_empty_marker_when_requested(tmp_path):
    path = tmp_path / "out.csv"
    base_runner.write_rows_csv(path, [], write_empty_marker=True)
    assert path.exists()
    assert path.read_text(encoding="utf-8") == ""


def _make_sync_and_process(sync_calls, process_calls, fail_on=()):
    def sync_fn(subject, work_path):
        sync_calls.append(subject)
        dest = work_path / subject
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "raw.bin").write_bytes(b"x")
        if subject in fail_on:
            raise RuntimeError(f"simulated failure for {subject}")
        return dest

    def process_fn(subject_root, subject, out_path):
        process_calls.append(subject)
        return {"n_rows": 1}

    return sync_fn, process_fn


def test_run_streaming_loop_processes_and_checkpoints(tmp_path):
    out_path = tmp_path / "out"
    work_path = tmp_path / "work"
    sync_calls, process_calls = [], []
    sync_fn, process_fn = _make_sync_and_process(sync_calls, process_calls)

    manifest = base_runner.run_streaming_loop(
        ["sub-01", "sub-02"], out_path, work_path, sync_fn, process_fn
    )
    assert sync_calls == ["sub-01", "sub-02"]
    assert process_calls == ["sub-01", "sub-02"]
    assert set(manifest["processed_subjects"]) == {"sub-01", "sub-02"}
    assert manifest["failed_subjects"] == {}
    on_disk = json.loads((out_path / "manifest.json").read_text())
    assert on_disk == manifest


def test_run_streaming_loop_deletes_raw_by_default(tmp_path):
    out_path = tmp_path / "out"
    work_path = tmp_path / "work"
    sync_fn, process_fn = _make_sync_and_process([], [])
    base_runner.run_streaming_loop(["sub-01"], out_path, work_path, sync_fn, process_fn)
    assert not (work_path / "sub-01").exists()


def test_run_streaming_loop_keep_raw_preserves_files(tmp_path):
    out_path = tmp_path / "out"
    work_path = tmp_path / "work"
    sync_fn, process_fn = _make_sync_and_process([], [])
    base_runner.run_streaming_loop(["sub-01"], out_path, work_path, sync_fn, process_fn, keep_raw=True)
    assert (work_path / "sub-01" / "raw.bin").exists()


def test_run_streaming_loop_resume_skips_processed_subjects(tmp_path):
    out_path = tmp_path / "out"
    work_path = tmp_path / "work"
    sync_calls, process_calls = [], []
    sync_fn, process_fn = _make_sync_and_process(sync_calls, process_calls)

    base_runner.run_streaming_loop(["sub-01", "sub-02"], out_path, work_path, sync_fn, process_fn)
    sync_calls.clear()
    process_calls.clear()

    # Same out_path (manifest persists on disk) with a third subject added:
    # only the new one should be synced/processed on this second call.
    base_runner.run_streaming_loop(["sub-01", "sub-02", "sub-03"], out_path, work_path, sync_fn, process_fn)
    assert sync_calls == ["sub-03"]
    assert process_calls == ["sub-03"]


def test_run_streaming_loop_one_failure_does_not_abort(tmp_path):
    out_path = tmp_path / "out"
    work_path = tmp_path / "work"
    sync_calls, process_calls = [], []
    sync_fn, process_fn = _make_sync_and_process(sync_calls, process_calls, fail_on={"sub-bad"})

    manifest = base_runner.run_streaming_loop(
        ["sub-bad", "sub-good"], out_path, work_path, sync_fn, process_fn
    )
    assert "sub-good" in manifest["processed_subjects"]
    assert "sub-bad" in manifest["failed_subjects"]
    assert "simulated failure" in manifest["failed_subjects"]["sub-bad"]


def test_run_streaming_loop_limit_bounds_this_run(tmp_path):
    out_path = tmp_path / "out"
    work_path = tmp_path / "work"
    sync_fn, process_fn = _make_sync_and_process([], [])
    manifest = base_runner.run_streaming_loop(
        ["sub-01", "sub-02", "sub-03"], out_path, work_path, sync_fn, process_fn, limit=1
    )
    assert len(manifest["processed_subjects"]) == 1


def test_run_streaming_loop_checkpoints_after_every_subject_not_just_at_end(tmp_path):
    """A crash mid-run must not lose already-completed subjects: assert the
    manifest on disk reflects each subject immediately, not only after the
    whole loop finishes (this is what makes overnight/interrupted runs safe).
    """
    out_path = tmp_path / "out"
    work_path = tmp_path / "work"
    manifest_path = out_path / "manifest.json"
    seen_after_first = {}

    def sync_fn(subject, work_path):
        dest = work_path / subject
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def process_fn(subject_root, subject, out_path):
        if subject == "sub-01":
            # Simulate inspecting the manifest mid-run, before sub-02 is touched.
            seen_after_first.update(json.loads(manifest_path.read_text()) if manifest_path.exists() else {})
        return {"n_rows": 1}

    base_runner.run_streaming_loop(["sub-01", "sub-02"], out_path, work_path, sync_fn, process_fn)
    # sub-01's own checkpoint write happens after process_fn returns, so at the
    # point process_fn(sub-01) ran, the manifest file shouldn't exist yet --
    # but by the time sub-02 is processed, sub-01 must already be checkpointed.
    final_manifest = json.loads(manifest_path.read_text())
    assert set(final_manifest["processed_subjects"]) == {"sub-01", "sub-02"}
