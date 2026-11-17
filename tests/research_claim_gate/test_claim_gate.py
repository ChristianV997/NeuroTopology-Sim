"""Contract tests for the deterministic research-claim gate."""

from __future__ import annotations

import json
import math

import pytest

from tools.research_claim_gate.gate import (
    CLAIM_CLASSES,
    DECISION_STATES,
    ClaimGateResult,
    ProvenanceRecord,
    evaluate_claim,
    evaluate_claim_batch,
    serialize_json,
    validate_provenance,
)


GOOD_PROVENANCE = {
    "source_id": "fixture-dataset",
    "source_uri": "local://fixture-dataset",
    "checksum": "a" * 64,
    "acquisition": "fixture",
    "dataset_version": "v1",
    "labels_verified": True,
}


def good_claim(**overrides):
    record = {
        "claim_id": "claim-1",
        "text": "The fixture produced a descriptive empirical association.",
        "claim_class": "descriptive_empirical",
        "evidence_class": "descriptive_empirical",
        "data_mode": "empirical",
        "provenance": GOOD_PROVENANCE,
        "n_tests": 1,
        "multiplicity_correction": "not_needed_single_test",
        "labels_verified": True,
        "null_controls": ["phase_shuffle"],
        "uncertainty": {"ci95": [0.1, 0.2]},
        "effect_size": {"name": "difference", "value": 0.15},
    }
    record.update(overrides)
    return record


def test_all_required_vocabularies_are_closed():
    assert set(CLAIM_CLASSES) == {
        "engineering_fact", "benchmark_result", "synthetic_demonstration", "descriptive_empirical",
        "proxy_inference", "formal_statistical_evidence", "hypothesis", "speculation", "unsupported_claim",
    }
    assert set(DECISION_STATES) == {
        "CLAIM_ADMISSIBLE", "CLAIM_REQUIRES_REVIEW", "CLAIM_DOWNGRADED", "CLAIM_REJECTED",
        "CLAIM_INCOMPLETE", "CLAIM_SYNTHETIC_ONLY", "CLAIM_PROVENANCE_INVALID", "CLAIM_NOT_COMPARABLE",
    }


def test_admissible_engineering_fact():
    result = evaluate_claim({"claim_id": "eng", "text": "The parser is deterministic.", "claim_class": "engineering_fact", "data_mode": "not_applicable"})
    assert result.decision == "CLAIM_ADMISSIBLE"
    assert result.scientific_pass is False


def test_metadata_gate_never_marks_a_claim_scientifically_eligible():
    result = evaluate_claim(good_claim())
    assert result.decision == "CLAIM_ADMISSIBLE"
    assert result.scientific_eligibility is False


def test_requires_review_for_unknown_multiplicity_and_missing_controls():
    result = evaluate_claim(good_claim(n_tests=None, multiplicity_correction=None, null_controls=[], uncertainty=None, effect_size=None))
    assert result.decision == "CLAIM_REQUIRES_REVIEW"
    assert {"UNKNOWN_N_TESTS", "MISSING_NULL_CONTROLS", "MISSING_UNCERTAINTY", "MISSING_EFFECT_SIZE"} <= set(result.reason_codes)


def test_downgrade_proxy_overclaim():
    result = evaluate_claim(good_claim(claim_class="proxy_inference", evidence_class="proxy_inference", evidence_method="aicc_ratio", proxy_status="proxy", text="The proxy K proves a causal mechanism."))
    assert result.decision == "CLAIM_DOWNGRADED"
    assert result.recommended_downgrade_class == "proxy_inference"
    assert "PROXY_NOT_CAUSAL" in result.reason_codes


def test_rejected_unknown_class_and_unsupported_claim():
    unknown = evaluate_claim(good_claim(claim_class="magic_evidence"))
    unsupported = evaluate_claim(good_claim(claim_class="unsupported_claim", evidence_class="unsupported_claim"))
    assert unknown.decision == "CLAIM_REJECTED"
    assert "UNKNOWN_CLAIM_CLASS" in unknown.reason_codes
    assert unsupported.decision == "CLAIM_REJECTED"


def test_incomplete_malformed_input():
    assert evaluate_claim(None).decision == "CLAIM_INCOMPLETE"
    assert evaluate_claim({"claim_id": "missing-text", "claim_class": "hypothesis"}).decision == "CLAIM_INCOMPLETE"
    assert "MALFORMED_INPUT" in evaluate_claim({"claim_id": "nan", "text": "x", "claim_class": "hypothesis", "score": math.nan}).reason_codes


def test_synthetic_empirical_claim_is_synthetic_only():
    result = evaluate_claim(good_claim(data_mode="synthetic", claim_class="descriptive_empirical", evidence_class="descriptive_empirical"))
    assert result.decision == "CLAIM_SYNTHETIC_ONLY"
    assert result.scientific_eligibility is False


def test_missing_provenance_blocks_promotion():
    result = evaluate_claim(good_claim(provenance=None))
    assert result.decision == "CLAIM_PROVENANCE_INVALID"
    assert result.provenance_status == "missing"


def test_hard_rejection_rules_for_labels_leakage_and_comparability():
    unverified = evaluate_claim(good_claim(labels_verified=False))
    overlap = evaluate_claim(good_claim(train_subjects=["s1"], test_subjects=["s1"]))
    leakage = evaluate_claim(good_claim(future_to_past_leakage=True))
    triadic = evaluate_claim(good_claim(compared_metric="triadic_dependence", relation="causal influence", text="Triadic dependence is causal influence."))
    graph = evaluate_claim(good_claim(compared_metric="graph_beta1", text="Graph beta-1 is spatial winding and spatial charge."))
    assert unverified.decision == "CLAIM_REJECTED"
    assert overlap.decision == "CLAIM_REJECTED"
    assert leakage.decision == "CLAIM_REJECTED"
    assert triadic.decision == "CLAIM_REJECTED"
    assert graph.decision == "CLAIM_REJECTED"


def test_missing_multiplicity_correction_is_not_comparable_to_single_test():
    result = evaluate_claim(good_claim(n_tests=3, multiplicity_correction=None))
    assert result.decision == "CLAIM_REQUIRES_REVIEW"
    assert "MISSING_MULTIPLICITY_CORRECTION" in result.reason_codes


def test_explicitly_incompatible_comparison_is_not_comparable():
    result = evaluate_claim(good_claim(comparable=False))
    assert result.decision == "CLAIM_NOT_COMPARABLE"
    assert result.reason_codes == ("COMPARISON_NOT_COMPARABLE",)


def test_clean_audit_and_autonomic_overclaim_rejected():
    audit = evaluate_claim(good_claim(text="A clean audit confirms scientific confirmation."))
    autonomic = evaluate_claim(good_claim(text="Parasympathetic activation proves equanimity."))
    assert audit.decision == "CLAIM_REJECTED"
    assert autonomic.decision == "CLAIM_REJECTED"


def test_network_is_rejected_without_policy_and_never_called():
    result = evaluate_claim(good_claim(network_access_requested=True, network_policy_approved=False))
    assert result.decision == "CLAIM_REJECTED"
    assert "NETWORK_ACCESS_NOT_APPROVED" in result.reason_codes
    assert result.network_access_performed is False


def test_deterministic_repeated_evaluation_and_finite_json():
    first = evaluate_claim(good_claim())
    second = evaluate_claim(good_claim())
    assert first == second
    encoded = serialize_json(first)
    assert json.loads(encoded)["formal_bayes_factor"] is None
    assert "NaN" not in encoded and "Infinity" not in encoded


def test_batch_preserves_input_order():
    results = evaluate_claim_batch([good_claim(claim_id="a"), good_claim(claim_id="b")])
    assert [result.claim_id for result in results] == ["a", "b"]


def test_provenance_validation_is_explicit():
    assert validate_provenance(None).status == "missing"
    assert validate_provenance({"source_id": "x"}).status == "incomplete"
    assert validate_provenance(GOOD_PROVENANCE).status == "complete"
    assert validate_provenance({**GOOD_PROVENANCE, "checksum": "fake"}).status == "invalid"


@pytest.mark.parametrize("field,value", [
    ("source_id", "unknown_source"),
    ("source_id", "none"),
    ("acquisition", "derived_from_ledger"),
    ("acquisition", "none"),
    ("dataset_version", "TBD"),
    ("dataset_version", "none"),
])
def test_placeholder_provenance_cannot_be_treated_as_complete(field, value):
    provenance = {**GOOD_PROVENANCE, field: value}
    validation = validate_provenance(provenance)
    assert validation.status == "invalid"
    assert validation.reason_code == "PLACEHOLDER_PROVENANCE"
    result = evaluate_claim(good_claim(provenance=provenance))
    assert result.decision == "CLAIM_PROVENANCE_INVALID"


@pytest.mark.parametrize("field", ["identity", "checksum", "acquisition", "dataset_version"])
def test_typed_provenance_whitespace_fields_are_incomplete(field):
    values = {
        "source_id": "fixture-dataset",
        "source_uri": "local://fixture-dataset",
        "checksum": "a" * 64,
        "acquisition": "fixture",
        "dataset_version": "v1",
    }
    if field == "identity":
        values["source_id"] = "   "
        values["source_uri"] = "   "
    else:
        values[field] = "   "

    result = validate_provenance(ProvenanceRecord(**values))

    assert result.status == "incomplete"
    assert ("source_id" if field == "identity" else field) in result.missing_fields


@pytest.mark.parametrize("field", ["source_id", "acquisition", "dataset_version"])
@pytest.mark.parametrize("token", ["pass", "PASS", "passed", "fail", "ok", "true", "yes", "null"])
def test_bare_verdict_tokens_cannot_serve_as_complete_provenance(field, token):
    # Regression (#357 remediation): a bare verdict-like token must not complete provenance
    # and promote an empirical claim to CLAIM_ADMISSIBLE.
    provenance = {**GOOD_PROVENANCE, field: token}
    assert validate_provenance(provenance).status == "invalid"
    result = evaluate_claim(good_claim(provenance=provenance))
    assert result.decision == "CLAIM_PROVENANCE_INVALID"


@pytest.mark.parametrize("field", ["source_id", "acquisition", "dataset_version"])
@pytest.mark.parametrize("token", ["rejected", "inconclusive", "error", "blocked", "supported", "verified", "accepted", "success"])
def test_verdict_and_status_words_cannot_serve_as_provenance(field, token):
    # Regression (#357 review): verdict and status vocabulary is not a source identity.
    provenance = {**GOOD_PROVENANCE, field: token}
    assert validate_provenance(provenance).status == "invalid"
    assert evaluate_claim(good_claim(provenance=provenance)).decision == "CLAIM_PROVENANCE_INVALID"
