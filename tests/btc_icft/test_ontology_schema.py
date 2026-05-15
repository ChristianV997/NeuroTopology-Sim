"""Tests for ontology schema (O1)."""
from __future__ import annotations

import json

from sciencer_d.btc_icft.ontology.schema import (
    CLAIM_SCOPES,
    ONTOLOGY_LAYERS,
    PROMOTION_STATES,
    BridgeClaim,
    ClaimScope,
    OntologyClaim,
    OntologyEvaluationResult,
    OntologyLayer,
    PromotionState,
)


def test_all_ontology_layers_present():
    expected = {
        "D_PHENOMENOLOGY", "M_MARKER", "T_TOPOLOGY", "C_SUBSTRATE",
        "Q_THEORY", "O_ONTOLOGY_CANDIDATE", "OMEGA_GOVERNANCE",
    }
    assert expected.issubset(set(ONTOLOGY_LAYERS))


def test_all_claim_scopes_present():
    expected = {
        "engineering_runtime", "marker_association", "topology_residual",
        "mechanism_candidate", "theory_consistency", "ontology_candidate",
        "blocked_overreach", "rejected",
    }
    assert expected.issubset(set(CLAIM_SCOPES))


def test_all_promotion_states_present():
    expected = {
        "draft", "engineering_validated", "empirical_candidate",
        "empirical_supported_limited", "mechanism_candidate",
        "theory_consistency_only", "ontology_quarantined",
        "blocked_pending_real_execution", "blocked_pending_controls",
        "blocked_pending_review", "blocked_overreach", "rejected",
    }
    assert expected.issubset(set(PROMOTION_STATES))


def test_ontology_claim_serializes():
    c = OntologyClaim(
        claim_id="M1",
        title="Marker association",
        layer=OntologyLayer.M_MARKER,
        scope=ClaimScope.MARKER_ASSOCIATION,
        statement="Markers may associate with reviewed labels.",
        allowed=False,
        promotion_state=PromotionState.BLOCKED_PENDING_REAL_EXECUTION,
    )
    d = c.to_dict()
    assert d["claim_id"] == "M1"
    assert d["layer"] == "M_MARKER"
    assert d["scope"] == "marker_association"
    assert json.dumps(d)  # serializable


def test_bridge_claim_serializes():
    b = BridgeClaim(
        bridge_id="B1",
        source_layer=OntologyLayer.M_MARKER,
        target_layer=OntologyLayer.D_PHENOMENOLOGY,
        allowed_claim="Marker association.",
    )
    d = b.to_dict()
    assert d["bridge_id"] == "B1"
    assert json.dumps(d)


def test_ontology_evaluation_result_serializes():
    r = OntologyEvaluationResult(
        dataset_id="DS005620",
        run_mode="mock_e2e",
        max_claim_scope=ClaimScope.ENGINEERING_RUNTIME,
        promotion_state=PromotionState.ENGINEERING_VALIDATED,
    )
    d = r.to_dict()
    assert d["dataset_id"] == "DS005620"
    assert d["ontology_claim_status"] == "ontology_quarantined"
    assert json.dumps(d)
