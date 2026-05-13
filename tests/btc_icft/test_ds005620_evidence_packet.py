"""Tests for DS005620 evidence packet exporter (P18.2)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "export_ds005620_evidence_packet",
    Path(__file__).parent.parent.parent / "tools" / "export_ds005620_evidence_packet.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
build_evidence_packet = _mod.build_evidence_packet


def _setup_manifest(tmp_path: Path) -> Path:
    root = tmp_path / "execution"
    root.mkdir()
    (root / "ds005620_real_benchmark_execution.json").write_text(
        json.dumps({
            "benchmark_completed": True,
            "mode": "mock_e2e",
            "p12_succeeded": True,
            "p13_succeeded": True,
            "p11_succeeded": True,
        }),
        encoding="utf-8",
    )
    (root / "omega_event.json").write_text(
        json.dumps({
            "labels_inferred": False,
            "targets_fabricated": False,
            "source_contracts_modified": False,
            "legacy_mt_real_modified": False,
            "contracts_activated_by_executor": False,
            "p11_promotion_gate_modified": False,
            "consciousness_claims_made": False,
        }),
        encoding="utf-8",
    )
    manifest = {
        "dataset_id": "DS005620",
        "artifact_root": str(root),
        "artifact_count": 2,
        "artifacts": [],
        "safe_claim": "test",
    }
    manifest_path = root / "artifact_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_evidence_packet_created(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    assert Path(artifacts["evidence_packet.json"]).exists()
    assert Path(artifacts["evidence_packet.md"]).exists()
    assert Path(artifacts["notion_import_payload.json"]).exists()


def test_evidence_packet_promotion_decision(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    assert packet["promotion_decision"] == "engineering_runtime_validated_only"


def test_evidence_packet_all_omega_false(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    assert packet["all_omega_invariants_false"] is True


def test_evidence_packet_no_banned_phrases(tmp_path):
    _BANNED = [
        "proves consciousness", "consciousness proven", "soul proven",
        "afterlife proven", "liberation detected", "ontology solved",
        "ultimate reality", "q equals self", "q equals soul",
        "q_abs equals suffering", "f_dress equals karma",
        "sedated implies no_experience", "unresponsive implies unconscious",
        "topology proves liberation", "eeg proves consciousness",
    ]
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    md_text = Path(artifacts["evidence_packet.md"]).read_text(encoding="utf-8").lower()
    for phrase in _BANNED:
        assert phrase not in md_text, f"banned phrase found in evidence_packet.md: {phrase!r}"
