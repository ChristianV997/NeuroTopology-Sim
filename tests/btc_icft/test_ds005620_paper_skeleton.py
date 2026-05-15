"""Tests for DS005620 paper skeleton generator (P18.2)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "generate_ds005620_paper_skeleton",
    Path(__file__).parent.parent.parent / "tools" / "generate_ds005620_paper_skeleton.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
generate_paper_skeleton = _mod.generate_paper_skeleton


_BANNED = [
    "proves consciousness", "consciousness proven", "soul proven",
    "afterlife proven", "liberation detected", "ontology solved",
    "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness",
]


def _setup_evidence(tmp_path: Path) -> Path:
    evidence = {
        "dataset_id": "DS005620",
        "mode": "mock_e2e",
        "benchmark_completed": True,
        "stage_outcomes": {"p12_succeeded": True, "p13_succeeded": True, "p11_succeeded": True},
        "omega_invariants": {
            "labels_inferred": False,
            "targets_fabricated": False,
            "source_contracts_modified": False,
            "legacy_mt_real_modified": False,
            "contracts_activated_by_executor": False,
            "p11_promotion_gate_modified": False,
            "consciousness_claims_made": False,
        },
        "promotion_decision": "engineering_runtime_validated_only",
        "safe_claim": "test safe claim",
    }
    p = tmp_path / "evidence_packet.json"
    p.write_text(json.dumps(evidence), encoding="utf-8")
    return p


def test_paper_skeleton_files_created(tmp_path):
    evidence_path = _setup_evidence(tmp_path)
    artifacts = generate_paper_skeleton(str(evidence_path), str(tmp_path / "out"))
    assert Path(artifacts["paper_skeleton.md"]).exists()
    assert Path(artifacts["reviewer_checklist.md"]).exists()
    assert Path(artifacts["negative_space_disclaimers.md"]).exists()


def test_paper_skeleton_no_banned_phrases(tmp_path):
    evidence_path = _setup_evidence(tmp_path)
    out = tmp_path / "out"
    artifacts = generate_paper_skeleton(str(evidence_path), str(out))
    for fname in ("paper_skeleton.md", "reviewer_checklist.md", "negative_space_disclaimers.md"):
        text = Path(artifacts[fname]).read_text(encoding="utf-8").lower()
        for phrase in _BANNED:
            assert phrase not in text, f"banned phrase {phrase!r} found in {fname}"


def test_reviewer_checklist_has_omega_checks(tmp_path):
    evidence_path = _setup_evidence(tmp_path)
    artifacts = generate_paper_skeleton(str(evidence_path), str(tmp_path / "out"))
    checklist = Path(artifacts["reviewer_checklist.md"]).read_text(encoding="utf-8")
    assert "labels_inferred" in checklist
    assert "consciousness_claims_made" in checklist


def test_negative_space_disclaimers_has_non_claims(tmp_path):
    evidence_path = _setup_evidence(tmp_path)
    artifacts = generate_paper_skeleton(str(evidence_path), str(tmp_path / "out"))
    text = Path(artifacts["negative_space_disclaimers.md"]).read_text(encoding="utf-8")
    assert "engineering" in text.lower()
    assert "metaphysical" in text.lower()


def _setup_ontology_root(tmp_path: Path) -> Path:
    ont = tmp_path / "ontology"
    ont.mkdir(exist_ok=True)
    (ont / "ontology_claim_evaluation.json").write_text(
        json.dumps({
            "max_claim_scope": "engineering_runtime",
            "promotion_state": "engineering_validated",
            "ontology_claim_status": "ontology_quarantined",
            "claims": [],
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
        json.dumps({"bridge_statuses": []}), encoding="utf-8",
    )
    (ont / "claim_scope_matrix.json").write_text(
        json.dumps({
            "engineering_runtime": {"allowed": True, "max_state": "engineering_validated", "blockers": []},
        }),
        encoding="utf-8",
    )
    return ont


def test_paper_skeleton_includes_ontology_section(tmp_path):
    ev_path = _setup_evidence(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = generate_paper_skeleton(str(ev_path), str(tmp_path / "out"), ontology_root=str(ont))
    skeleton = Path(artifacts["paper_skeleton.md"]).read_text(encoding="utf-8")
    assert "## Ontology and Claim Scope" in skeleton


def test_reviewer_checklist_includes_ontology_review(tmp_path):
    ev_path = _setup_evidence(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = generate_paper_skeleton(str(ev_path), str(tmp_path / "out"), ontology_root=str(ont))
    checklist = Path(artifacts["reviewer_checklist.md"]).read_text(encoding="utf-8")
    assert "## Ontology Review Checklist" in checklist
    assert "ontology candidates remain quarantined" in checklist.lower()


def test_negative_space_disclaimers_include_quarantine(tmp_path):
    ev_path = _setup_evidence(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = generate_paper_skeleton(str(ev_path), str(tmp_path / "out"), ontology_root=str(ont))
    disclaimers = Path(artifacts["negative_space_disclaimers.md"]).read_text(encoding="utf-8")
    assert "quarantined" in disclaimers.lower()
    assert "mock" in disclaimers.lower()


def test_generated_paper_artifacts_avoid_banned_phrases(tmp_path):
    ev_path = _setup_evidence(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = generate_paper_skeleton(str(ev_path), str(tmp_path / "out"), ontology_root=str(ont))
    for name, path in artifacts.items():
        text = Path(path).read_text(encoding="utf-8").lower()
        for phrase in _BANNED:
            assert phrase not in text, f"banned phrase in {name}: {phrase!r}"


def test_require_ontology_raises_when_missing(tmp_path):
    ev_path = _setup_evidence(tmp_path)
    with pytest.raises(SystemExit):
        generate_paper_skeleton(str(ev_path), str(tmp_path / "out"),
                                ontology_root=str(tmp_path / "missing"),
                                require_ontology=True)
