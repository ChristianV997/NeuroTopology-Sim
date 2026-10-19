"""Adversarial contract suite for PR #426 calibration/evaluation and ROC.

HOLD / SYNTHETIC_ONLY. Direct import of the candidate. No mock, no skip.
SHA-256 fingerprints are consistency checks, not signatures.

Candidate head under test is recorded by the runner; this file does not
vendor production code.
"""

from __future__ import annotations

import math

import pytest

from analysis.binomial_planning.wilson import wilson_score_interval
from neurotopology_sim.experimental.benchmarks import synthetic_forward_roc as roc
from neurotopology_sim.experimental.benchmarks.synthetic_forward_roc import (
    SyntheticRunnerConfig,
)


def test_direct_import_and_status():
    assert roc.__file__.endswith("synthetic_forward_roc.py")
    assert roc.PROJECT_STATUS == "HOLD / SYNTHETIC_ONLY"
    assert "not external signatures" in roc.HASH_NOTE


def test_length_nan_inf_and_label_strictness():
    with pytest.raises(roc.BenchmarkError):
        roc.compute_roc([], [])
    with pytest.raises(roc.BenchmarkError):
        roc.compute_roc([0.1, 0.2], [0])
    with pytest.raises(roc.BenchmarkError):
        roc.compute_roc([0.1, float("nan")], [0, 1])
    with pytest.raises(roc.BenchmarkError):
        roc.compute_roc([0.1, float("inf")], [0, 1])
    with pytest.raises(roc.BenchmarkError):
        roc.compute_roc([0.1, 0.2], [0, 2])
    # Written contract accepts bool labels and converts them to 0/1.
    accepted = roc.compute_roc([0.1, 0.9], [False, True])
    assert accepted["auc_status"] == "estimated"


def test_ids_must_be_nonempty_unique_strings():
    with pytest.raises(roc.BenchmarkError):
        roc.select_threshold_on_calibration([0.1, 0.9], [0, 1], [1, "b"], "youden")
    with pytest.raises(roc.BenchmarkError):
        roc.fingerprint_sample_ids(["", "b"])
    with pytest.raises(roc.BenchmarkError, match="duplicate"):
        roc.select_threshold_on_calibration([0.1, 0.9], [0, 1], ["a", "a"], "youden")
    with pytest.raises(roc.BenchmarkError):
        roc.select_threshold_on_calibration([0.1, 0.9], [0, 1], ["only"], "youden")


def test_overlap_is_raw_id_not_hash_only():
    with pytest.raises(roc.BenchmarkError, match="overlap"):
        roc.assert_no_sample_overlap(["shared", "c2"], ["shared", "e2"])
    left = roc.fingerprint_sample_ids(["shared", "c2"])
    right = roc.fingerprint_sample_ids(["shared", "e2"])
    assert left != right
    with pytest.raises(roc.BenchmarkError, match="overlap"):
        roc.evaluate_held_out(
            [0.2, 0.8], [0, 1], ["shared", "e2"], 0.5, left, ["shared", "c2"]
        )


def test_newline_collision_canonical_fingerprint_distinguishes():
    left = ["a\nb", "c"]
    right = ["a", "b\nc"]
    assert "\n".join(sorted(left)) == "\n".join(sorted(right))
    assert roc.fingerprint_sample_ids(left) != roc.fingerprint_sample_ids(right)


def test_frozen_record_changes_with_ids_scores_labels_and_rule():
    base = roc.select_threshold_on_calibration(
        [0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], ["c1", "c2", "c3", "c4"], "youden"
    )
    other_ids = roc.select_threshold_on_calibration(
        [0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], ["d1", "d2", "d3", "d4"], "youden"
    )
    other_scores = roc.select_threshold_on_calibration(
        [0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1], ["c1", "c2", "c3", "c4"], "youden"
    )
    other_labels = roc.select_threshold_on_calibration(
        [0.1, 0.2, 0.8, 0.9], [1, 0, 0, 1], ["c1", "c2", "c3", "c4"], "youden"
    )
    other_rule = roc.select_threshold_on_calibration(
        [0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], ["c1", "c2", "c3", "c4"], "f1"
    )
    assert base["calibration_sample_fingerprint"] != other_ids["calibration_sample_fingerprint"]
    assert base["calibration_data_digest"] != other_scores["calibration_data_digest"]
    assert base["calibration_data_digest"] != other_labels["calibration_data_digest"]
    assert other_rule["criterion"] == "f1"
    assert "signature" in base["hash_note"]


def test_caller_supplied_digest_bypasses_recomputation():
    """Reproduce the current bypass: a mismatched digest is accepted."""
    frozen = roc.select_threshold_on_calibration(
        [0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], ["c1", "c2", "c3", "c4"], "youden"
    )
    mutated = roc.select_threshold_on_calibration(
        [0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1], ["c1", "c2", "c3", "c4"], "youden"
    )
    assert frozen["calibration_data_digest"] != mutated["calibration_data_digest"]
    accepted = roc.evaluate_held_out(
        [0.1, 0.9], [0, 1], ["e1", "e2"], frozen["threshold"],
        frozen["calibration_sample_fingerprint"], ["c1", "c2", "c3", "c4"],
        calibration_data_digest=mutated["calibration_data_digest"],
    )
    assert accepted["threshold"] == frozen["threshold"]
    assert accepted["calibration_fingerprint"] == frozen["calibration_sample_fingerprint"]
    with pytest.raises(roc.BenchmarkError, match="fingerprint"):
        roc.evaluate_held_out(
            [0.1, 0.9], [0, 1], ["e1", "e2"], frozen["threshold"],
            "not-the-fingerprint", ["c1", "c2", "c3", "c4"],
        )


def test_evaluation_cannot_move_frozen_threshold():
    frozen = roc.select_threshold_on_calibration(
        [0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], ["c1", "c2", "c3", "c4"], "youden"
    )
    first = roc.evaluate_held_out(
        [0.1, 0.9], [0, 1], ["e1", "e2"], frozen["threshold"],
        frozen["calibration_sample_fingerprint"], ["c1", "c2", "c3", "c4"],
    )
    second = roc.evaluate_held_out(
        [0.1, 0.9], [1, 0], ["e1", "e2"], frozen["threshold"],
        frozen["calibration_sample_fingerprint"], ["c1", "c2", "c3", "c4"],
    )
    assert first["threshold"] == second["threshold"] == frozen["threshold"]
    assert first["operating_point"]["counts"] != second["operating_point"]["counts"]


def test_tie_aware_auc_and_stepwise_ap():
    auc = roc.compute_roc([0.1, 0.4, 0.4, 0.8], [0, 0, 1, 1])
    assert math.isclose(auc["auc"], 0.875)
    assert auc["n_tied_groups"] >= 1
    ap = roc.compute_roc([0.9, 0.8, 0.7, 0.1], [1, 0, 1, 0])
    assert math.isclose(ap["average_precision"], 5.0 / 6.0)
    trap = 0.5 * (1.0 + 2.0 / 3.0) * 0.5 + 0.5 * (2.0 / 3.0 + 0.5) * 0.5
    assert not math.isclose(ap["average_precision"], trap)


def test_endpoints_one_class_and_zero_denominator():
    ends = roc.compute_roc([0.1, 0.9], [0, 1], thresholds=[float("inf"), float("-inf")])
    assert ends["operating_points"][0]["endpoint_note"] == "plus_inf_no_predicted_positives"
    assert ends["operating_points"][0]["counts"]["tp"] == 0
    assert ends["operating_points"][1]["counts"]["tn"] == 0
    single = roc.compute_roc([1.0, 2.0, 3.0], [1, 1, 1])
    assert single["auc"] is None
    assert single["auc_status"] == "undefined_single_class"
    op = roc.operating_point([1.0, 2.0], [1, 1], float("inf"))
    assert op["precision"] is None
    assert op["precision_status"] == "undefined_zero_denominator"


def test_wilson_parity_with_merged_pr405():
    result = roc.compute_roc([0.1, 0.2, 0.3, 0.9], [0, 0, 0, 1], thresholds=[0.5])
    op = result["operating_points"][0]
    expected = wilson_score_interval(op["tpr_wilson"]["k"], op["tpr_wilson"]["n"])
    assert math.isclose(op["tpr_wilson"]["upper"], expected.upper)
    assert op["tpr_wilson"]["k"] == expected.k
    assert wilson_score_interval(0, 0).status == "unavailable_zero_trials"


def test_cluster_interval_is_not_a_window_interval():
    labels = [0] * 200
    scores = [0.1] * 200
    cluster_ids = [f"c{i // 20}" for i in range(200)]
    report = roc.cluster_any_event_rate(labels, cluster_ids)
    assert report["n_clusters"] == 10
    assert report["wilson"]["n"] == 10
    assert report["k"] == 0
    assert report["independent_statistical_unit"] == "cluster"
    window = wilson_score_interval(0, 200)
    assert report["wilson"]["upper"] != window.upper
    roc_out = roc.compute_roc(scores, labels, cluster_ids=cluster_ids)
    cluster_op = roc_out["operating_points"][0]["cluster_any_event"]
    assert cluster_op["n_clusters"] == 10
    assert cluster_op["wilson"]["n"] != roc_out["n_negative"]
    # Direct operating_point on a list currently raises; compute_roc is the validated path.
    with pytest.raises(TypeError):
        roc.operating_point(scores, labels, 0.5, cluster_ids=cluster_ids)


def test_underpowered_gate_publishes_no_verdict():
    def gen(seed, n):
        return [0.1, 0.9] * (n // 2), [0, 1] * (n // 2), [f"s{seed}_{i}" for i in range(n)]

    out = roc.run_synthetic_operating_characteristics(
        SyntheticRunnerConfig(
            seed=1, model_id="smoke", null_id="none", config_hash="abc",
            n_calibration=20, n_evaluation=20, score_generator=gen,
        ),
        prerequisites={},
    )
    assert out["sample_size_gate"]["meets_target"] is False
    assert out["performance_published"] is False
    assert out["project_status"] == "HOLD / SYNTHETIC_ONLY"
    assert "PASS" not in str(out["status"])
