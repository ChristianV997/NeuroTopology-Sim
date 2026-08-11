"""Tests for phase-space estimators — synthetic TransitionRecords only."""
from __future__ import annotations

import pytest

from phase_space.axes import AXIS_NAMES, PLACEHOLDER_AXES
from phase_space.estimators import estimate_axis, estimate_coordinates
from phase_space.normalization import NormalizationError
from phase_space.uncertainty import assign_confidence, cap_confidence
from transitions.record import TransitionRecordV1


def _record(feature_names, deltas, **overrides):
    kwargs = dict(
        dataset_id="ds005620",
        subject_id="sub-9001",
        modality="EEG",
        source_state="awake",
        target_state="sedated",
        transition_class="anesthesia_propofol_awake_to_sedated",
        feature_names=list(feature_names),
        limitations=["synthetic fixture only"],
        claim_scope="exploratory_metric",
        evidence_level="L2_single_subject_real_signal",
        delta_summary={
            "status": "ok",
            "delta_per_feature": list(deltas),
            "mean_abs_delta": (
                sum(abs(d) for d in deltas) / len(deltas) if deltas else 0.0
            ),
            "n_timepoints": 2,
            "n_features": len(deltas),
        },
        time_axis={"unit": "condition_summary", "n_samples": 2},
    )
    kwargs.update(overrides)
    return TransitionRecordV1.make(**kwargs)


# ── Estimation from present features ────────────────────────────────────────

def test_topological_organization_estimated_from_topology_features():
    rec = _record(
        ["topology.q_abs", "topology.spatial_defect_betti1"], [8.0, 1.0]
    )
    c = estimate_axis(rec, "topological_organization")
    assert c.status == "estimated"
    assert c.value is not None
    assert set(c.source_features) == {"topology.q_abs", "topology.spatial_defect_betti1"}
    assert c.validate() == []


def test_integration_estimated_from_mean_plv():
    rec = _record(["connectivity.mean_plv"], [-0.35])
    c = estimate_axis(rec, "integration")
    assert c.status == "estimated"
    assert c.source_features == ["connectivity.mean_plv"]
    assert c.value == pytest.approx(-1.0)  # only feature, so it is 100% of the mass
    assert c.validate() == []


def test_temporal_continuity_estimated_from_velocity_and_acceleration():
    rec = _record(
        ["transition.velocity", "transition.acceleration"], [0.4, -0.1]
    )
    c = estimate_axis(rec, "temporal_continuity")
    assert c.status == "estimated"
    assert set(c.source_features) == {"transition.velocity", "transition.acceleration"}
    assert c.validate() == []


def test_only_mapped_features_contribute():
    rec = _record(
        ["topology.q_abs", "connectivity.mean_plv"], [5.0, 5.0]
    )
    c = estimate_axis(rec, "topological_organization")
    assert c.source_features == ["topology.q_abs"]
    assert "connectivity.mean_plv" not in c.source_features


def test_within_record_value_is_bounded_to_unit_interval():
    rec = _record(
        ["topology.q_abs", "connectivity.mean_plv", "complexity.entropy"],
        [100.0, -3.0, 0.5],
    )
    for axis in AXIS_NAMES:
        c = estimate_axis(rec, axis)
        if c.status == "estimated":
            assert -1.0 <= c.value <= 1.0, f"axis {axis} escaped [-1, 1]"


def test_signed_direction_is_preserved():
    up = estimate_axis(_record(["topology.q_abs"], [4.0]), "topological_organization")
    down = estimate_axis(_record(["topology.q_abs"], [-4.0]), "topological_organization")
    assert up.value > 0 > down.value


# ── Missing data never fabricated ───────────────────────────────────────────

def test_missing_features_yield_insufficient_data_not_a_value():
    rec = _record(["topology.q_abs"], [4.0])
    c = estimate_axis(rec, "integration")
    assert c.status == "insufficient_data"
    assert c.value is None
    assert c.confidence == "none"
    assert c.missing_features  # explicit
    assert c.validate() == []


def test_missing_delta_summary_yields_insufficient_data():
    rec = _record(["topology.q_abs"], [4.0], delta_summary=None)
    c = estimate_axis(rec, "topological_organization")
    assert c.status == "insufficient_data"
    assert c.value is None


def test_misaligned_delta_summary_refuses_to_guess():
    rec = _record(["topology.q_abs", "topology.q_net"], [4.0])
    rec.delta_summary = {"status": "ok", "delta_per_feature": [4.0], "n_timepoints": 2}
    c = estimate_axis(rec, "topological_organization")
    assert c.status == "insufficient_data"
    assert "alignment" in " ".join(c.limitations).lower() or "refusing" in " ".join(
        c.limitations
    ).lower()


def test_non_numeric_delta_yields_insufficient_data():
    rec = _record(["topology.q_abs"], [0.0])
    rec.delta_summary = {"delta_per_feature": ["not-a-number"], "n_timepoints": 2}
    c = estimate_axis(rec, "topological_organization")
    assert c.status == "insufficient_data"
    assert c.value is None


def test_all_zero_change_is_undefined_not_zero_under_within_record():
    rec = _record(["topology.q_abs", "topology.q_net"], [0.0, 0.0])
    c = estimate_axis(rec, "topological_organization", normalization_mode="within_record")
    assert c.status == "insufficient_data"
    assert c.value is None


# ── Placeholder / proxy axis conservatism ───────────────────────────────────

@pytest.mark.parametrize("axis", sorted(PLACEHOLDER_AXES))
def test_placeholder_axes_return_insufficient_data(axis):
    rec = _record(
        ["topology.q_abs", "connectivity.mean_plv", "complexity.entropy"],
        [1.0, 1.0, 1.0],
    )
    c = estimate_axis(rec, axis)
    assert c.status == "insufficient_data"
    assert c.value is None
    assert c.confidence == "none"


def test_accessibility_proxy_stays_low_confidence_even_with_multiple_features():
    rec = _record(
        ["complexity.pcist_proxy", "transition.hysteresis", "transition.velocity"],
        [0.2, 0.1, 0.3],
        null_control_summary={"status": "passed"},
    )
    c = estimate_axis(rec, "accessibility_proxy")
    assert c.status == "estimated"
    assert c.confidence == "low"  # capped despite passing null + 3 features


def test_precision_stability_proxy_stays_low_confidence():
    rec = _record(
        ["qc.signal_quality", "transition.variance", "dynamics.kuramoto_r"],
        [0.2, 0.1, 0.3],
        null_control_summary={"status": "passed"},
    )
    c = estimate_axis(rec, "precision_stability_proxy")
    assert c.confidence == "low"


# ── Confidence policy ───────────────────────────────────────────────────────

def test_moderate_requires_multiple_features_and_passing_null():
    rec = _record(
        ["topology.q_abs", "topology.q_net"], [3.0, 2.0],
        null_control_summary={"status": "passed"},
    )
    c = estimate_axis(rec, "topological_organization")
    assert c.confidence == "moderate"


def test_single_feature_stays_low_even_with_passing_null():
    rec = _record(
        ["topology.q_abs"], [3.0], null_control_summary={"status": "passed"}
    )
    assert estimate_axis(rec, "topological_organization").confidence == "low"


def test_not_provided_null_control_stays_low():
    rec = _record(
        ["topology.q_abs", "topology.q_net"], [3.0, 2.0],
        null_control_summary={"status": "not_provided"},
    )
    assert estimate_axis(rec, "topological_organization").confidence == "low"


def test_high_confidence_is_unreachable_in_v1():
    for n in range(0, 12):
        for null_status in ("passed", "failed", "not_provided", "not_applicable"):
            got = assign_confidence(
                status="estimated",
                n_source_features=n,
                null_control_summary={"status": null_status},
                axis_max_confidence="high",
            )
            assert got != "high"


def test_cap_confidence_takes_the_weaker_level():
    assert cap_confidence("moderate", "low") == "low"
    assert cap_confidence("low", "moderate") == "low"


def test_non_estimated_status_always_has_no_confidence():
    for status in ("insufficient_data", "not_applicable", "failed_validation"):
        assert assign_confidence(status=status, n_source_features=5) == "none"


# ── Two-point limitation ────────────────────────────────────────────────────

def test_two_point_trajectory_limitation_is_recorded():
    rec = _record(["topology.q_abs"], [4.0])
    c = estimate_axis(rec, "topological_organization")
    assert any("Two-point" in lim for lim in c.limitations)


def test_multi_point_trajectory_omits_two_point_limitation():
    rec = _record(
        ["topology.q_abs"], [4.0],
        time_axis={"unit": "seconds", "n_samples": 50},
        delta_summary={
            "status": "ok", "delta_per_feature": [4.0],
            "mean_abs_delta": 4.0, "n_timepoints": 50, "n_features": 1,
        },
    )
    c = estimate_axis(rec, "topological_organization")
    assert not any("Two-point" in lim for lim in c.limitations)


# ── Normalization modes ─────────────────────────────────────────────────────

def test_raw_mode_returns_unnormalized_mean():
    rec = _record(["topology.q_abs", "topology.q_net"], [4.0, 2.0])
    c = estimate_axis(rec, "topological_organization", normalization_mode="raw")
    assert c.value == pytest.approx(3.0)


def test_zscore_mode_without_reference_is_insufficient_data():
    rec = _record(["topology.q_abs"], [4.0])
    c = estimate_axis(rec, "topological_organization",
                      normalization_mode="zscore_if_available")
    assert c.status == "insufficient_data"
    assert c.value is None


def test_zscore_mode_with_reference_stats_estimates():
    rec = _record(
        ["topology.q_abs"], [4.0],
        metadata={"feature_reference_stats": {"topology.q_abs": {"mean": 2.0, "std": 1.0}}},
    )
    c = estimate_axis(rec, "topological_organization",
                      normalization_mode="zscore_if_available")
    assert c.status == "estimated"
    assert c.value == pytest.approx(2.0)


def test_unknown_normalization_mode_raises():
    rec = _record(["topology.q_abs"], [4.0])
    with pytest.raises(NormalizationError):
        estimate_axis(rec, "topological_organization", normalization_mode="minmax")


# ── Governance inheritance ──────────────────────────────────────────────────

def test_output_claim_scope_never_exceeds_input():
    from phase_space.coordinate import CLAIM_SCOPE_ORDER

    for scope in CLAIM_SCOPE_ORDER:
        rec = _record(["topology.q_abs"], [4.0], claim_scope=scope)
        for c in estimate_coordinates(rec):
            assert CLAIM_SCOPE_ORDER.index(c.output_claim_scope) <= CLAIM_SCOPE_ORDER.index(
                scope
            )


def test_strong_input_scope_is_weakened_to_the_phase_space_ceiling():
    rec = _record(
        ["topology.q_abs"], [4.0],
        claim_scope="cross_subject_dataset_specific",
        record_level="cohort", subject_id=None,
        evidence_level="L4_cross_subject_dataset_specific",
    )
    c = estimate_axis(rec, "topological_organization")
    assert c.input_claim_scope == "cross_subject_dataset_specific"
    assert c.output_claim_scope == "exploratory_metric"


def test_input_evidence_level_is_recorded_not_promoted():
    rec = _record(["topology.q_abs"], [4.0], evidence_level="L2_single_subject_real_signal")
    c = estimate_axis(rec, "topological_organization")
    assert c.input_evidence_level == "L2_single_subject_real_signal"


def test_every_coordinate_carries_non_empty_limitations():
    rec = _record(["topology.q_abs"], [4.0])
    for c in estimate_coordinates(rec):
        assert c.limitations


def test_every_coordinate_records_source_provenance():
    rec = _record(["topology.q_abs"], [4.0])
    for c in estimate_coordinates(rec):
        assert c.provenance["source_transition_id"] == rec.transition_id
        assert c.provenance["source"] == "transitions.TransitionRecordV1"


def test_estimate_coordinates_covers_all_axes_by_default():
    rec = _record(["topology.q_abs"], [4.0])
    assert {c.axis for c in estimate_coordinates(rec)} == set(AXIS_NAMES)


def test_estimate_coordinates_honours_axis_subset():
    rec = _record(["topology.q_abs"], [4.0])
    coords = estimate_coordinates(rec, axes=["topological_organization"])
    assert len(coords) == 1 and coords[0].axis == "topological_organization"


def test_all_generated_coordinates_validate_clean():
    rec = _record(
        ["topology.q_abs", "connectivity.mean_plv", "transition.velocity"],
        [4.0, -0.2, 0.3],
    )
    for mode in ("raw", "within_record", "zscore_if_available"):
        for c in estimate_coordinates(rec, normalization_mode=mode):
            assert c.validate() == [], f"{c.axis}/{mode}: {c.validate()}"
