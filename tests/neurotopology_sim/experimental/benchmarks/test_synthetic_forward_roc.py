"""Tests for synthetic operating-characteristics benchmark API."""

import math

import numpy as np
import pytest

from neurotopology_sim.experimental.benchmarks.synthetic_forward_roc import (
    BenchmarkError,
    assert_no_sample_overlap,
    compute_roc,
    confusion_at_threshold,
    json_safe,
    fingerprint_sample_ids,
    operating_point,
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
    with pytest.raises(BenchmarkError, match="one-dimensional"):
        compute_roc(1.0, 1)
    with pytest.raises(BenchmarkError, match="sample_ids"):
        select_threshold_on_calibration([0.1, 0.9], [0, 1], "ab", "youden")
    with pytest.raises(BenchmarkError, match="threshold"):
        compute_roc([0.1, 0.9], [0, 1], thresholds=[float("nan")])


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


def test_clustered_roc_reports_descriptive_window_rates_only():
    labels = [0, 1] * 10
    scores = [0.1, 0.9] * 10
    cluster_ids = [f"cluster-{i // 2}" for i in range(len(labels))]

    result = compute_roc(scores, labels, thresholds=[0.5], cluster_ids=cluster_ids)
    operating = result["operating_points"][0]

    assert operating["tpr"] == 1.0
    assert operating["fpr"] == 0.0
    assert operating["tpr_status"] == "point_estimate_clustered"
    assert operating["fpr_status"] == "point_estimate_clustered"
    assert operating["precision_status"] == "point_estimate_clustered"
    assert operating["tpr_wilson"] is None
    assert operating["fpr_wilson"] is None
    assert operating["precision_wilson"] is None
    assert operating["independent_statistical_unit"] == "observation"
    assert operating["cluster_any_event"]["wilson"]["n"] == 10
    assert result["independent_statistical_unit"] == "observation"
    assert "not treated as independent" in result["clustered_evaluation_note"]


def test_clustered_undefined_rates_keep_undefined_statuses():
    result = compute_roc(
        [0.1, 0.9], [1, 1], thresholds=[float("inf")],
        cluster_ids=["a", "b"],
    )
    operating = result["operating_points"][0]
    assert operating["tpr_status"] == "point_estimate_clustered"
    assert operating["fpr"] is None
    assert operating["fpr_status"] == "undefined_zero_denominator"
    assert operating["precision"] is None
    assert operating["precision_status"] == "undefined_zero_denominator"
    assert operating["tpr_wilson"] is None
    assert operating["fpr_wilson"] is None
    assert operating["precision_wilson"] is None


def test_cluster_id_iterable_is_normalized_once():
    result = compute_roc(
        [0.1, 0.9], [0, 1], thresholds=[0.5],
        cluster_ids=iter(["cluster-a", "cluster-b"]),
    )
    assert result["operating_points"][0]["cluster_any_event"]["n_clusters"] == 2


def test_operating_point_validates_direct_inputs_and_thresholds():
    endpoint = operating_point([1.0, 2.0], [1, 1], float("inf"))
    assert endpoint["counts"]["n_positive"] == 2
    with pytest.raises(BenchmarkError, match="threshold"):
        operating_point([1.0, 2.0], [1, 1], float("nan"))


def test_confusion_at_threshold_validates_direct_inputs():
    with pytest.raises(BenchmarkError, match="one-dimensional"):
        confusion_at_threshold([[1.0]], [1], 0.5)
    with pytest.raises(BenchmarkError, match="threshold"):
        confusion_at_threshold([1.0], [1], float("nan"))


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

    iter_held = evaluate_held_out(
        [0.15, 0.85], [0, 1], iter(["e", "f"]), frozen["threshold"],
        frozen["calibration_sample_fingerprint"], iter(cal_ids),
    )
    assert iter_held["threshold"] == frozen["threshold"]


def test_threshold_selection_tie_break_is_explicit_and_deterministic():
    frozen = select_threshold_on_calibration(
        [0.1, 0.2, 0.3, 0.4], [0, 1, 0, 1], ["a", "b", "c", "d"], "youden"
    )
    assert frozen["threshold"] == 0.4
    assert "ties retain the highest non-endpoint threshold" in frozen["selection_rule"]


def test_calibration_digest_requires_and_verifies_bound_bundle():
    cal_scores = [0.1, 0.2, 0.8, 0.9]
    cal_labels = [0, 0, 1, 1]
    cal_ids = ["a", "b", "c", "d"]
    frozen = select_threshold_on_calibration(cal_scores, cal_labels, cal_ids, "youden")
    held_out = ([0.15, 0.85], [0, 1], ["e", "f"])
    bundle = {"scores": cal_scores, "labels": cal_labels}

    with pytest.raises(BenchmarkError, match="bundle"):
        evaluate_held_out(
            *held_out,
            frozen["threshold"],
            frozen["calibration_sample_fingerprint"],
            cal_ids,
            calibration_data_digest=frozen["calibration_data_digest"],
        )

    accepted = evaluate_held_out(
        *held_out,
        frozen["threshold"],
        frozen["calibration_sample_fingerprint"],
        cal_ids,
        calibration_data_digest=frozen["calibration_data_digest"],
        frozen_calibration_record=frozen,
        calibration_bundle=bundle,
    )
    assert accepted["threshold"] == frozen["threshold"]

    with pytest.raises(BenchmarkError, match="mismatch"):
        evaluate_held_out(
            *held_out,
            frozen["threshold"],
            frozen["calibration_sample_fingerprint"],
            cal_ids,
            calibration_data_digest="0" * 64,
            frozen_calibration_record=frozen,
            calibration_bundle=bundle,
        )

    altered_bundle = {"scores": [0.9, 0.8, 0.2, 0.1], "labels": cal_labels}
    with pytest.raises(BenchmarkError, match="mismatch"):
        evaluate_held_out(
            *held_out,
            frozen["threshold"],
            frozen["calibration_sample_fingerprint"],
            cal_ids,
            calibration_data_digest=frozen["calibration_data_digest"],
            frozen_calibration_record=frozen,
            calibration_bundle=altered_bundle,
        )

    altered_record = dict(frozen, threshold=float(frozen["threshold"]) + 1.0)
    with pytest.raises(BenchmarkError, match="frozen calibration record mismatch"):
        evaluate_held_out(
            *held_out,
            frozen["threshold"],
            frozen["calibration_sample_fingerprint"],
            cal_ids,
            calibration_data_digest=frozen["calibration_data_digest"],
            frozen_calibration_record=altered_record,
            calibration_bundle=bundle,
        )

    altered_rule = dict(frozen, selection_rule="caller-modified selection rule")
    with pytest.raises(BenchmarkError, match="frozen calibration record mismatch"):
        evaluate_held_out(
            *held_out,
            frozen["threshold"],
            frozen["calibration_sample_fingerprint"],
            cal_ids,
            calibration_data_digest=frozen["calibration_data_digest"],
            frozen_calibration_record=altered_rule,
            calibration_bundle=bundle,
        )


def test_prerequisite_gate_blocked():
    gate = prerequisite_gate_report({})
    assert gate["overall"] == "BLOCKED"
    assert len(gate["blocked_reasons"]) == 4


def test_prerequisite_gate_requires_explicit_boolean_true():
    names = (
        "source_pinned_four_sphere_model",
        "valid_planar_geometry_and_winding_hodge",
        "csd_conformance",
        "phase_surrogate_calibration",
    )
    gate = prerequisite_gate_report({name: "true" for name in names})
    assert gate["overall"] == "BLOCKED"
    assert gate["blocked_reasons"] == list(names)
    assert all(gate["component_status"][name] == "invalid" for name in names)

    ready = prerequisite_gate_report({name: True for name in names})
    assert ready["overall"] == "READY_FOR_FORWARD_MODEL_ROC"


def test_json_safe_encodes_explicit_infinite_threshold_endpoints():
    result = compute_roc([0.1, 0.9], [0, 1])
    encoded = json_safe(result)
    assert '"threshold": "+Infinity"' in encoded
    assert '"threshold": "-Infinity"' in encoded


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


def test_runner_rejects_noninteger_sample_counts():
    cfg = SyntheticRunnerConfig(
        seed=1,
        model_id="fixture",
        null_id="none",
        config_hash="cfg",
        n_calibration=True,
        n_evaluation=10,
        score_generator=lambda seed, n: ([0.1, 0.9], [0, 1], ["a", "b"]),
    )
    with pytest.raises(BenchmarkError, match="positive integers"):
        run_synthetic_operating_characteristics(cfg, prerequisites={})
