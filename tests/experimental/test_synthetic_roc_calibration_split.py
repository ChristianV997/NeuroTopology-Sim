"""Direct regression tests for PR #426 synthetic ROC / split-integrity API.

HOLD / SYNTHETIC_ONLY. Imports the candidate implementation. No mock, no skip.
Hashes are content fingerprints, not digital signatures.
"""

from __future__ import annotations

import hashlib
import json
import math

import pytest

from analysis.binomial_planning.wilson import wilson_score_interval
from neurotopology_sim.experimental.benchmarks import synthetic_forward_roc as roc


def _canonical_fingerprint(ids):
    payload = json.dumps(list(ids), sort_keys=False, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_direct_import_is_candidate_module():
    assert roc.compute_roc is not None
    assert roc.__file__.endswith("synthetic_forward_roc.py")
    assert roc.PROJECT_STATUS == "HOLD / SYNTHETIC_ONLY"


def test_unequal_lengths_and_empty_and_nonfinite():
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
    with pytest.raises(roc.BenchmarkError):
        roc.evaluate_held_out([0.1, 0.2], [0, 1], ["only-one"], 0.5, "fp", ["c1"])


def test_non_string_and_duplicate_ids():
    frozen = roc.select_threshold_on_calibration([0.1, 0.9], [0, 1], [1, "1"], "youden")
    assert frozen["calibration_sample_fingerprint"] == roc.fingerprint_sample_ids([1, "1"])
    with pytest.raises(roc.BenchmarkError, match="overlap"):
        roc.assert_no_sample_overlap(["dup", "dup"], ["dup"])


def test_raw_calibration_evaluation_overlap_rejected():
    frozen = roc.select_threshold_on_calibration([0.1, 0.9], [0, 1], ["shared", "c2"], "youden")
    with pytest.raises(roc.BenchmarkError, match="overlap"):
        roc.evaluate_held_out([0.2, 0.8], [0, 1], ["shared", "e2"], frozen["threshold"], frozen["calibration_sample_fingerprint"], ["shared", "c2"])


def test_newline_collision_requires_canonical_json():
    left = ["a\nb", "c"]
    right = ["a", "b\nc"]
    assert "\n".join(sorted(left)) == "\n".join(sorted(right))
    assert _canonical_fingerprint(left) != _canonical_fingerprint(right)
    # Candidate must not use a newline-join fingerprint for these ids.
    assert roc.fingerprint_sample_ids(left) != roc.fingerprint_sample_ids(right)


def test_frozen_threshold_immutability_and_fingerprint_mismatch():
    frozen = roc.select_threshold_on_calibration([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], ["c1", "c2", "c3", "c4"], "youden")
    first = roc.evaluate_held_out([0.1, 0.9], [0, 1], ["e1", "e2"], frozen["threshold"], frozen["calibration_sample_fingerprint"], ["c1", "c2", "c3", "c4"])
    second = roc.evaluate_held_out([0.1, 0.9], [1, 0], ["e1", "e2"], frozen["threshold"], frozen["calibration_sample_fingerprint"], ["c1", "c2", "c3", "c4"])
    assert first["threshold"] == second["threshold"] == frozen["threshold"]
    assert first["operating_point"]["counts"] != second["operating_point"]["counts"]
    with pytest.raises(roc.BenchmarkError, match="fingerprint"):
        roc.evaluate_held_out([0.1, 0.9], [0, 1], ["e1", "e2"], frozen["threshold"], "not-the-fingerprint", ["c1", "c2", "c3", "c4"])
    # Fingerprint is a content hash, not a digital signature.
    assert len(frozen["calibration_sample_fingerprint"]) == 64


def test_threshold_selected_on_calibration_only_and_leakage_fixture():
    cal_scores = [0.1, 0.2, 0.8, 0.9]
    cal_labels = [0, 0, 1, 1]
    cal_ids = ["c1", "c2", "c3", "c4"]
    frozen = roc.select_threshold_on_calibration(cal_scores, cal_labels, cal_ids, "youden")
    held = roc.evaluate_held_out([0.15, 0.25, 0.35, 0.95], [0, 0, 0, 1], ["e1", "e2", "e3", "e4"], frozen["threshold"], frozen["calibration_sample_fingerprint"], cal_ids)
    cal_eval = roc.evaluate_held_out(cal_scores, cal_labels, ["x1", "x2", "x3", "x4"], frozen["threshold"], frozen["calibration_sample_fingerprint"], cal_ids)
    assert held["operating_point"]["counts"] != cal_eval["operating_point"]["counts"]
    assert held["threshold"] == frozen["threshold"]
    assert held["project_status"] == "HOLD / SYNTHETIC_ONLY"
    assert "sample_overlap_check_does_not_prove_no_leakage" in held["warnings"]


def test_tie_aware_auc_example():
    result = roc.compute_roc([0.1, 0.4, 0.4, 0.8], [0, 0, 1, 1])
    assert result["auc_status"] == "estimated"
    assert math.isclose(result["auc"], 0.875)


def test_stepwise_average_precision_not_trapezoid():
    result = roc.compute_roc([0.9, 0.8, 0.7, 0.1], [1, 0, 1, 0])
    assert math.isclose(result["average_precision"], 5.0 / 6.0)
    # Trapezoidal PR area on the same points is not 5/6.
    trap = 0.5 * (1.0 + 2.0 / 3.0) * 0.5 + 0.5 * (2.0 / 3.0 + 0.5) * 0.5
    assert not math.isclose(result["average_precision"], trap)


def test_single_class_and_zero_denominator_undefined():
    result = roc.compute_roc([1.0, 2.0, 3.0], [1, 1, 1])
    assert result["auc"] is None
    assert result["auc_status"] == "undefined_single_class"
    assert result["average_precision"] is None
    op = roc.operating_point([1.0, 2.0], [1, 1], float("inf"))
    assert op["tpr"] is None or op["precision_status"] == "undefined_zero_denominator"
    assert op["precision"] is None
    assert op["precision_status"] == "undefined_zero_denominator"


def test_wilson_parity_with_pr405():
    result = roc.compute_roc([0.1, 0.2, 0.3, 0.9], [0, 0, 0, 1], thresholds=[0.5])
    op = result["operating_points"][0]
    expected = wilson_score_interval(op["tpr_wilson"]["k"], op["tpr_wilson"]["n"])
    assert math.isclose(op["tpr_wilson"]["upper"], expected.upper)
    zero = wilson_score_interval(0, 0)
    assert zero.status == "unavailable_zero_trials"


def test_cluster_estimand_uses_cluster_count_not_window_count():
    # 200 windows in 10 independent clusters, zero events.
    # cluster_any_event_rate must use n=10. A pooled window rate must not
    # receive an ordinary Wilson interval as if the 200 windows were independent.
    if not hasattr(roc, "cluster_any_event_rate"):
        pytest.fail("candidate lacks cluster_any_event_rate; ordinary Wilson on 200 windows would be unjustified")
    cluster_ids = [f"c{i // 20}" for i in range(200)]
    events = [0] * 200
    report = roc.cluster_any_event_rate(events, cluster_ids)
    assert report["n"] == 10
    assert report["n"] != 200
    assert report["wilson"]["n"] == 10
    pooled = wilson_score_interval(0, 200)
    assert report["wilson"]["upper"] != pooled.upper or report.get("pooled_wilson_rejected") is True
