"""Evidence-state vocabulary and artifact classification."""
from __future__ import annotations

import pytest

from awareness_studio.orchestrator.orchestrator import (
    _DECLARED_CLASS_STATES,
    _UNSUPPORTED_DECLARED_CLASSES,
    DRY_RUN_STATES,
    EVIDENCE_READY_STATES,
    EvidenceState,
    classify_artifact,
)
from awareness_studio.research_cycle import EvidenceClass
from tests.orchestrator.conftest import make_identified

REQUIRED_STATES = {
    "mock", "synthetic", "proxy", "engineering", "empirical",
    "invalid", "incomplete", "failed", "blocked", "planning", "review_required",
}


def test_vocabulary_contains_every_required_state():
    assert {state.value for state in EvidenceState} == REQUIRED_STATES


def test_only_engineering_and_empirical_are_evidence_ready_states():
    assert EVIDENCE_READY_STATES == frozenset({EvidenceState.ENGINEERING, EvidenceState.EMPIRICAL})


def test_dry_run_states_are_planning_or_review_only():
    assert DRY_RUN_STATES == frozenset({EvidenceState.PLANNING, EvidenceState.REVIEW_REQUIRED})


def test_fully_identified_engineering_artifact_is_evidence_ready(identified):
    decision = classify_artifact(identified())
    assert decision.state is EvidenceState.ENGINEERING
    assert decision.evidence_ready is True
    assert decision.missing_identities == ()


def test_fully_identified_descriptive_empirical_artifact_is_evidence_ready(identified):
    decision = classify_artifact(identified(evidence_class="descriptive_empirical"))
    assert decision.state is EvidenceState.EMPIRICAL
    assert decision.evidence_ready is True


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"data_mode": "synthetic", "evidence_class": "synthetic_demonstration"}, EvidenceState.SYNTHETIC),
        ({"data_mode": "mock", "evidence_class": "mock"}, EvidenceState.MOCK),
        ({"data_mode": "proxy", "evidence_class": "proxy_inference"}, EvidenceState.PROXY),
        ({"data_mode": "planning", "evidence_class": "planning"}, EvidenceState.PLANNING),
    ],
)
def test_non_evidence_markers_are_never_evidence_ready_even_with_full_identity(identified, overrides, expected):
    decision = classify_artifact(identified(**overrides))
    assert decision.state is expected
    assert decision.evidence_ready is False


def test_synthetic_data_declared_as_engineering_is_rejected_as_conflict(identified):
    decision = classify_artifact(identified(data_mode="synthetic", evidence_class="engineering_fact"))
    assert decision.state is EvidenceState.INVALID
    assert any(reason.startswith("conflicting_evidence_declaration") for reason in decision.reasons)


def test_proxy_data_declared_as_empirical_is_rejected_as_conflict(identified):
    decision = classify_artifact(identified(data_mode="proxy", evidence_class="descriptive_empirical"))
    assert decision.state is EvidenceState.INVALID


def test_conflicting_non_evidence_markers_are_rejected(identified):
    decision = classify_artifact(identified(data_mode="synthetic", mock=True, evidence_class="synthetic_demonstration"))
    assert decision.state is EvidenceState.INVALID
    assert any(reason.startswith("conflicting_non_evidence_markers") for reason in decision.reasons)


def test_unknown_evidence_class_fails_closed(identified):
    decision = classify_artifact(identified(evidence_class="definitely_not_a_class"))
    assert decision.state is EvidenceState.INVALID
    assert decision.evidence_ready is False


def test_formal_statistical_evidence_is_unsupported_while_bayes_factor_is_null(identified):
    decision = classify_artifact(identified(evidence_class="formal_statistical_evidence"))
    assert decision.state is EvidenceState.INVALID
    assert any(reason.startswith("unsupported_claim:formal_statistical_evidence") for reason in decision.reasons)


def test_undeclared_evidence_class_is_incomplete_not_evidence(identified):
    artifact = identified()
    del artifact["evidence_class"]
    decision = classify_artifact(artifact)
    assert decision.state is EvidenceState.INCOMPLETE
    assert decision.evidence_ready is False


@pytest.mark.parametrize("declared", ["hypothesis", "speculation"])
def test_hypothesis_and_speculation_are_review_required_not_evidence(identified, declared):
    decision = classify_artifact(identified(evidence_class=declared))
    assert decision.state is EvidenceState.REVIEW_REQUIRED
    assert decision.evidence_ready is False


def test_unsupported_claim_declared_class_is_invalid(identified):
    decision = classify_artifact(identified(evidence_class="unsupported_claim"))
    assert decision.state is EvidenceState.INVALID


# ── vocabulary drift and allowlists ───────────────────────────────────────────

def test_every_research_cycle_evidence_class_is_explicitly_classified():
    known = set(_DECLARED_CLASS_STATES) | set(_UNSUPPORTED_DECLARED_CLASSES)
    assert {member.value for member in EvidenceClass} - known == set()


def test_declared_classes_map_to_the_intended_states():
    assert _DECLARED_CLASS_STATES[EvidenceClass.ENGINEERING_FACT.value] is EvidenceState.ENGINEERING
    assert _DECLARED_CLASS_STATES[EvidenceClass.BENCHMARK_RESULT.value] is EvidenceState.EMPIRICAL
    assert _DECLARED_CLASS_STATES[EvidenceClass.DESCRIPTIVE_EMPIRICAL.value] is EvidenceState.EMPIRICAL
    assert _DECLARED_CLASS_STATES[EvidenceClass.SYNTHETIC_DEMONSTRATION.value] is EvidenceState.SYNTHETIC
    assert _DECLARED_CLASS_STATES[EvidenceClass.PROXY_INFERENCE.value] is EvidenceState.PROXY
    assert _DECLARED_CLASS_STATES[EvidenceClass.HYPOTHESIS.value] is EvidenceState.REVIEW_REQUIRED
    assert _DECLARED_CLASS_STATES[EvidenceClass.SPECULATION.value] is EvidenceState.REVIEW_REQUIRED
    assert _DECLARED_CLASS_STATES[EvidenceClass.UNSUPPORTED_CLAIM.value] is EvidenceState.INVALID


def test_measured_data_mode_is_accepted_on_an_identified_empirical_artifact(identified):
    decision = classify_artifact(identified(data_mode="empirical", evidence_class="descriptive_empirical"))
    assert decision.state is EvidenceState.EMPIRICAL
    assert decision.evidence_ready is True


@pytest.mark.parametrize("data_mode", ["demo", "synthetic_or_real", "unlisted_mode"])
def test_unknown_data_mode_fails_closed_even_with_full_identity(identified, data_mode):
    decision = classify_artifact(identified(data_mode=data_mode))
    assert decision.state is EvidenceState.INVALID
    assert decision.evidence_ready is False


@pytest.mark.parametrize("flag_value", ["true", "false", 1, 0, None])
def test_non_boolean_mock_or_synthetic_flag_is_invalid(identified, flag_value):
    assert classify_artifact(identified(mock=flag_value)).state is EvidenceState.INVALID
    assert classify_artifact(identified(synthetic=flag_value)).state is EvidenceState.INVALID


@pytest.mark.parametrize(
    "overrides",
    [
        {"scientific_pass": True},
        {"scientific_pass": None},
        {"scientific_evidence": True},
        {"formal_bayes_factor": 0.5},
    ],
)
def test_artifact_asserting_a_pass_or_a_formal_statistic_is_invalid(identified, overrides):
    decision = classify_artifact(identified(**overrides))
    assert decision.state is EvidenceState.INVALID
    assert decision.evidence_ready is False


def test_explicit_false_scientific_fields_and_null_bayes_factor_are_accepted(identified):
    decision = classify_artifact(identified(scientific_pass=False, scientific_evidence=False, formal_bayes_factor=None))
    assert decision.evidence_ready is True
