"""Tests for DS005620 ontology evaluator (O3)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from sciencer_d.btc_icft.ontology.ds005620_evaluator import (
    evaluate_ds005620_ontology_claims,
    inspect_available_artifacts,
    load_controls_if_present,
    run_evaluation,
)
from sciencer_d.btc_icft.ontology.safe_language import (
    FORBIDDEN_ONTOLOGY_PHRASES,
    validate_json_safe_text,
    validate_safe_text,
)
from sciencer_d.btc_icft.ontology.schema import ClaimScope, PromotionState


_REPO_ROOT = Path(__file__).parent.parent.parent
_BRIDGE = _REPO_ROOT / "configs" / "btc_icft" / "ontology_bridge_registry.json"
_MATRIX = _REPO_ROOT / "contracts" / "btc_icft" / "ontology_claims" / "evidence_requirement_matrix.json"


_OMEGA_BASE = {
    "labels_inferred": False,
    "targets_fabricated": False,
    "source_contracts_modified": False,
    "legacy_mt_real_modified": False,
    "contracts_activated_by_executor": False,
    "p11_promotion_gate_modified": False,
    "consciousness_claims_made": False,
}


def _make_mock_execution_root(tmp_path: Path) -> Path:
    root = tmp_path / "exec_mock"
    root.mkdir()
    (root / "ds005620_real_benchmark_execution.json").write_text(
        json.dumps({
            "dataset_id": "DS005620",
            "mode": "mock_e2e",
            "benchmark_completed": True,
            "p12_succeeded": True,
            "p13_succeeded": True,
            "p11_succeeded": True,
        }),
        encoding="utf-8",
    )
    (root / "omega_event.json").write_text(json.dumps(_OMEGA_BASE), encoding="utf-8")
    return root


def _make_real_execution_root(tmp_path: Path, *, with_labels: bool = True) -> Path:
    root = tmp_path / "exec_real"
    root.mkdir()
    (root / "ds005620_real_benchmark_execution.json").write_text(
        json.dumps({
            "dataset_id": "DS005620",
            "mode": "real_local",
            "benchmark_completed": True,
            "p12_succeeded": True,
            "p13_succeeded": True,
            "p11_succeeded": True,
        }),
        encoding="utf-8",
    )
    (root / "omega_event.json").write_text(json.dumps(_OMEGA_BASE), encoding="utf-8")
    (root / "metrics_signal_mt.json").write_text("{}", encoding="utf-8")
    if with_labels:
        (root / "features_m_signal_labeled.csv").write_text("", encoding="utf-8")
    return root


def _make_controls_root(tmp_path: Path, complete: bool = True) -> Path:
    cdir = tmp_path / "controls"
    cdir.mkdir()
    files = ["nulls.json", "ablations.json", "leakage_report.json", "artifact_report.json"]
    if not complete:
        files = files[:2]
    for f in files:
        (cdir / f).write_text("{}", encoding="utf-8")
    return cdir


def test_mock_e2e_evaluation_writes_all_outputs(tmp_path):
    exec_root = _make_mock_execution_root(tmp_path)
    out_dir = tmp_path / "out"
    paths = run_evaluation(
        execution_root=str(exec_root),
        controls_root=None,
        out_dir=str(out_dir),
        bridge_registry_path=str(_BRIDGE),
        evidence_matrix_path=str(_MATRIX),
    )
    expected = {
        "ontology_claim_evaluation.json",
        "claim_scope_matrix.json",
        "bridge_claim_status.json",
        "falsifier_status.json",
        "alternative_explanations.json",
        "ontology_promotion_decision.json",
        "omega_event.json",
        "report.md",
    }
    assert expected.issubset(set(paths.keys()))
    for p in paths.values():
        assert Path(p).exists()


def test_mock_max_claim_scope_is_engineering_runtime(tmp_path):
    exec_root = _make_mock_execution_root(tmp_path)
    out_dir = tmp_path / "out"
    run_evaluation(
        execution_root=str(exec_root),
        controls_root=None,
        out_dir=str(out_dir),
        bridge_registry_path=str(_BRIDGE),
        evidence_matrix_path=str(_MATRIX),
    )
    ev = json.loads((out_dir / "ontology_claim_evaluation.json").read_text(encoding="utf-8"))
    assert ev["max_claim_scope"] == ClaimScope.ENGINEERING_RUNTIME
    assert ev["promotion_state"] == PromotionState.ENGINEERING_VALIDATED


def test_mock_ontology_status_is_quarantined(tmp_path):
    exec_root = _make_mock_execution_root(tmp_path)
    out_dir = tmp_path / "out"
    run_evaluation(
        execution_root=str(exec_root),
        controls_root=None,
        out_dir=str(out_dir),
        bridge_registry_path=str(_BRIDGE),
        evidence_matrix_path=str(_MATRIX),
    )
    ev = json.loads((out_dir / "ontology_claim_evaluation.json").read_text(encoding="utf-8"))
    assert ev["ontology_claim_status"] == PromotionState.ONTOLOGY_QUARANTINED


def test_mock_mt_empirical_claims_blocked(tmp_path):
    exec_root = _make_mock_execution_root(tmp_path)
    out_dir = tmp_path / "out"
    run_evaluation(
        execution_root=str(exec_root),
        controls_root=None,
        out_dir=str(out_dir),
        bridge_registry_path=str(_BRIDGE),
        evidence_matrix_path=str(_MATRIX),
    )
    ev = json.loads((out_dir / "ontology_claim_evaluation.json").read_text(encoding="utf-8"))
    claims_by_id = {c["claim_id"]: c for c in ev["claims"]}
    assert claims_by_id["M1"]["allowed"] is False
    assert claims_by_id["T1"]["allowed"] is False
    assert any("real_execution" in b for b in claims_by_id["M1"]["blockers"])


def test_missing_controls_block_topology_residual(tmp_path):
    exec_root = _make_real_execution_root(tmp_path, with_labels=True)
    controls = _make_controls_root(tmp_path, complete=False)
    out_dir = tmp_path / "out"
    run_evaluation(
        execution_root=str(exec_root),
        controls_root=str(controls),
        out_dir=str(out_dir),
        bridge_registry_path=str(_BRIDGE),
        evidence_matrix_path=str(_MATRIX),
        run_mode_override="real_local",
        human_review_completed=True,
    )
    ev = json.loads((out_dir / "ontology_claim_evaluation.json").read_text(encoding="utf-8"))
    assert ev["max_claim_scope"] != ClaimScope.TOPOLOGY_RESIDUAL
    assert ev["promotion_state"] == PromotionState.BLOCKED_PENDING_CONTROLS


def test_real_execution_without_controls_blocks_empirical_promotion(tmp_path):
    exec_root = _make_real_execution_root(tmp_path, with_labels=False)
    out_dir = tmp_path / "out"
    run_evaluation(
        execution_root=str(exec_root),
        controls_root=None,
        out_dir=str(out_dir),
        bridge_registry_path=str(_BRIDGE),
        evidence_matrix_path=str(_MATRIX),
        run_mode_override="real_local",
    )
    ev = json.loads((out_dir / "ontology_claim_evaluation.json").read_text(encoding="utf-8"))
    assert ev["promotion_state"] == PromotionState.BLOCKED_PENDING_REAL_EXECUTION


def test_real_plus_controls_allows_mt_but_keeps_o_quarantined(tmp_path):
    exec_root = _make_real_execution_root(tmp_path, with_labels=True)
    controls = _make_controls_root(tmp_path, complete=True)
    out_dir = tmp_path / "out"
    run_evaluation(
        execution_root=str(exec_root),
        controls_root=str(controls),
        out_dir=str(out_dir),
        bridge_registry_path=str(_BRIDGE),
        evidence_matrix_path=str(_MATRIX),
        run_mode_override="real_local",
        human_review_completed=True,
    )
    ev = json.loads((out_dir / "ontology_claim_evaluation.json").read_text(encoding="utf-8"))
    assert ev["max_claim_scope"] in (
        ClaimScope.MARKER_ASSOCIATION,
        ClaimScope.TOPOLOGY_RESIDUAL,
    )
    assert ev["ontology_claim_status"] == PromotionState.ONTOLOGY_QUARANTINED
    # O claim must remain not allowed regardless
    claims_by_id = {c["claim_id"]: c for c in ev["claims"]}
    assert claims_by_id["O1"]["allowed"] is False


def test_generated_report_contains_no_banned_phrases(tmp_path):
    exec_root = _make_mock_execution_root(tmp_path)
    out_dir = tmp_path / "out"
    run_evaluation(
        execution_root=str(exec_root),
        controls_root=None,
        out_dir=str(out_dir),
        bridge_registry_path=str(_BRIDGE),
        evidence_matrix_path=str(_MATRIX),
    )
    for p in out_dir.iterdir():
        text = p.read_text(encoding="utf-8")
        hits = validate_safe_text(text)
        assert hits == [], f"banned phrase(s) in {p.name}: {hits}"


def test_omega_event_overclaim_invariants_false(tmp_path):
    exec_root = _make_mock_execution_root(tmp_path)
    out_dir = tmp_path / "out"
    run_evaluation(
        execution_root=str(exec_root),
        controls_root=None,
        out_dir=str(out_dir),
        bridge_registry_path=str(_BRIDGE),
        evidence_matrix_path=str(_MATRIX),
    )
    omega = json.loads((out_dir / "omega_event.json").read_text(encoding="utf-8"))
    inv = omega["omega_invariants"]
    for key in (
        "labels_inferred", "targets_fabricated", "source_contracts_modified",
        "legacy_mt_real_modified", "contracts_activated_by_executor",
        "p11_promotion_gate_modified", "consciousness_claims_made",
        "ontology_promotion_attempted", "metaphysical_claim_made",
        "empirical_promotion_from_mock",
    ):
        assert inv[key] is False, f"omega invariant {key} should be false"


def test_makefile_contains_ontology_targets():
    mk = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "ds005620-ontology-eval-mock:" in mk
    assert "ds005620-ontology-check:" in mk


def test_inspect_available_artifacts_walks_subdirs(tmp_path):
    root = tmp_path / "exec"
    sub = root / "stage_outputs" / "p11"
    sub.mkdir(parents=True)
    (sub / "metrics_signal_mt.json").write_text("{}", encoding="utf-8")
    (root / "features_m_signal_labeled.csv").write_text("", encoding="utf-8")
    arts = inspect_available_artifacts(root)
    assert "metrics_signal_mt.json" in arts
    assert "features_m_signal_labeled.csv" in arts


def test_promotion_decision_never_marks_ontology_promotion(tmp_path):
    exec_root = _make_real_execution_root(tmp_path, with_labels=True)
    controls = _make_controls_root(tmp_path, complete=True)
    out_dir = tmp_path / "out"
    run_evaluation(
        execution_root=str(exec_root),
        controls_root=str(controls),
        out_dir=str(out_dir),
        bridge_registry_path=str(_BRIDGE),
        evidence_matrix_path=str(_MATRIX),
        run_mode_override="real_local",
        independent_dataset_present=True,
        independent_mechanism_evidence_present=True,
        human_review_completed=True,
    )
    pd = json.loads((out_dir / "ontology_promotion_decision.json").read_text(encoding="utf-8"))
    assert pd["ontology_promotion"] is False
    assert pd["metaphysical_promotion"] is False
    assert pd["ontology_claim_status"] == PromotionState.ONTOLOGY_QUARANTINED
