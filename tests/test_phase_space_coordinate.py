"""Tests for PhaseSpaceCoordinateV1 — offline, synthetic fixtures only."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from phase_space.coordinate import (
    CLAIM_SCOPE_ORDER,
    PHASE_SPACE_MAX_CLAIM_SCOPE,
    CoordinateValidationError,
    PhaseSpaceCoordinateV1,
    cap_claim_scope,
    compute_coordinate_id,
)

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

_REQUIRED_KEYS = (
    "schema_version", "coordinate_id", "transition_id", "dataset_id",
    "subject_id", "session_id", "record_level", "modality", "axis", "value",
    "status", "confidence", "source_features", "missing_features",
    "normalization_mode", "estimator", "estimator_version",
    "input_claim_scope", "output_claim_scope", "input_evidence_level",
    "limitations", "provenance", "created_at", "metadata",
)


def _make(**overrides):
    kwargs = dict(
        transition_id="abc123def456",
        axis="topological_organization",
        normalization_mode="within_record",
        estimator="delta_share_v1",
        input_claim_scope="exploratory_metric",
        input_evidence_level="L2_single_subject_real_signal",
        value=0.5,
        status="estimated",
        confidence="low",
        source_features=["topology.q_abs"],
        limitations=["synthetic fixture only"],
        _now=_NOW,
    )
    kwargs.update(overrides)
    return PhaseSpaceCoordinateV1.make(**kwargs)


# ── Serialization ───────────────────────────────────────────────────────────

def test_to_dict_has_all_required_keys():
    assert set(_make().to_dict()) == set(_REQUIRED_KEYS)


def test_dict_roundtrip():
    c = _make()
    assert PhaseSpaceCoordinateV1.from_dict(c.to_dict()).to_dict() == c.to_dict()


def test_json_roundtrip():
    c = _make()
    assert PhaseSpaceCoordinateV1.from_json(c.to_json()).to_dict() == c.to_dict()


def test_write_json_roundtrip(tmp_path):
    c = _make()
    path = c.write_json(tmp_path / "nested" / "PhaseSpaceCoordinate.json")
    assert path.exists()
    assert PhaseSpaceCoordinateV1.from_json(path.read_text()).to_dict() == c.to_dict()


def test_valid_coordinate_validates_clean():
    assert _make().validate() == []


# ── Deterministic ID ────────────────────────────────────────────────────────

def test_identical_identity_fields_produce_identical_id():
    a = _make(value=0.1, confidence="low", limitations=["one"])
    b = _make(value=0.9, confidence="moderate", limitations=["totally different"])
    assert a.coordinate_id == b.coordinate_id


def test_created_at_does_not_affect_id():
    a = _make(_now=_NOW)
    b = _make(_now=datetime(2031, 7, 4, tzinfo=timezone.utc))
    assert a.coordinate_id == b.coordinate_id


def test_transition_id_change_affects_id():
    assert _make(transition_id="aaa").coordinate_id != _make(transition_id="bbb").coordinate_id


def test_axis_change_affects_id():
    a = _make(axis="topological_organization")
    b = _make(axis="integration", source_features=["connectivity.mean_plv"])
    assert a.coordinate_id != b.coordinate_id


def test_normalization_mode_change_affects_id():
    assert _make(normalization_mode="raw").coordinate_id != _make(
        normalization_mode="within_record"
    ).coordinate_id


def test_estimator_version_change_affects_id():
    assert _make(estimator_version="phase_space.v1").coordinate_id != _make(
        estimator_version="phase_space.v2"
    ).coordinate_id


def test_compute_coordinate_id_matches_make():
    c = _make()
    assert c.coordinate_id == compute_coordinate_id(
        transition_id="abc123def456",
        axis="topological_organization",
        estimator_version=c.estimator_version,
        normalization_mode="within_record",
    )


def test_tampered_coordinate_id_fails_validation():
    c = _make()
    c.coordinate_id = "0000000000000000"
    assert any("does not match" in e for e in c.validate())


# ── Claim-scope monotonicity ────────────────────────────────────────────────

def test_cap_claim_scope_never_promotes():
    for scope in CLAIM_SCOPE_ORDER:
        capped = cap_claim_scope(scope)
        assert CLAIM_SCOPE_ORDER.index(capped) <= CLAIM_SCOPE_ORDER.index(scope)


def test_cap_claim_scope_applies_phase_space_ceiling():
    assert cap_claim_scope("cross_subject_dataset_specific") == PHASE_SPACE_MAX_CLAIM_SCOPE
    assert cap_claim_scope("dataset_specific") == PHASE_SPACE_MAX_CLAIM_SCOPE


def test_cap_claim_scope_preserves_weaker_input():
    assert cap_claim_scope("computational_artifact") == "computational_artifact"


def test_cap_claim_scope_fails_closed_on_blocked_scope():
    assert cap_claim_scope("clinical") == CLAIM_SCOPE_ORDER[0]


def test_cap_claim_scope_fails_closed_on_unknown_scope():
    assert cap_claim_scope("totally_made_up") == CLAIM_SCOPE_ORDER[0]


def test_output_scope_exceeding_input_fails_validation():
    c = _make(input_claim_scope="computational_artifact")
    c.output_claim_scope = "dataset_specific"
    assert any("exceeds" in e for e in c.validate())


def test_blocked_input_scope_fails_validation():
    c = _make()
    c.input_claim_scope = "clinical"
    assert any("blocked" in e for e in c.validate())


# ── Status / value / confidence coherence ───────────────────────────────────

def test_estimated_without_value_fails():
    c = _make(status="estimated", value=None)
    assert any("requires a non-null value" in e for e in c.validate())


def test_estimated_without_source_features_fails():
    c = _make(source_features=[])
    assert any("source_features" in e for e in c.validate())


def test_estimated_with_none_confidence_fails():
    c = _make(confidence="none")
    assert any("confidence above 'none'" in e for e in c.validate())


def test_non_estimated_with_value_fails():
    c = _make(status="insufficient_data", value=0.3, confidence="none",
              missing_features=["topology.q_abs"], source_features=[])
    assert any("must not carry a value" in e for e in c.validate())


def test_insufficient_data_without_missing_features_fails():
    c = _make(status="insufficient_data", value=None, confidence="none",
              source_features=[], missing_features=[])
    assert any("missing_features" in e for e in c.validate())


def test_zero_value_is_a_legitimate_estimate_not_missing_data():
    c = _make(value=0.0)
    assert c.validate() == []
    assert c.status == "estimated"


@pytest.mark.parametrize("bad", ["nonsense", "", "ESTIMATED"])
def test_unknown_status_fails(bad):
    c = _make(status=bad)
    assert any("status" in e for e in c.validate())


@pytest.mark.parametrize("bad", ["very_high", "certain", ""])
def test_unknown_confidence_fails(bad):
    c = _make(confidence=bad)
    assert any("confidence" in e for e in c.validate())


def test_unknown_normalization_mode_fails():
    c = _make(normalization_mode="minmax")
    assert any("normalization_mode" in e for e in c.validate())


# ── Governance free text ────────────────────────────────────────────────────

def test_empty_limitations_fails():
    c = _make(limitations=[])
    assert any("limitations" in e for e in c.validate())


def test_banned_phrase_in_limitations_fails():
    # Sourced from the canonical list rather than hardcoded, so this tests the
    # real firewall and does not itself plant banned text in the repository.
    from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES

    c = _make(limitations=[f"this {BANNED_REPORT_PHRASES[0]}"])
    assert any("banned phrase" in e for e in c.validate())


def test_banned_phrase_in_metadata_fails():
    from transitions.governance import TRANSITION_EXTRA_BANNED_PHRASES

    c = _make(metadata={"note": TRANSITION_EXTRA_BANNED_PHRASES[1]})
    assert any("banned phrase" in e for e in c.validate())


def test_unknown_axis_fails_validation():
    c = _make(axis="consciousness_level")
    assert c.validate()


def test_validate_or_raise_raises():
    c = _make(limitations=[])
    with pytest.raises(CoordinateValidationError):
        c.validate_or_raise()
