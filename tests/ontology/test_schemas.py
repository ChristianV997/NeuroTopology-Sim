from __future__ import annotations

import pytest

from sciencer_d.ontology.schemas import (
    OntologyClaim,
    OntologyClaimLink,
    OntologyFalsifier,
    OntologyScore,
)


def test_claim_schema_round_trips():
    claim = OntologyClaim.from_dict(
        {
            "claim_id": "O_TEST",
            "title": "Test claim",
            "statement": "A bounded hypothesis.",
            "status": "O-C",
            "ladder_level": "H4",
            "score_inputs": {"empirical_support": 1},
        }
    )
    assert claim.to_dict()["claim_id"] == "O_TEST"
    assert claim.score_inputs == {"empirical_support": 1.0}


def test_claim_schema_rejects_unknown_status():
    with pytest.raises(ValueError, match="Unknown claim status"):
        OntologyClaim.from_dict(
            {
                "claim_id": "O_TEST",
                "title": "Test",
                "statement": "Test",
                "status": "promoted",
                "ladder_level": "H4",
            }
        )


def test_claim_link_enforces_direction_and_strength():
    base = {
        "claim_id": "O_TEST",
        "paper_id": "P_TEST",
        "support_direction": "supports",
        "strength": 3,
        "notes": "Bounded support",
    }
    assert OntologyClaimLink.from_dict(base).strength == 3
    with pytest.raises(ValueError, match="strength"):
        OntologyClaimLink.from_dict({**base, "strength": 6})
    with pytest.raises(ValueError, match="support direction"):
        OntologyClaimLink.from_dict({**base, "support_direction": "proves"})


def test_score_schema_enforces_zero_to_five_dimensions():
    values = {
        "claim_id": "O_TEST",
        "empirical_support": 1,
        "phenomenological_depth": 1,
        "metaphysical_coherence": 1,
        "falsifiability": 1,
        "btc_icft_relevance": 1,
        "risk_of_overclaim": 1,
        "composite": 0.75,
        "status": "O-C",
    }
    assert OntologyScore(**values).status == "O-C"
    with pytest.raises(ValueError, match="empirical_support"):
        OntologyScore(**{**values, "empirical_support": -1})


def test_falsifier_schema_rejects_unknown_severity():
    with pytest.raises(ValueError, match="severity"):
        OntologyFalsifier.from_dict(
            {
                "claim_id": "O_TEST",
                "falsifier_id": "F_TEST",
                "description": "Failure",
                "required_test": "Test",
                "severity": "absolute",
            }
        )
