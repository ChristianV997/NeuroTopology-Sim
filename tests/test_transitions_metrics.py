"""Tests for transitions.metrics — generic, modality-agnostic trajectory summaries."""
from __future__ import annotations

import math

import pytest

from transitions.metrics import (
    dwell_time_summary,
    hysteresis_summary,
    label_balance_check,
    subject_pairing_check,
    trajectory_mean_delta,
    transition_acceleration,
    transition_variance,
    transition_velocity,
)

_TRAJECTORY = [[0.0, 1.0], [1.0, 1.5], [2.0, 2.0], [4.0, 3.0]]


# ── delta / velocity / acceleration / variance ──────────────────────────────

def test_trajectory_mean_delta_basic():
    result = trajectory_mean_delta(_TRAJECTORY)
    assert result["status"] == "ok"
    assert result["delta_per_feature"] == [4.0, 2.0]
    assert math.isclose(result["mean_abs_delta"], 3.0)


def test_trajectory_mean_delta_single_row_raises():
    with pytest.raises(ValueError):
        trajectory_mean_delta([[1.0, 2.0]])


def test_trajectory_mean_delta_empty_raises():
    with pytest.raises(ValueError):
        trajectory_mean_delta([])


def test_trajectory_mean_delta_nan_raises():
    with pytest.raises(ValueError):
        trajectory_mean_delta([[1.0, float("nan")], [2.0, 3.0]])


def test_transition_velocity_unit_steps():
    result = transition_velocity(_TRAJECTORY)
    assert result["status"] == "ok"
    assert result["n_steps"] == 3
    assert result["velocity_per_step"][0] == [1.0, 0.5]


def test_transition_velocity_with_timestamps():
    result = transition_velocity(_TRAJECTORY, timestamps=[0.0, 2.0, 4.0, 8.0])
    assert result["status"] == "ok"
    assert result["velocity_per_step"][0] == [0.5, 0.25]


def test_transition_velocity_mismatched_timestamps_raises():
    with pytest.raises(ValueError):
        transition_velocity(_TRAJECTORY, timestamps=[0.0, 1.0])


def test_transition_velocity_non_increasing_timestamps_raises():
    with pytest.raises(ValueError):
        transition_velocity(_TRAJECTORY, timestamps=[0.0, 1.0, 1.0, 3.0])


def test_transition_acceleration_ok_for_three_or_more_points():
    result = transition_acceleration(_TRAJECTORY)
    assert result["status"] == "ok"
    assert result["n_steps"] == 2


def test_transition_acceleration_insufficient_data_for_two_points():
    result = transition_acceleration([[0.0, 0.0], [1.0, 1.0]])
    assert result["status"] == "insufficient_data"
    assert "reason" in result


def test_transition_variance_basic():
    result = transition_variance(_TRAJECTORY)
    assert result["status"] == "ok"
    assert len(result["variance_per_feature"]) == 2


def test_malformed_trajectory_raises_clear_valueerror():
    with pytest.raises(ValueError, match="trajectory"):
        trajectory_mean_delta("not a trajectory")


def test_ragged_trajectory_raises():
    with pytest.raises(ValueError):
        trajectory_mean_delta([[1.0, 2.0], [1.0]])


# ── dwell time ────────────────────────────────────────────────────────────

def test_dwell_time_summary_basic():
    result = dwell_time_summary(["awake", "awake", "sedated", "sedated", "sedated", "awake"])
    assert result["status"] == "ok"
    assert result["n_runs"] == 3
    assert result["per_label"]["awake"]["n_runs"] == 2
    assert result["per_label"]["sedated"]["total_samples"] == 3


def test_dwell_time_summary_single_label():
    result = dwell_time_summary(["a", "a", "a"])
    assert result["per_label"]["a"]["n_runs"] == 1
    assert result["per_label"]["a"]["fraction_of_sequence"] == 1.0


def test_dwell_time_summary_empty_raises():
    with pytest.raises(ValueError):
        dwell_time_summary([])


def test_dwell_time_summary_with_sample_duration():
    result = dwell_time_summary(["a", "a", "b"], sample_duration_s=2.0)
    assert result["time_unit"] == "seconds"
    assert result["per_label"]["a"]["total_duration_s"] == 4.0


# ── hysteresis ────────────────────────────────────────────────────────────

def test_hysteresis_summary_returns_insufficient_data_when_no_recovery():
    result = hysteresis_summary(_TRAJECTORY, None)
    assert result["status"] == "insufficient_data"
    assert "reason" in result


def test_hysteresis_summary_returns_insufficient_data_for_empty_backward():
    result = hysteresis_summary(_TRAJECTORY, [])
    assert result["status"] == "insufficient_data"


def test_hysteresis_summary_ok_with_recovery_leg():
    backward = [[3.0, 3.0], [2.0, 2.0], [0.5, 1.2]]
    result = hysteresis_summary(_TRAJECTORY, backward)
    assert result["status"] == "ok"
    assert result["hysteresis_gap_mean"] >= 0.0


def test_hysteresis_summary_mismatched_feature_count_raises():
    with pytest.raises(ValueError):
        hysteresis_summary(_TRAJECTORY, [[1.0], [2.0]])


# ── label balance / subject pairing ──────────────────────────────────────

def test_label_balance_check_basic():
    result = label_balance_check(["a", "a", "b"])
    assert result["counts"] == {"a": 2, "b": 1}
    assert math.isclose(result["imbalance_ratio"], 2.0)


def test_label_balance_check_single_class_has_no_ratio():
    result = label_balance_check(["a", "a"])
    assert result["imbalance_ratio"] is None


def test_label_balance_check_empty_raises():
    with pytest.raises(ValueError):
        label_balance_check([])


def test_subject_pairing_check_finds_overlap():
    result = subject_pairing_check(["s1", "s2", "s3"], ["s2", "s3", "s4"])
    assert result["status"] == "ok"
    assert result["paired_subjects"] == ["s2", "s3"]
    assert result["unpaired_a"] == ["s1"]
    assert result["unpaired_b"] == ["s4"]


def test_subject_pairing_check_no_overlap_is_insufficient_data():
    result = subject_pairing_check(["s1"], ["s2"])
    assert result["status"] == "insufficient_data"
    assert result["n_paired"] == 0


def test_metrics_outputs_are_json_serializable():
    import json

    for result in (
        trajectory_mean_delta(_TRAJECTORY),
        transition_velocity(_TRAJECTORY),
        transition_acceleration(_TRAJECTORY),
        transition_variance(_TRAJECTORY),
        dwell_time_summary(["a", "b", "a"]),
        label_balance_check(["a", "b"]),
        subject_pairing_check(["s1"], ["s1"]),
    ):
        json.dumps(result)  # must not raise
