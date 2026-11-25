"""Deterministic schema and uniqueness checks for the Batch 3 theory-to-measurement claim matrix.

Does not compute scientific evidence. Does not promote any claim.
"""

import json
from pathlib import Path

MATRIX_PATH = Path(__file__).resolve().parents[3] / "reports" / "batch3" / "grok_chat_a" / "claim_matrix.json"

REQUIRED_CLAIM_FIELDS = {
    "claim_id",
    "review_question",
    "category",
    "sources",
    "assumptions",
    "counterevidence_or_uncertainty",
    "alternative_explanations",
    "falsifiable_prediction_or_disconfirming_test",
    "evidence_limit",
    "review_finding",
}

ALLOWED_CATEGORIES = {
    "formal_mathematical_identity",
    "computational_analogy_or_borrowed_operator",
    "operational_measurement_claim",
    "empirical_claim",
    "phenomenological_or_mechanistic_interpretation",
}

EXPECTED_CATEGORIES = {
    "TTM-001": "computational_analogy_or_borrowed_operator",
    "TTM-002": "operational_measurement_claim",
    "TTM-003": "phenomenological_or_mechanistic_interpretation",
    "TTM-004": "formal_mathematical_identity",
    "TTM-005": "empirical_claim",
}

EXPECTED_DIRECT_SUPPORT = {
    "TTM-001": True,
    "TTM-002": False,
    "TTM-003": False,
    "TTM-004": False,
    "TTM-005": False,
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
        assert isinstance(claim["review_question"], str) and claim["review_question"]
        assert isinstance(claim["assumptions"], list)
        assert isinstance(claim["alternative_explanations"], list)
        assert isinstance(claim["sources"], list) and claim["sources"]
        for source in claim["sources"]:
            assert source["citation"]
            assert source["url"].startswith("https://")
            assert source["source_type"]
            assert isinstance(source["direct_support_for_proposition"], bool)
            assert source["support_scope"]
            assert source["limitations"]


def test_claims_are_explicitly_framed_as_questions_under_review():
    """The matrix records questions, not findings or scientific conclusions."""
    data = load_matrix()
    for claim in data["claims"]:
        question = claim["review_question"].strip()
        assert question.startswith("Question under review:"), claim["claim_id"]
        assert question.endswith("?"), claim["claim_id"]


def test_graph_cycle_rank_is_not_directly_supported_as_spatial_charge():
    """The cited repository contract distinguishes these metric namespaces."""
    data = load_matrix()
    claim = next(c for c in data["claims"] if c["claim_id"] == "TTM-004")
    assert all(not source["direct_support_for_proposition"] for source in claim["sources"])


def test_reviewed_categories_and_source_scope_remain_distinct():
    """Locks the matrix labels; it does not validate scientific truth."""
    data = load_matrix()
    claims = {claim["claim_id"]: claim for claim in data["claims"]}
    assert {key: claim["category"] for key, claim in claims.items()} == EXPECTED_CATEGORIES
    assert len(set(EXPECTED_CATEGORIES.values())) == len(EXPECTED_CATEGORIES)
    for claim_id, expected in EXPECTED_DIRECT_SUPPORT.items():
        sources = claims[claim_id]["sources"]
        assert all(source["direct_support_for_proposition"] is expected for source in sources)


def test_prior_unlinked_gate_count_is_not_reused_as_evidence():
    """An undocumented historical count must not read as a verified result."""
    data = load_matrix()
    note = data["audit_metadata"]["historical_statement_not_relied_on"]
    assert "could not locate a linked run record" in note.lower()
    assert all("20/20" not in claim["review_question"] for claim in data["claims"])


def test_no_validated_status():
    data = load_matrix()
    # Ensure no top-level or claim-level promotion key
    assert "reviewer_state" not in data
    for claim in data["claims"]:
        assert "reviewer_state" not in claim
        assert claim.get("status", "").upper() != "VALIDATED"
    # Review completion is not a scientific promotion or validity decision.
    non_promotion = data.get("non_promotion", "")
    assert "does not emit or assign scientific VALIDATED" in non_promotion
    assert "does not establish any scientific claim" in non_promotion
