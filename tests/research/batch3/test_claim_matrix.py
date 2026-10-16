"""Deterministic schema and uniqueness checks for the Batch 3 theory-to-measurement claim matrix.

Does not compute scientific evidence. Does not promote any claim.
"""

import json
from pathlib import Path

import pytest

MATRIX_PATH = Path(__file__).resolve().parents[3] / "reports" / "batch3" / "grok_chat_a" / "claim_matrix.json"

REQUIRED_CLAIM_FIELDS = {
    "claim_id",
    "statement",
    "category",
    "strongest_primary_source",
    "assumptions",
    "counterevidence_or_uncertainty",
    "alternative_explanations",
    "falsifiable_prediction_or_disconfirming_test",
    "evidence_limit",
}

ALLOWED_CATEGORIES = {
    "formal_mathematical_identity",
    "computational_analogy_or_borrowed_operator",
    "operational_measurement_claim",
    "empirical_claim",
    "phenomenological_or_mechanistic_interpretation",
}


def load_matrix():
    text = MATRIX_PATH.read_text(encoding="utf-8")
    data = json.loads(text)
    # Finite JSON check
    json.dumps(data, allow_nan=False)
    return data


def test_matrix_exists_and_parses():
    assert MATRIX_PATH.is_file()
    data = load_matrix()
    assert "claims" in data
    assert isinstance(data["claims"], list)
    assert len(data["claims"]) >= 1


def test_claim_id_uniqueness():
    data = load_matrix()
    ids = [c["claim_id"] for c in data["claims"]]
    assert len(ids) == len(set(ids)), "Duplicate claim_id found"


def test_required_fields_and_categories():
    data = load_matrix()
    for claim in data["claims"]:
        missing = REQUIRED_CLAIM_FIELDS - set(claim.keys())
        assert not missing, f"Missing fields in {claim.get('claim_id')}: {missing}"
        assert claim["category"] in ALLOWED_CATEGORIES
        assert isinstance(claim["statement"], str) and claim["statement"]
        assert isinstance(claim["assumptions"], list)
        assert isinstance(claim["alternative_explanations"], list)
        src = claim["strongest_primary_source"]
        assert "citation" in src
        assert "direct_support" in src
        assert isinstance(src["direct_support"], bool)


def test_no_validated_status():
    data = load_matrix()
    # Ensure no top-level or claim-level promotion key
    assert "reviewer_state" not in data
    for claim in data["claims"]:
        assert "reviewer_state" not in claim
        assert claim.get("status", "").upper() != "VALIDATED"
    # Non-promotion statement present
    assert "does not introduce VALIDATED" in data.get("non_promotion", "") or \
           "does not introduce VALIDATED" in json.dumps(data)
