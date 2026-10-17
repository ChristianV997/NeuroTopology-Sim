"""Tests for synthetic operating-characteristics benchmark API."""

import math

import numpy as np
import pytest

from neurotopology_sim.experimental.benchmarks.synthetic_forward_roc import (
    BenchmarkError,
    assert_no_sample_overlap,
    compute_roc,
    fingerprint_sample_ids,
    prerequisite_gate_report,
    run_synthetic_operating_characteristics,
    select_threshold_on_calibration,
    SyntheticRunnerConfig,
    evaluate_held_out,
)


def test_input_validation():
    with pytest.raises(BenchmarkError):
        compute_roc([], [])
    with pytest.raises(BenchmarkError):
        compute_roc([1.0, 2.0], [1])
    with pytest.raises(BenchmarkError):
        compute_roc([1.0, float("nan")], [0, 1])
    with pytest.raises(BenchmarkError):
        compute_roc([1.0, 2.0], [0, 2])


def test_ties_and_midrank_auc():
    scores = [2.0, 2.0, 1.0, 3.0]
    labels = [1, 1, 0, 0]
    res = compute_roc(scores, labels)
    assert res["auc_status"] == "estimated"
    assert math.isclose(res["auc"], 0.5, abs_tol=1e-12)
    assert res["n_tied_groups"] >= 1


def test_endpoint_thresholds():
    res = compute_roc([0.1, 0.9], [0, 1], thresholds=[float("inf"), float("-inf")])
    plus = res["operating_points"][0]
    minus = res["operating_points"][1]
    assert plus["endpoint_note"] == "plus_inf_no_predicted_positives"
    assert plus["counts"]["tp"] == 0 and plus["counts"]["fp"] == 0
    assert minus["endpoint_note"] == "minus_inf_all_predicted_positives"
    assert minus["counts"]["tn"] == 0 and minus["counts"]["fn"] == 0


def test_single_class_undefined():
    res = compute_roc([1.0, 2.0, 3.0], [1, 1, 1])
    assert res["auc"] is None
    assert res["auc_status"] == "undefined_single_class"
    assert res["average_precision"] is None


def test_permutation_invariance():
    rng = np.random.default_rng(0)
    scores = rng.normal(size=40).tolist()
    labels = (rng.random(40) > 0.5).astype(int).tolist()
    base = compute_roc(scores, labels)
    perm = np.random.default_rng(1).permutation(40)
    s2 = [scores[i] for i in perm]
    y2 = [labels[i] for i in perm]
    other = compute_roc(s2, y2)
    assert math.isclose(base["auc"], other["auc"], abs_tol=1e-12)
    assert math.isclose(base["average_precision"], other["average_precision"], abs_tol=1e-12)


def test_auc_rank_parity_simple():
    res = compute_roc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1])
    assert math.isclose(res["auc"], 1.0, abs_tol=1e-12)


def test_wilson_reuse_and_rates():
    res = compute_roc([0.1, 0.2, 0.3, 0.9], [0, 0, 0, 1], thresholds=[0.5])
    op = res["operating_points"][0]
    assert op["tpr_wilson"] is not None
    assert op["tpr_wilson"]["n"] == 1
    assert op["fpr_wilson"]["n"] == 3
    assert op["tpr_status"] == "estimated"


def test_frozen_threshold_and_overlap():
    cal_scores = [0.1, 0.2, 0.8, 0.9]
    cal_labels = [0, 0, 1, 1]
    cal_ids = ["a", "b", "c", "d"]
    frozen = select_threshold_on_calibration(cal_scores, cal_labels, cal_ids, "youden")
    assert "threshold" in frozen
    assert frozen["calibration_sample_fingerprint"] == fingerprint_sample_ids(cal_ids)
    held = evaluate_held_out(
        [0.15, 0.85], [0, 1], ["e", "f"], frozen["threshold"],
        frozen["calibration_sample_fingerprint"], cal_ids,
    )
    assert held["threshold"] == frozen["threshold"]
    with pytest.raises(BenchmarkError, match="overlap"):
        assert_no_sample_overlap(cal_ids, ["a", "z"])


def test_prerequisite_gate_blocked():
    gate = prerequisite_gate_report({})
    assert gate["overall"] == "BLOCKED"
    assert len(gate["blocked_reasons"]) == 4


def test_injected_fixture_run_no_performance_publish():
    def gen(seed, n):
        rng = np.random.default_rng(seed)
        scores = rng.normal(size=n)
        labels = (rng.random(n) > 0.4).astype(int)
        ids = [f"s{seed}_{i}" for i in range(n)]
        return scores, labels, ids

    cfg = SyntheticRunnerConfig(
        seed=42, model_id="injected_fixture", null_id="none", config_hash="abc",
        n_calibration=20, n_evaluation=20, score_generator=gen,
    )
    out = run_synthetic_operating_characteristics(cfg, prerequisites={})
    assert out["status"] == "FIXTURE_RUN_COMPLETE"
    assert out["experiment_ran"] is True
    assert out["performance_published"] is False
    assert out["project_status"] == "HOLD / SYNTHETIC_ONLY"
    assert out["sample_size_gate"]["meets_target"] is False


def test_full_forward_model_refused_when_blocked():
    cfg = SyntheticRunnerConfig(
        seed=1, model_id="x", null_id="y", config_hash="z",
        n_calibration=10, n_evaluation=10,
    )
    out = run_synthetic_operating_characteristics(cfg, prerequisites={}, allow_full_forward_model=True)
    assert out["status"] == "BLOCKED"
    assert out["experiment_ran"] is False
