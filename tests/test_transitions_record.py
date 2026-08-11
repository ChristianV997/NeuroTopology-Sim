"""Tests for TransitionRecordV1 — all offline, synthetic fixtures only."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from transitions.record import TransitionRecordV1, compute_transition_id

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

_REQUIRED_KEYS = (
    "schema_version", "transition_id", "dataset_id", "subject_id", "session_id",
    "record_level", "modality", "source_state", "target_state", "transition_class",
    "time_axis", "feature_names", "trajectory_artifact", "delta_summary",
    "velocity_summary", "duration", "intervention", "preprocessing_provenance",
    "null_control_summary", "state_label_confidence", "claim_scope", "evidence_level",
    "limitations", "artifact_paths", "created_at", "repo_commit", "metadata",
)


def _make(**overrides):
    kwargs = dict(
        dataset_id="ds005620",
        subject_id="sub-1010",
        session_id=None,
        modality="eeg",
        source_state="awake",
        target_state="sedated",
        transition_class="anesthesia_induction",
        feature_names=["topology.q_net", "connectivity.mean_plv"],
        limitations=["synthetic fixture only"],
        _now=_NOW,
    )
    kwargs.update(overrides)
    return TransitionRecordV1.make(**kwargs)


# ── Serialization ───────────────────────────────────────────────────────────

def test_to_dict_has_all_required_keys():
    r = _make()
    d = r.to_dict()
    assert set(d.keys()) == set(_REQUIRED_KEYS)


def test_dict_roundtrip():
    r = _make()
    d = r.to_dict()
    r2 = TransitionRecordV1.from_dict(d)
    assert r2.to_dict() == d


def test_json_roundtrip():
    r = _make()
    text = r.to_json()
    r2 = TransitionRecordV1.from_json(text)
    assert r2.to_dict() == r.to_dict()


def test_write_json_roundtrip(tmp_path):
    r = _make()
    path = r.write_json(tmp_path / "nested" / "TransitionRecord.json")
    assert path.exists()
    loaded = TransitionRecordV1.from_json(path.read_text())
    assert loaded.to_dict() == r.to_dict()


def test_validate_success_for_valid_record():
    r = _make()
    assert r.validate() == []


def test_null_control_summary_defaults_to_not_provided():
    r = _make()
    assert r.null_control_summary == {"status": "not_provided"}


# ── Deterministic ID ─────────────────────────────────────────────────────────

def test_identical_identity_fields_produce_identical_id():
    r1 = _make(transition_class="a", limitations=["l1"])
    r2 = _make(transition_class="b", limitations=["l2 completely different"])
    assert r1.transition_id == r2.transition_id


def test_created_at_does_not_affect_id():
    r1 = _make(_now=_NOW)
    r2 = _make(_now=datetime(2030, 6, 1, tzinfo=timezone.utc))
    assert r1.transition_id == r2.transition_id


def test_target_state_change_affects_id():
    r1 = _make(target_state="sedated")
    r2 = _make(target_state="baseline")
    assert r1.transition_id != r2.transition_id


def test_source_state_change_affects_id():
    r1 = _make(source_state="awake")
    r2 = _make(source_state="drowsy")
    assert r1.transition_id != r2.transition_id


def test_dataset_change_affects_id():
    r1 = _make(dataset_id="ds005620")
    r2 = _make(dataset_id="ds006644")
    assert r1.transition_id != r2.transition_id


def test_subject_change_affects_id():
    r1 = _make(subject_id="sub-1010")
    r2 = _make(subject_id="sub-1011")
    assert r1.transition_id != r2.transition_id


def test_session_change_affects_id():
    r1 = _make(session_id="ses-01")
    r2 = _make(session_id="ses-02")
    assert r1.transition_id != r2.transition_id


def test_modality_change_affects_id():
    r1 = _make(modality="eeg")
    r2 = _make(modality="fmri")
    assert r1.transition_id != r2.transition_id


def test_feature_set_change_affects_id():
    r1 = _make(feature_names=["topology.q_net"])
    r2 = _make(feature_names=["topology.q_net", "topology.q_abs"])
    assert r1.transition_id != r2.transition_id


def test_feature_order_does_not_affect_id():
    r1 = _make(feature_names=["topology.q_net", "connectivity.mean_plv"])
    r2 = _make(feature_names=["connectivity.mean_plv", "topology.q_net"])
    assert r1.transition_id == r2.transition_id


def test_compute_transition_id_matches_make():
    r = _make()
    expected = compute_transition_id(
        dataset_id="ds005620", subject_id="sub-1010", session_id=None,
        source_state="awake", target_state="sedated", modality="eeg",
        feature_names=["topology.q_net", "connectivity.mean_plv"],
    )
    assert r.transition_id == expected


def test_tampered_transition_id_fails_validation():
    r = _make()
    r.transition_id = "0000000000000000"
    errors = r.validate()
    assert any("does not match" in e for e in errors)


# ── Required-field failures ──────────────────────────────────────────────────

def test_missing_dataset_id_fails():
    r = _make(dataset_id=None)
    errors = r.validate()
    assert any("dataset_id" in e for e in errors)


def test_missing_states_fails_under_default_scope_when_forced_stronger():
    r = _make(
        source_state=None, target_state=None,
        claim_scope="dataset_specific", evidence_level="L3_dataset_specific_effect",
        state_label_confidence=0.9,
    )
    errors = r.validate()
    assert any("source_state and target_state are required" in e for e in errors)


def test_missing_states_allowed_under_exploratory_metric_scope():
    r = _make(source_state=None, target_state=None, claim_scope="exploratory_metric")
    errors = r.validate()
    assert not any("source_state and target_state are required" in e for e in errors)


def test_cohort_record_level_must_be_explicit():
    r = _make(record_level="cohort", subject_id=None)
    errors = r.validate()
    assert errors == []


def test_cohort_record_level_rejects_subject_id():
    r = _make(record_level="cohort", subject_id="sub-1010")
    errors = r.validate()
    assert any("cohort" in e for e in errors)


def test_subject_record_level_requires_subject_id():
    r = _make(record_level="subject", subject_id=None)
    errors = r.validate()
    assert any("subject_id" in e for e in errors)


def test_unknown_record_level_fails():
    r = _make(record_level="galaxy")
    errors = r.validate()
    assert any("record_level" in e for e in errors)


def test_limitations_must_be_non_empty():
    r = _make(limitations=[])
    errors = r.validate()
    assert any("limitations" in e for e in errors)


def test_state_label_confidence_out_of_range_fails():
    r = _make(state_label_confidence=1.5)
    errors = r.validate()
    assert any("state_label_confidence" in e for e in errors)


def test_negative_duration_fails():
    r = _make(duration=-1.0)
    errors = r.validate()
    assert any("duration" in e for e in errors)


def test_validate_or_raise_raises_on_invalid_record():
    r = _make(dataset_id=None)
    with pytest.raises(Exception):
        r.validate_or_raise()
