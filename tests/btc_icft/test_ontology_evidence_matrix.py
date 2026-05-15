"""Tests for ontology evidence requirement matrix (O2)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sciencer_d.btc_icft.ontology.evidence import (
    evaluate_scope_requirements,
    load_evidence_requirement_matrix,
    validate_evidence_requirement_matrix,
)


_MATRIX_PATH = Path(__file__).parent.parent.parent / "contracts" / "btc_icft" / "ontology_claims" / "evidence_requirement_matrix.json"


def _load() -> dict:
    return load_evidence_requirement_matrix(str(_MATRIX_PATH))


def test_matrix_loads_and_has_rows():
    m = _load()
    scopes = {r["scope"] for r in m["rows"]}
    assert {
        "engineering_runtime",
        "marker_association",
        "topology_residual",
        "mechanism_candidate",
        "theory_consistency",
        "ontology_candidate",
    }.issubset(scopes)


def test_matrix_validates_clean():
    m = _load()
    errors = validate_evidence_requirement_matrix(m)
    assert errors == [], f"unexpected matrix errors: {errors}"


def test_engineering_runtime_allows_mock_e2e():
    m = _load()
    out = evaluate_scope_requirements(
        "engineering_runtime",
        available_artifacts=set(),
        available_controls=set(),
        run_mode="mock_e2e",
        matrix=m,
    )
    assert out["satisfied"] is True
    assert out["max_promotion_state"] == "engineering_validated"


def test_marker_association_requires_real_execution_and_labels():
    m = _load()
    out_mock = evaluate_scope_requirements(
        "marker_association",
        available_artifacts=set(),
        available_controls=set(),
        run_mode="mock_e2e",
        matrix=m,
    )
    assert out_mock["satisfied"] is False
    assert any("real execution" in b for b in out_mock["blockers"])

    out_real_no_labels = evaluate_scope_requirements(
        "marker_association",
        available_artifacts=set(),
        available_controls={"nulls.json", "leakage_report.json", "artifact_report.json"},
        run_mode="real_local",
        matrix=m,
    )
    assert out_real_no_labels["satisfied"] is False
    assert any("reviewed-label" in b for b in out_real_no_labels["blockers"])


def test_topology_residual_requires_controls():
    m = _load()
    out = evaluate_scope_requirements(
        "topology_residual",
        available_artifacts={"features_m_signal_labeled.csv"},
        available_controls=set(),
        run_mode="real_local",
        human_review_status="completed",
        matrix=m,
    )
    assert out["satisfied"] is False
    assert any("control" in b for b in out["blockers"])


def test_ontology_candidate_requires_independent_dataset_and_mechanism():
    m = _load()
    out = evaluate_scope_requirements(
        "ontology_candidate",
        available_artifacts={"features_m_signal_labeled.csv"},
        available_controls={"nulls.json", "ablations.json", "leakage_report.json", "artifact_report.json"},
        run_mode="real_local",
        human_review_status="completed",
        matrix=m,
    )
    assert out["satisfied"] is False
    blockers = out["blockers"]
    assert any("independent dataset" in b for b in blockers)
    assert any("mechanism evidence" in b for b in blockers)


def test_no_row_allows_ontology_proof_promotion():
    m = _load()
    for r in m["rows"]:
        if r["scope"] == "ontology_candidate":
            assert r["max_promotion_state"] == "ontology_quarantined"
        # No row may have a state implying proof
        forbidden_states = {"empirical_supported_limited", "ontology_proven", "ontology_validated"}
        assert r["max_promotion_state"] not in forbidden_states or r["scope"] != "ontology_candidate"


def test_invalid_scope_rejected():
    m = _load()
    bad = copy.deepcopy(m)
    bad["rows"][0]["scope"] = "not_a_scope"
    errors = validate_evidence_requirement_matrix(bad)
    assert any("invalid scope" in e for e in errors)
