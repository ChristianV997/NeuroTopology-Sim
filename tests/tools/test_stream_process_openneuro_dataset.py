from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Load module without requiring it on sys.path (matches tests/tools/test_run_eeg_signal_pipeline_smoke.py)
_spec = importlib.util.spec_from_file_location(
    "stream_process_openneuro_dataset",
    "tools/stream_process_openneuro_dataset.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)


def _fake_processor(subject_root, subject, out_dir, window_seconds, max_windows_per_file, max_channels):
    # Prove we actually received the synced subject's files, and write a tiny
    # per-subject feature file, mirroring what a real processor would do.
    files = list(Path(subject_root).glob("*"))
    (out_dir / f"{subject}_features_m.csv").write_text(f"row_id\n{subject}_w0\n", encoding="utf-8")
    return {"n_m_rows": 1, "n_files_seen": len(files)}


@pytest.fixture(autouse=True)
def _register_fake_processor(monkeypatch):
    monkeypatch.setitem(mod.DATASET_PROCESSORS, "fake_ds", _fake_processor)


def _fake_sync_subject(openneuro_id, subject, dest_root):
    dest = dest_root / subject
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "marker.txt").write_text("synced", encoding="utf-8")
    return dest


def test_unknown_dataset_id_rejected(tmp_path):
    rc = mod.run("no_such_dataset", str(tmp_path / "out"), str(tmp_path / "work"), subjects=["sub-01"])
    assert rc == 2


def test_processes_subjects_and_writes_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "sync_subject", _fake_sync_subject)
    monkeypatch.setattr(mod, "sync_dataset_metadata", lambda *a, **k: None)

    out = tmp_path / "out"
    work = tmp_path / "work"
    rc = mod.run("fake_ds", str(out), str(work), subjects=["sub-01", "sub-02"])
    assert rc == 0

    manifest = json.loads((out / "manifest.json").read_text())
    assert set(manifest["processed_subjects"]) == {"sub-01", "sub-02"}
    assert (out / "sub-01_features_m.csv").exists()
    assert (out / "sub-02_features_m.csv").exists()


def test_raw_files_deleted_after_processing(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "sync_subject", _fake_sync_subject)
    monkeypatch.setattr(mod, "sync_dataset_metadata", lambda *a, **k: None)

    work = tmp_path / "work"
    mod.run("fake_ds", str(tmp_path / "out"), str(work), subjects=["sub-01"])

    # peak-disk guarantee: the subject's raw files must be gone once processed
    assert not (work / "sub-01").exists()


def test_keep_raw_flag_preserves_files(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "sync_subject", _fake_sync_subject)
    monkeypatch.setattr(mod, "sync_dataset_metadata", lambda *a, **k: None)

    work = tmp_path / "work"
    mod.run("fake_ds", str(tmp_path / "out"), str(work), subjects=["sub-01"], keep_raw=True)
    assert (work / "sub-01" / "marker.txt").exists()


def test_resume_skips_already_processed_subjects(tmp_path, monkeypatch):
    calls = []

    def counting_sync(openneuro_id, subject, dest_root):
        calls.append(subject)
        return _fake_sync_subject(openneuro_id, subject, dest_root)

    monkeypatch.setattr(mod, "sync_subject", counting_sync)
    monkeypatch.setattr(mod, "sync_dataset_metadata", lambda *a, **k: None)

    out = tmp_path / "out"
    work = tmp_path / "work"
    mod.run("fake_ds", str(out), str(work), subjects=["sub-01", "sub-02"])
    assert calls == ["sub-01", "sub-02"]

    calls.clear()
    # Second run over the same out dir with a third subject added: only the new
    # one should be synced/processed -- this is the crash-resume guarantee.
    mod.run("fake_ds", str(out), str(work), subjects=["sub-01", "sub-02", "sub-03"])
    assert calls == ["sub-03"]


def test_one_failed_subject_does_not_abort_the_run(tmp_path, monkeypatch):
    def flaky_sync(openneuro_id, subject, dest_root):
        if subject == "sub-bad":
            raise RuntimeError("simulated network failure")
        return _fake_sync_subject(openneuro_id, subject, dest_root)

    monkeypatch.setattr(mod, "sync_subject", flaky_sync)
    monkeypatch.setattr(mod, "sync_dataset_metadata", lambda *a, **k: None)

    out = tmp_path / "out"
    rc = mod.run("fake_ds", str(out), str(tmp_path / "work"), subjects=["sub-bad", "sub-good"])
    assert rc == 0

    manifest = json.loads((out / "manifest.json").read_text())
    assert "sub-good" in manifest["processed_subjects"]
    assert "sub-bad" in manifest["failed_subjects"]


def test_limit_bounds_subjects_processed_this_run(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "sync_subject", _fake_sync_subject)
    monkeypatch.setattr(mod, "sync_dataset_metadata", lambda *a, **k: None)

    out = tmp_path / "out"
    mod.run("fake_ds", str(out), str(tmp_path / "work"), subjects=["sub-01", "sub-02", "sub-03"], limit=1)

    manifest = json.loads((out / "manifest.json").read_text())
    assert len(manifest["processed_subjects"]) == 1
