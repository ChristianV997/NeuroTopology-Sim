"""Interpretation text stays a proposal: no equivalence, no mechanism, no implied empirical support."""
from __future__ import annotations

import pytest

from shared.measurement_hypothesis.language import scan_interpretation, theory_terms_in


def _codes(report):
    return {error["code"] for error in report["errors"]}


def test_empirical_support_fixture_is_rejected_on_every_axis(load_fixture, check):
    report = check(load_fixture("empirical_support_implied"))
    assert report["contract_status"] == "REJECTED"
    assert {
        "CLAIM_CLASS_NOT_PERMITTED",
        "CAUSAL_OR_MECHANISM_LANGUAGE",
        "EMPIRICAL_SUPPORT_IMPLIED",
        "GATE_DECISION_BLOCKS_MAPPING",
    } <= _codes(report)
    assert report["gate"]["decision"] == "CLAIM_REJECTED"
    assert report["gate"]["scientific_eligibility"] is False


@pytest.mark.parametrize(
    "claim_class",
    ["descriptive_empirical", "formal_statistical_evidence", "benchmark_result",
     "engineering_fact", "empirical_observation", "proxy_inference", "synthetic_demonstration", "unsupported_claim"],
)
def test_mapping_may_not_declare_a_gate_class(valid_mapping, check, claim_class):
    valid_mapping["interpretation"]["claim_class"] = claim_class
    assert "CLAIM_CLASS_NOT_PERMITTED" in _codes(check(valid_mapping))


@pytest.mark.parametrize("claim_class", ["hypothesis", "speculation"])
def test_proposal_classes_are_permitted(valid_mapping, check, claim_class):
    valid_mapping["interpretation"]["claim_class"] = claim_class
    assert "CLAIM_CLASS_NOT_PERMITTED" not in _codes(check(valid_mapping))


@pytest.mark.parametrize(
    "sentence",
    [
        "The gradient is equivalent to phase circulation.",
        "The gradient is identical to the gauge field of the electrodes.",
        "The electrodes are literally quantum gauge fields.",
        "The phase gradient is the self of the recording.",
    ],
)
def test_equivalence_language_is_rejected(valid_mapping, check, sentence):
    valid_mapping["interpretation"]["proposed_interpretation"] = sentence
    assert "EQUIVALENCE_LANGUAGE" in _codes(check(valid_mapping))


@pytest.mark.parametrize(
    "sentence",
    [
        "The gradient causes phase circulation.",
        "The gradient is a mechanism for circulation.",
        "The gradient underlies the circulation process.",
        "The gradient drives inter-channel coupling.",
    ],
)
def test_causal_or_mechanistic_language_is_rejected(valid_mapping, check, sentence):
    valid_mapping["interpretation"]["proposed_interpretation"] = sentence
    assert "CAUSAL_OR_MECHANISM_LANGUAGE" in _codes(check(valid_mapping))


@pytest.mark.parametrize(
    "sentence",
    [
        "The gradient confirms phase circulation.",
        "Phase circulation is demonstrated by the gradient.",
        "The gradient proves that circulation occurs.",
        "The gradient validates the reading.",
    ],
)
def test_wording_that_implies_empirical_support_is_rejected(valid_mapping, check, sentence):
    valid_mapping["interpretation"]["proposed_interpretation"] = sentence
    assert "EMPIRICAL_SUPPORT_IMPLIED" in _codes(check(valid_mapping))


def test_negated_status_wording_stays_admissible(valid_mapping, check):
    valid_mapping["interpretation"]["proposed_interpretation"] = (
        "The reading is not yet validated and is not established as a finding."
    )
    valid_mapping["interpretation"]["assumptions"] = ["This is not validated for any montage."]
    report = check(valid_mapping)
    assert "EMPIRICAL_SUPPORT_IMPLIED" not in _codes(report)
    assert report["contract_status"] == "VALID_HYPOTHESIS_MAPPING"


def test_explicit_non_equivalence_is_admissible(valid_mapping, check):
    valid_mapping["interpretation"]["proposed_interpretation"] = (
        "The gradient is not equivalent to a gauge field; it could serve as a proxy."
    )
    assert "EQUIVALENCE_LANGUAGE" not in _codes(check(valid_mapping))


def test_ontology_firewall_phrase_is_rejected(valid_mapping, check):
    valid_mapping["interpretation"]["proposed_interpretation"] = "Q equals self in this reading."
    assert "ONTOLOGY_FIREWALL_VIOLATION" in _codes(check(valid_mapping))


def test_shared_claim_rule_phrase_is_rejected(valid_mapping, check):
    valid_mapping["interpretation"]["proposed_interpretation"] = "The metric proves consciousness."
    assert "SHARED_CLAIM_RULE" in _codes(check(valid_mapping))


def test_scanner_reports_categories_without_editing_text():
    text = "The gradient confirms and causes circulation."
    original = text
    hits = scan_interpretation(text)
    assert hits["empirical_support"] == ["confirm"]
    assert hits["causal_or_mechanism"] == ["causes"]
    assert text == original


@pytest.mark.parametrize("field, code", [
    ("alternative_explanations", "ALTERNATIVES_MISSING"),
    ("confounds", "CONFOUNDS_MISSING"),
    ("assumptions", "ASSUMPTIONS_MISSING"),
])
def test_missing_alternatives_confounds_or_assumptions_are_rejected(valid_mapping, check, field, code):
    valid_mapping["interpretation"][field] = []
    assert code in _codes(check(valid_mapping))


def test_missing_falsifiers_are_rejected(valid_mapping, check):
    valid_mapping["interpretation"]["falsifiers"] = []
    assert "FALSIFIERS_MISSING" in _codes(check(valid_mapping))


@pytest.mark.parametrize("patch", [
    {"discriminates": ""},
    {"test": None},
    {"id": "one"},
])
def test_incomplete_falsifier_is_rejected(valid_mapping, check, patch):
    valid_mapping["interpretation"]["falsifiers"][0].update(patch)
    assert "FALSIFIER_INCOMPLETE" in _codes(check(valid_mapping))


def test_missing_proposed_interpretation_is_rejected(valid_mapping, check):
    del valid_mapping["interpretation"]["proposed_interpretation"]
    assert "INTERPRETATION_MISSING" in _codes(check(valid_mapping))


def test_malformed_hypothesis_identifier_is_rejected(valid_mapping, check):
    valid_mapping["interpretation"]["hypothesis_id"] = "hypothesis one"
    assert "HYPOTHESIS_ID_INVALID" in _codes(check(valid_mapping))


def test_missing_not_established_statement_is_rejected(valid_mapping, check):
    valid_mapping["not_established"] = []
    assert "NOT_ESTABLISHED_MISSING" in _codes(check(valid_mapping))


def test_theory_terms_are_detected_regardless_of_formatting():
    assert theory_terms_in("ttfcd_phase_gradient") == ["ttfcd"]
    assert theory_terms_in("TTFCD.phase") == ["ttfcd"]
    assert theory_terms_in("UTTL-phase-gradient") == ["uttl"]
    assert theory_terms_in("channel_phase_gradient_metrics") == []
