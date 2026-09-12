"""Atomic, fsync'd, recovery-safe manifest writes."""
from __future__ import annotations

import json
import os
from pathlib import Path

from tools.streaming import base_runner


def test_save_manifest_fsyncs_before_replace(tmp_path, monkeypatch):
    fsync_fds = []
    real_fsync = os.fsync

    def tracking_fsync(fd):
        fsync_fds.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(base_runner.os, "fsync", tracking_fsync)
    path = tmp_path / "manifest.json"
    payload = {"processed_subjects": {"sub-01": {"n": 1}}, "failed_subjects": {}}
    base_runner.save_manifest(path, payload)
    assert fsync_fds, "save_manifest must fsync the temp file before replace"
    assert path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_save_manifest_uses_os_replace(tmp_path, monkeypatch):
    calls = []
    real_replace = os.replace

    def tracking_replace(src, dst):
        calls.append((Path(src).name, Path(dst).name))
        return real_replace(src, dst)

    monkeypatch.setattr(base_runner.os, "replace", tracking_replace)
    path = tmp_path / "manifest.json"
    base_runner.save_manifest(path, {"processed": {"a": {"ok": True}}})
    assert calls == [("manifest.json.tmp", "manifest.json")]


def test_truncated_dest_recovers_from_complete_tmp(tmp_path):
    path = tmp_path / "manifest.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    path.write_text("{truncated", encoding="utf-8")
    tmp.write_text(
        json.dumps({"processed_subjects": {"sub-01": {"n": 3}}, "failed_subjects": {}}),
        encoding="utf-8",
    )
    loaded = base_runner.load_manifest(path)
    assert loaded["processed_subjects"]["sub-01"] == {"n": 3}
    assert json.loads(path.read_text(encoding="utf-8"))["processed_subjects"]["sub-01"]["n"] == 3


def test_valid_dest_is_preferred_over_stale_tmp(tmp_path):
    path = tmp_path / "manifest.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    base_runner.save_manifest(path, {"processed_subjects": {"sub-new": {"n": 2}}, "failed_subjects": {}})
    tmp.write_text(
        json.dumps({"processed_subjects": {"sub-old": {"n": 1}}, "failed_subjects": {}}),
        encoding="utf-8",
    )
    loaded = base_runner.load_manifest(path)
    assert "sub-new" in loaded["processed_subjects"]
    assert "sub-old" not in loaded["processed_subjects"]


def test_manifest_loop_write_is_atomic(tmp_path, monkeypatch):
    writes = []
    real = base_runner.save_manifest

    def tracking(path, manifest):
        writes.append(Path(path).name)
        return real(path, manifest)

    monkeypatch.setattr(base_runner, "save_manifest", tracking)
    base_runner.run_manifest_loop(
        ["a"], tmp_path, key_fn=lambda x: x, process_fn=lambda x: {"ok": True}
    )
    assert writes == ["manifest.json"]
    assert not (tmp_path / "manifest.json.tmp").exists()
