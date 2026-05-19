"""Tests for ontology artifact reader (O4 / P24.1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sciencer_d.btc_icft.ontology.artifact_reader import (
    load_bridge_claim_status,
    load_claim_scope_matrix,
    load_ontology_evaluation,
    load_ontology_promotion_decision,
    summarize_ontology_for_markdown,
    summarize_ontology_for_packet,
)
from sciencer_d.btc_icft.ontology.safe_language import FORBIDDEN_ONTOLOGY_PHRASES


def _make_ontology_root(tmp_path: Path) -> Path:
    root = tmp_path / "ontology_eval"
    root.mkdir()

    (root / "ontology_claim_evaluation.json").write_text(
        json.dumps({
            "dataset_id": "DS005620",
            "run_mode": "mock_e2e",
            "max_claim_scope": "engineering_runtime",
            "promotion_state": "engineering_validated",
            "ontology_claim_status": "ontology_quarantined",
            "claims": [
                {"claim_id": "M1", "allowed": False, "blockers": ["blocked_pending_real_execution"]},
                {"claim_id": "T1", "allowed": False, "blockers": ["blocked_pending_real_execution"]},
                {"claim_id": "O1", "allowed": False, "blockers": ["blocked_pending_real_execution"]},
            ],
            "blockers": ["run_mode_is_mock_e2e"],
            "safe_claim": "Ontology evaluation constrains benchmark outputs to explicit claim scopes.",
            "forbidden_claims": [],
            "omega_invariants": {},
        }),
        encoding="utf-8",
    )
    (root / "ontology_promotion_decision.json").write_text(
        json.dumps({
            "ontology_promotion": False,
            "empirical_marker_promotion": False,
            "empirical_topology_promotion": False,
            "mechanism_promotion": False,
            "metaphysical_promotion": False,
            "ontology_claim_status": "ontology_quarantined",
        }),
        encoding="utf-8",
    )
    (root / "bridge_claim_status.json").write_text(
        json.dumps({
            "bridge_statuses": [
                {"bridge_id": "B1", "status": "blocked_pending_real_execution"},
                {"bridge_id": "B2", "status": "blocked_pending_real_execution"},
                {"bridge_id": "B4", "status": "quarantined"},
                {"bridge_id": "B6", "status": "quarantined"},
            ]
        }),
        encoding="utf-8",
    )
    (root / "claim_scope_matrix.json").write_text(
        json.dumps({
            "engineering_runtime": {"allowed": True, "max_state": "engineering_validated", "blockers": []},
            "ontology_candidate": {"allowed": False, "max_state": "ontology_quarantined", "blockers": ["mock"]},
        }),
        encoding="utf-8",
    )
    return root


def test_missing_ontology_root_returns_not_available(tmp_path):
    summary = summarize_ontology_for_packet(tmp_path / "nonexistent")
    assert summary["ontology_available"] is False


def test_missing_ontology_root_preserves_safe_defaults(tmp_path):
    summary = summarize_ontology_for_packet(tmp_path / "nonexistent")
    assert summary["max_claim_scope"] == "engineering_runtime"
    assert summary["ontology_claim_status"] == "ontology_quarantined"
    assert summary["ontology_promotion"] is False
    assert summary["metaphysical_promotion"] is False


def test_valid_ontology_root_returns_max_claim_scope(tmp_path):
    root = _make_ontology_root(tmp_path)
    summary = summarize_ontology_for_packet(root)
    assert summary["ontology_available"] is True
    assert summary["max_claim_scope"] == "engineering_runtime"


def test_valid_ontology_root_returns_claim_status(tmp_path):
    root = _make_ontology_root(tmp_path)
    summary = summarize_ontology_for_packet(root)
    assert summary["ontology_claim_status"] == "ontology_quarantined"


def test_bridge_status_counts_computed(tmp_path):
    root = _make_ontology_root(tmp_path)
    summary = summarize_ontology_for_packet(root)
    counts = summary["bridge_status_counts"]
    assert counts.get("blocked_pending_real_execution", 0) == 2
    assert counts.get("quarantined", 0) == 2


def test_markdown_summary_avoids_banned_phrases(tmp_path):
    root = _make_ontology_root(tmp_path)
    md = summarize_ontology_for_markdown(root)
    lower = md.lower()
    for phrase in FORBIDDEN_ONTOLOGY_PHRASES:
        assert phrase not in lower, f"banned phrase found: {phrase!r}"


def test_markdown_summary_not_available_when_missing(tmp_path):
    md = summarize_ontology_for_markdown(tmp_path / "nonexistent")
    assert "not yet available" in md.lower()


def test_load_ontology_evaluation_returns_dict(tmp_path):
    root = _make_ontology_root(tmp_path)
    ev = load_ontology_evaluation(root)
    assert ev["run_mode"] == "mock_e2e"


def test_load_promotion_decision_returns_dict(tmp_path):
    root = _make_ontology_root(tmp_path)
    pd = load_ontology_promotion_decision(root)
    assert pd["ontology_promotion"] is False


def test_load_claim_scope_matrix_returns_dict(tmp_path):
    root = _make_ontology_root(tmp_path)
    m = load_claim_scope_matrix(root)
    assert "engineering_runtime" in m


def test_blocked_claims_list(tmp_path):
    root = _make_ontology_root(tmp_path)
    summary = summarize_ontology_for_packet(root)
    blocked = summary["blocked_claims"]
    assert "M1" in blocked
    assert "T1" in blocked
    assert "O1" in blocked
