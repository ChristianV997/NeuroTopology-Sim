"""Tests for DS005620 artifact manifest builder (P18.2)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "build_ds005620_artifact_manifest",
    Path(__file__).parent.parent.parent / "tools" / "build_ds005620_artifact_manifest.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
build_artifact_manifest = _mod.build_artifact_manifest


def _setup_root(tmp_path: Path) -> Path:
    root = tmp_path / "execution"
    root.mkdir()
    (root / "ds005620_real_benchmark_execution.json").write_text(
        json.dumps({"benchmark_completed": True, "mode": "mock_e2e", "p12_succeeded": True, "p13_succeeded": True, "p11_succeeded": True}),
        encoding="utf-8",
    )
    (root / "report.md").write_text("# Report", encoding="utf-8")
    (root / "omega_event.json").write_text(json.dumps({"labels_inferred": False}), encoding="utf-8")
    return root


def test_manifest_created(tmp_path):
    root = _setup_root(tmp_path)
    manifest_path = build_artifact_manifest(str(root), str(tmp_path / "out"))
    assert Path(manifest_path).exists()


def test_manifest_has_artifacts(tmp_path):
    root = _setup_root(tmp_path)
    manifest_path = build_artifact_manifest(str(root), str(tmp_path / "out"))
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    assert manifest["artifact_count"] >= 3
    assert manifest["dataset_id"] == "DS005620"


def test_manifest_execution_summary(tmp_path):
    root = _setup_root(tmp_path)
    manifest_path = build_artifact_manifest(str(root), str(tmp_path / "out"))
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    assert manifest["execution_summary"]["benchmark_completed"] is True
    assert manifest["execution_summary"]["mode"] == "mock_e2e"


def test_manifest_safe_claim_present(tmp_path):
    root = _setup_root(tmp_path)
    manifest_path = build_artifact_manifest(str(root), str(tmp_path / "out"))
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    assert "safe_claim" in manifest
    assert len(manifest["safe_claim"]) > 10
