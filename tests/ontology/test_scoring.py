from __future__ import annotations

import pytest

from sciencer_d.ontology.scoring import (
    apply_status_ceiling,
    classify_score,
    composite_score,
)


def test_composite_uses_issue_defined_weights():
    values = {
        "empirical_support": 4,
        "phenomenological_depth": 3,
        "metaphysical_coherence": 2,
        "falsifiability": 4,
        "btc_icft_relevance": 4,
        "risk_of_overclaim": 1,
    }
    assert composite_score(values) == pytest.approx(3.25)


def test_empirical_gate_requires_support_and_falsifiability():
    strong = {
        "empirical_support": 5,
        "phenomenological_depth": 5,
        "metaphysical_coherence": 5,
        "falsifiability": 5,
        "btc_icft_relevance": 5,
        "risk_of_overclaim": 0,
    }
    assert classify_score(strong) == "O-A"
    assert classify_score({**strong, "empirical_support": 3}) == "O-B"
    assert classify_score({**strong, "falsifiability": 2}) == "O-C"


def test_coherence_alone_cannot_promote_claim():
    coherence_only = {"metaphysical_coherence": 5}
    assert classify_score(coherence_only) == "O-C"


def test_firewall_or_dominant_overclaim_risk_rejects_claim():
    assert classify_score({}, firewall_rejected=True) == "O-X"
    assert classify_score({"risk_of_overclaim": 5}) == "O-X"


def test_sensitive_claim_status_ceilings_are_enforced():
    assert apply_status_ceiling("O5_SOUL_IDENTITY_INVARIANT", "O-A") == (
        "O-C",
        "policy_ceiling:O-C",
    )
    assert apply_status_ceiling("O7_FIELD_CONSCIOUSNESS", "O-A") == (
        "O-B",
        "policy_ceiling:O-B",
    )


def test_out_of_range_score_is_rejected():
    with pytest.raises(ValueError, match="empirical_support"):
        composite_score({"empirical_support": 5.1})
