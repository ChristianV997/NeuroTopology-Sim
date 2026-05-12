"""Basic tests for sciencer_d/btc_icft/rag/artifact_manifest.py (P20.0)."""

from __future__ import annotations

import importlib.util
import json
import sys
import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
MOD_PATH = REPO_ROOT / "sciencer_d" / "btc_icft" / "rag" / "artifact_manifest.py"


def _load_mod():
    module_name = "sciencer_d.btc_icft.rag.artifact_manifest"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_safe_claim_constant():
    mod = _load_mod()
    assert "RAG ingestion manifest" in mod.SAFE_CLAIM


def test_banned_phrases_tuple():
    mod = _load_mod()
    assert isinstance(mod.BANNED_PHRASES, tuple)
    assert len(mod.BANNED_PHRASES) >= 16


def test_create_mock_fixtures_returns_dir(tmp_path):
    mod = _load_mod()
    root = mod.create_mock_fixtures(tmp_path)
    assert root.is_dir()
    assert (root / "report.md").exists()
    assert (root / "omega_event.json").exists()


def test_scan_mock_fixtures(tmp_path):
    mod = _load_mod()
    root = mod.create_mock_fixtures(tmp_path)
    records = mod.scan_artifacts(root)
    assert len(records) > 0


def test_write_outputs_creates_all_files(tmp_path):
    mod = _load_mod()
    out = tmp_path / "out"
    mod.write_outputs([], out, tmp_path, datetime.datetime.now(datetime.timezone.utc).isoformat())
    required = [
        "rag_artifact_manifest.jsonl",
        "rag_artifact_manifest.json",
        "rag_index_priority.csv",
        "rag_ingestion_plan.md",
        "quarantined_artifacts.json",
        "omega_event.json",
        "report.md",
    ]
    for name in required:
        assert (out / name).exists(), f"missing: {name}"


def test_scan_claim_safety_safe():
    mod = _load_mod()
    status, found = mod.scan_claim_safety("all metrics are candidate proxies only")
    assert status == "safe"
    assert found == []


def test_scan_claim_safety_quarantine():
    mod = _load_mod()
    # Contains a banned phrase in test content only
    status, found = mod.scan_claim_safety("eeg proves consciousness of the subject")
    assert status == "quarantined_banned_phrase"
    assert "eeg proves consciousness" in found


def test_make_artifact_id_deterministic(tmp_path):
    mod = _load_mod()
    p = tmp_path / "file.md"
    p.write_text("x")
    id1 = mod.make_artifact_id(p, tmp_path)
    id2 = mod.make_artifact_id(p, tmp_path)
    assert id1 == id2
    assert id1.startswith("art_")
