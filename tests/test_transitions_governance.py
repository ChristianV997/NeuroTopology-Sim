"""Tests for transitions.governance — claim-scope / evidence-level gating."""
from __future__ import annotations

import pytest

from transitions.governance import (
    ALLOWED_CLAIM_SCOPES,
    ALLOWED_EVIDENCE_LEVELS,
    BLOCKED_CLAIM_SCOPES,
    GovernanceError,
    validate_governance,
    validate_governance_or_raise,
)
from transitions.record import TransitionRecordV1


def _make(**overrides):
    kwargs = dict(
        dataset_id="ds005620",
        subject_id="sub-1010",
        modality="eeg",
        source_state="awake",
        target_state="sedated",
        transition_class="anesthesia_induction",
        feature_names=["topology.q_net"],
        limitations=["synthetic fixture only"],
    )
    kwargs.update(overrides)
    return TransitionRecordV1.make(**kwargs)


@pytest.mark.parametrize("scope", sorted(BLOCKED_CLAIM_SCOPES))
def test_blocked_claim_scopes_always_fail(scope):
    r = _make(claim_scope=scope, evidence_level="L0_computational_artifact")
    errors = validate_governance(r)
    assert any("blocked" in e for e in errors)


def test_clinical_scope_fails():
    r = _make(claim_scope="clinical")
    errors = validate_governance(r)
    assert any("blocked" in e for e in errors)


def test_diagnostic_scope_fails():
    r = _make(claim_scope="diagnostic")
    assert any("blocked" in e for e in validate_governance(r))


def test_treatment_scope_fails():
    r = _make(claim_scope="treatment")
    assert any("blocked" in e for e in validate_governance(r))


def test_consciousness_biomarker_scope_fails():
    r = _make(claim_scope="consciousness_biomarker")
    assert any("blocked" in e for e in validate_governance(r))


def test_jhana_detection_scope_fails():
    r = _make(claim_scope="jhana_detection")
    assert any("blocked" in e for e in validate_governance(r))


def test_cessation_detection_scope_fails():
    r = _make(claim_scope="cessation_detection")
    assert any("blocked" in e for e in validate_governance(r))


def test_enlightenment_detection_scope_fails():
    r = _make(claim_scope="enlightenment_detection")
    assert any("blocked" in e for e in validate_governance(r))


def test_spiritual_attainment_scope_fails():
    r = _make(claim_scope="spiritual_attainment")
    assert any("blocked" in e for e in validate_governance(r))


def test_mechanistic_causal_scope_fails():
    r = _make(claim_scope="mechanistic_causal")
    assert any("blocked" in e for e in validate_governance(r))


@pytest.mark.parametrize("scope", sorted(ALLOWED_CLAIM_SCOPES))
def test_allowed_scopes_pass_when_requirements_met(scope):
    r = _make(
        claim_scope=scope,
        evidence_level="L4_cross_subject_dataset_specific",
        state_label_confidence=0.9,
        record_level="cohort" if scope == "cross_subject_dataset_specific" else "subject",
        subject_id=None if scope == "cross_subject_dataset_specific" else "sub-1010",
    )
    errors = validate_governance(r)
    assert errors == [], errors


def test_unknown_claim_scope_fails_closed():
    r = _make(claim_scope="totally_made_up_scope")
    errors = validate_governance(r)
    assert any("not a recognized scope" in e for e in errors)


def test_unknown_evidence_level_fails_closed():
    r = _make(evidence_level="L99_nonexistent")
    errors = validate_governance(r)
    assert any("not a recognized level" in e for e in errors)


def test_dataset_specific_without_dataset_id_fails():
    r = _make(claim_scope="dataset_specific", dataset_id=None, state_label_confidence=0.8)
    errors = validate_governance(r)
    assert any("dataset_specific" in e and "dataset_id" in e for e in errors)


def test_dataset_specific_without_states_fails():
    r = _make(
        claim_scope="dataset_specific", source_state=None, target_state=None,
        state_label_confidence=0.8,
    )
    errors = validate_governance(r)
    assert any("source_state and target_state" in e for e in errors)


def test_dataset_specific_without_state_label_confidence_fails():
    r = _make(claim_scope="dataset_specific", state_label_confidence=None)
    errors = validate_governance(r)
    assert any("state_label_confidence" in e for e in errors)


def test_dataset_specific_with_all_requirements_passes():
    r = _make(
        claim_scope="dataset_specific", evidence_level="L3_dataset_specific_effect",
        state_label_confidence=0.85,
    )
    assert validate_governance(r) == []


def test_cross_subject_without_cohort_evidence_fails():
    r = _make(
        claim_scope="cross_subject_dataset_specific",
        evidence_level="L4_cross_subject_dataset_specific",
        record_level="subject", subject_id="sub-1010",
    )
    errors = validate_governance(r)
    assert any("cross_subject_dataset_specific" in e for e in errors)


def test_cross_subject_with_cohort_record_level_passes():
    r = _make(
        claim_scope="cross_subject_dataset_specific",
        evidence_level="L4_cross_subject_dataset_specific",
        record_level="cohort", subject_id=None,
    )
    assert validate_governance(r) == []


def test_cross_subject_with_subject_count_metadata_passes():
    r = _make(
        claim_scope="cross_subject_dataset_specific",
        evidence_level="L4_cross_subject_dataset_specific",
        metadata={"subject_count": 12},
    )
    assert validate_governance(r) == []


def test_cross_subject_with_subject_count_of_one_fails():
    r = _make(
        claim_scope="cross_subject_dataset_specific",
        evidence_level="L4_cross_subject_dataset_specific",
        record_level="subject", subject_id="sub-1010",
        metadata={"subject_count": 1},
    )
    errors = validate_governance(r)
    assert any("cross_subject_dataset_specific" in e for e in errors)


def test_experimental_feature_capped_at_exploratory_metric():
    r = _make(
        feature_names=["experimental.novel_metric"],
        claim_scope="dataset_specific",
        evidence_level="L3_dataset_specific_effect",
        state_label_confidence=0.8,
    )
    errors = validate_governance(r)
    assert any("experimental" in e for e in errors)


def test_experimental_feature_allowed_under_exploratory_metric():
    r = _make(
        feature_names=["experimental.novel_metric"],
        claim_scope="exploratory_metric",
    )
    assert validate_governance(r) == []


# ── Null-control status ──────────────────────────────────────────────────────

def test_null_status_cannot_silently_pass_when_absent():
    r = _make()
    r.null_control_summary = None
    errors = validate_governance(r)
    assert any("null_control_summary" in e for e in errors)


def test_null_status_missing_status_key_fails():
    r = _make()
    r.null_control_summary = {"note": "no status here"}
    errors = validate_governance(r)
    assert any("null_control_summary" in e for e in errors)


def test_null_status_invalid_value_fails():
    r = _make()
    r.null_control_summary = {"status": "definitely_passed_trust_me"}
    errors = validate_governance(r)
    assert any("null_control_summary.status" in e for e in errors)


@pytest.mark.parametrize("status", ["not_provided", "not_applicable", "failed", "passed"])
def test_null_status_valid_values_pass(status):
    r = _make()
    r.null_control_summary = {"status": status}
    assert validate_governance(r) == []


def test_default_null_control_status_is_not_provided_never_passed():
    r = _make()
    assert r.null_control_summary["status"] == "not_provided"
    assert r.null_control_summary["status"] != "passed"


# ── Free-text overreach scan ─────────────────────────────────────────────────

def test_banned_phrase_in_limitations_fails():
    r = _make(limitations=["this proves consciousness beyond doubt"])
    errors = validate_governance(r)
    assert any("banned phrase" in e for e in errors)


def test_banned_phrase_in_metadata_fails():
    r = _make(metadata={"note": "jhana detected in this window"})
    errors = validate_governance(r)
    assert any("banned phrase" in e for e in errors)


def test_validate_governance_or_raise_raises():
    r = _make(claim_scope="clinical")
    with pytest.raises(GovernanceError):
        validate_governance_or_raise(r)


def test_all_allowed_evidence_levels_are_five():
    assert len(ALLOWED_EVIDENCE_LEVELS) == 5
