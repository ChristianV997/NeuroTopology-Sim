"""Tests for tools/stream_process_ds001787.py's Phase 4 base_runner wiring.

Mirrors tests/tools/test_stream_process_openneuro_dataset.py's monkeypatch
pattern: `sync_subject`/`sync_dataset_metadata`/`process_subject` stay
directly monkeypatchable module-level names even though the actual
sync/checkpoint/delete loop now lives in tools/streaming/base_runner.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "stream_process_ds001787",
    "tools/stream_process_ds001787.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)


def _fake_sync_dataset_metadata(dest_root):
    (dest_root / "participants.tsv").write_text("participant_id\n", encoding="utf-8")
    code_dir = dest_root / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "MW_Current_TextFileBIDS.zip").write_bytes(b"fake-zip-bytes")


def _fake_sync_subject(subject, dest_root):
    dest = dest_root / subject
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "marker.txt").write_text("synced", encoding="utf-8")
    return dest


def _fake_process_subject(subject_root, subject, out_dir, behavioral_data, n_fixed_windows, fixed_window_seconds, max_channels):
    files = list(Path(subject_root).glob("*"))
    (out_dir / f"{subject}_features_m_fixed.csv").write_text(f"row_id\n{subject}_w0\n", encoding="utf-8")
    return {"n_fixed_m_rows": 1, "n_files_seen": len(files)}


@pytest.fixture(autouse=True)
def _stub_behavioral_parsing(monkeypatch):
    monkeypatch.setattr(
        "sciencer_d.btc_icft.level_m.ds001787_behavioral.parse_behavioral_zip",
        lambda zip_bytes: {},
    )


def test_processes_subjects_and_writes_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "sync_subject", _fake_sync_subject)
    monkeypatch.setattr(mod, "sync_dataset_metadata", _fake_sync_dataset_metadata)
    monkeypatch.setattr(mod, "process_subject", _fake_process_subject)

    out = tmp_path / "out"
    work = tmp_path / "work"
    rc = mod.run(str(out), str(work), subjects=["sub-001", "sub-013"])
    assert rc == 0

    manifest = json.loads((out / "manifest.json").read_text())
    assert set(manifest["processed_subjects"]) == {"sub-001", "sub-013"}
    assert (out / "sub-001_features_m_fixed.csv").exists()
    assert (out / "sub-013_features_m_fixed.csv").exists()


def test_raw_files_deleted_after_processing(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "sync_subject", _fake_sync_subject)
    monkeypatch.setattr(mod, "sync_dataset_metadata", _fake_sync_dataset_metadata)
    monkeypatch.setattr(mod, "process_subject", _fake_process_subject)

    work = tmp_path / "work"
    mod.run(str(tmp_path / "out"), str(work), subjects=["sub-001"])
    assert not (work / "sub-001").exists()


def test_keep_raw_flag_preserves_files(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "sync_subject", _fake_sync_subject)
    monkeypatch.setattr(mod, "sync_dataset_metadata", _fake_sync_dataset_metadata)
    monkeypatch.setattr(mod, "process_subject", _fake_process_subject)

    work = tmp_path / "work"
    mod.run(str(tmp_path / "out"), str(work), subjects=["sub-001"], keep_raw=True)
    assert (work / "sub-001" / "marker.txt").exists()


def test_resume_skips_already_processed_subjects(tmp_path, monkeypatch):
    calls = []

    def counting_sync(subject, dest_root):
        calls.append(subject)
        return _fake_sync_subject(subject, dest_root)

    monkeypatch.setattr(mod, "sync_subject", counting_sync)
    monkeypatch.setattr(mod, "sync_dataset_metadata", _fake_sync_dataset_metadata)
    monkeypatch.setattr(mod, "process_subject", _fake_process_subject)

    out = tmp_path / "out"
    work = tmp_path / "work"
    mod.run(str(out), str(work), subjects=["sub-001", "sub-013"])
    assert calls == ["sub-001", "sub-013"]

    calls.clear()
    mod.run(str(out), str(work), subjects=["sub-001", "sub-013", "sub-020"])
    assert calls == ["sub-020"]


def test_one_failed_subject_does_not_abort_the_run(tmp_path, monkeypatch):
    def flaky_sync(subject, dest_root):
        if subject == "sub-bad":
            raise RuntimeError("simulated network failure")
        return _fake_sync_subject(subject, dest_root)

    monkeypatch.setattr(mod, "sync_subject", flaky_sync)
    monkeypatch.setattr(mod, "sync_dataset_metadata", _fake_sync_dataset_metadata)
    monkeypatch.setattr(mod, "process_subject", _fake_process_subject)

    out = tmp_path / "out"
    rc = mod.run(str(out), str(tmp_path / "work"), subjects=["sub-bad", "sub-good"])
    assert rc == 0

    manifest = json.loads((out / "manifest.json").read_text())
    assert "sub-good" in manifest["processed_subjects"]
    assert "sub-bad" in manifest["failed_subjects"]


def test_limit_bounds_subjects_processed_this_run(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "sync_subject", _fake_sync_subject)
    monkeypatch.setattr(mod, "sync_dataset_metadata", _fake_sync_dataset_metadata)
    monkeypatch.setattr(mod, "process_subject", _fake_process_subject)

    out = tmp_path / "out"
    mod.run(str(out), str(tmp_path / "work"), subjects=["sub-001", "sub-013", "sub-020"], limit=1)

    manifest = json.loads((out / "manifest.json").read_text())
    assert len(manifest["processed_subjects"]) == 1


def test_metadata_synced_once_when_missing_then_skipped(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "sync_subject", _fake_sync_subject)
    monkeypatch.setattr(mod, "sync_dataset_metadata", lambda dest_root: (calls.append(1), _fake_sync_dataset_metadata(dest_root)))
    monkeypatch.setattr(mod, "process_subject", _fake_process_subject)

    work = tmp_path / "work"
    mod.run(str(tmp_path / "out1"), str(work), subjects=["sub-001"])
    assert len(calls) == 1

    # second run over the same work_root: metadata + behavioral zip already present, skip re-sync
    mod.run(str(tmp_path / "out2"), str(work), subjects=["sub-013"])
    assert len(calls) == 1
