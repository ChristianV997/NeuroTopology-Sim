"""Tests for DS005620 evidence packet exporter (P18.2 / O4)."""
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

_BANNED = [
    "proves consciousness", "consciousness proven", "soul proven",
    "afterlife proven", "liberation detected", "ontology solved",
    "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness",
]


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


def _setup_ontology_root(tmp_path: Path) -> Path:
    """Create a minimal ontology evaluation output directory."""
    ont = tmp_path / "ontology"
    ont.mkdir()
    (ont / "ontology_claim_evaluation.json").write_text(
        json.dumps({
            "max_claim_scope": "engineering_runtime",
            "promotion_state": "engineering_validated",
            "ontology_claim_status": "ontology_quarantined",
            "claims": [{"claim_id": "M1", "allowed": False, "blockers": ["b"]}],
            "blockers": ["run_mode_is_mock_e2e"],
            "safe_claim": "Ontology evaluation constrains claim scopes.",
        }),
        encoding="utf-8",
    )
    (ont / "ontology_promotion_decision.json").write_text(
        json.dumps({
            "ontology_promotion": False,
            "empirical_marker_promotion": False,
            "empirical_topology_promotion": False,
            "mechanism_promotion": False,
            "metaphysical_promotion": False,
        }),
        encoding="utf-8",
    )
    (ont / "bridge_claim_status.json").write_text(
        json.dumps({"bridge_statuses": [{"bridge_id": "B1", "status": "blocked_pending_real_execution"}]}),
        encoding="utf-8",
    )
    return ont


# Original tests (preserved)

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
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    md_text = Path(artifacts["evidence_packet.md"]).read_text(encoding="utf-8").lower()
    for phrase in _BANNED:
        assert phrase not in md_text, f"banned phrase found in evidence_packet.md: {phrase!r}"


# New O4 tests

def test_evidence_packet_includes_ontology_summary_when_present(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    assert "ontology_summary" in packet
    assert packet["ontology_summary"]["ontology_available"] is True
    assert packet["ontology_summary"]["max_claim_scope"] == "engineering_runtime"


def test_evidence_packet_ontology_summary_not_available_when_missing(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"),
                                      ontology_root=str(tmp_path / "missing"))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    assert packet["ontology_summary"]["ontology_available"] is False
    assert "ontology_evaluation_missing" in packet.get("warnings", [])


def test_evidence_packet_require_ontology_raises_when_missing(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    with pytest.raises(SystemExit):
        build_evidence_packet(str(manifest_path), str(tmp_path / "out"),
                              ontology_root=str(tmp_path / "missing"),
                              require_ontology=True)


def test_notion_payload_includes_ontology_fields(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    notion = json.loads(Path(artifacts["notion_import_payload.json"]).read_text(encoding="utf-8"))
    assert "ontology_claim_scope" in notion
    assert "ontology_promotion_state" in notion
    assert "ontology_status" in notion
    assert notion["ontology_status"] == "ontology_quarantined"


def test_evidence_markdown_includes_ontology_section(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    md = Path(artifacts["evidence_packet.md"]).read_text(encoding="utf-8")
    assert "## Ontology Claim Scope" in md


def test_mock_evidence_packet_does_not_promote_empirical_claims(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    summary = packet["ontology_summary"]
    assert summary["empirical_marker_promotion"] is False
    assert summary["empirical_topology_promotion"] is False
    assert summary["mechanism_promotion"] is False
    assert summary["metaphysical_promotion"] is False
    assert summary["ontology_promotion"] is False


def test_claim_scope_dict_in_packet(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    scope = packet.get("claim_scope", {})
    assert scope.get("engineering_runtime") is True
    assert scope.get("ontology_candidate") is False
