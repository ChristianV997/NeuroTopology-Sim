"""Direct regression tests for PR #426 calibration/evaluation and ROC contract.

HOLD / SYNTHETIC_ONLY. Imports the candidate. No mock, no skip.
SHA-256 fingerprints are tamper-evident consistency checks, not signatures.
"""

from __future__ import annotations

import math

import pytest

from analysis.binomial_planning.wilson import wilson_score_interval
from neurotopology_sim.experimental.benchmarks import synthetic_forward_roc as roc
from neurotopology_sim.experimental.benchmarks.synthetic_forward_roc import (
    SyntheticRunnerConfig,
)


def test_direct_import_is_candidate_module():
    assert roc.__file__.endswith("synthetic_forward_roc.py")
    assert roc.PROJECT_STATUS == "HOLD / SYNTHETIC_ONLY"
    assert "not external signatures" in roc.HASH_NOTE


def test_length_mismatch_empty_nonstring_duplicate_and_overlap():
    with pytest.raises(roc.BenchmarkError):
        roc.compute_roc([], [])
    with pytest.raises(roc.BenchmarkError):
        roc.select_threshold_on_calibration([0.1, 0.9], [0, 1], ["only"], "youden")
    with pytest.raises(roc.BenchmarkError):
        roc.select_threshold_on_calibration([0.1, 0.9], [0, 1], [1, "b"], "youden")
    with pytest.raises(roc.BenchmarkError):
        roc.fingerprint_sample_ids(["", "b"])
    with pytest.raises(roc.BenchmarkError, match="duplicate"):
        roc.select_threshold_on_calibration([0.1, 0.9], [0, 1], ["a", "a"], "youden")
    with pytest.raises(roc.BenchmarkError, match="overlap"):
        roc.assert_no_sample_overlap(["shared", "c2"], ["shared", "e2"])
    with pytest.raises(roc.BenchmarkError):
        roc.cluster_any_event_rate([0, 1], ["c0"])


def test_newline_join_collides_canonical_fingerprint_does_not():
    left = ["a\nb", "c"]
    right = ["a", "b\nc"]
    assert "\n".join(sorted(left)) == "\n".join(sorted(right))
    assert roc.fingerprint_sample_ids(left) != roc.fingerprint_sample_ids(right)


def test_frozen_threshold_immutability_and_digest_mismatch():
    scores = [0.1, 0.2, 0.8, 0.9]
    labels = [0, 0, 1, 1]
    ids = ["c1", "c2", "c3", "c4"]
    frozen = roc.select_threshold_on_calibration(scores, labels, ids, "youden")
    mutated = roc.select_threshold_on_calibration([0.9, 0.8, 0.2, 0.1], labels, ids, "youden")
    assert frozen["calibration_data_digest"] != mutated["calibration_data_digest"]
    first = roc.evaluate_held_out(
        [0.1, 0.9], [0, 1], ["e1", "e2"], frozen["threshold"],
        frozen["calibration_sample_fingerprint"], ids,
        calibration_data_digest=frozen["calibration_data_digest"],
    )
    second = roc.evaluate_held_out(
        [0.1, 0.9], [1, 0], ["e1", "e2"], frozen["threshold"],
        frozen["calibration_sample_fingerprint"], ids,
        calibration_data_digest=frozen["calibration_data_digest"],
    )
    assert first["threshold"] == second["threshold"] == frozen["threshold"]
    assert first["operating_point"]["counts"] != second["operating_point"]["counts"]
    with pytest.raises(roc.BenchmarkError, match="fingerprint"):
        roc.evaluate_held_out(
            [0.1, 0.9], [0, 1], ["e1", "e2"], frozen["threshold"],
            "not-the-fingerprint", ids,
        )
    with pytest.raises(roc.BenchmarkError, match="digest"):
        roc.evaluate_held_out(
            [0.1, 0.9], [0, 1], ["e1", "e2"], frozen["threshold"],
            frozen["calibration_sample_fingerprint"], ids,
            calibration_data_digest=mutated["calibration_data_digest"],
        )
    assert "signature" in frozen["hash_note"]


def test_threshold_uses_calibration_only_and_rejects_overlap():
    frozen = roc.select_threshold_on_calibration(
        [0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], ["c1", "c2", "c3", "c4"], "youden"
    )
    held = roc.evaluate_held_out(
        [0.15, 0.25, 0.35, 0.95], [0, 0, 0, 1], ["e1", "e2", "e3", "e4"],
        frozen["threshold"], frozen["calibration_sample_fingerprint"],
        ["c1", "c2", "c3", "c4"],
    )
    assert held["threshold"] == frozen["threshold"]
    assert held["project_status"] == "HOLD / SYNTHETIC_ONLY"
    with pytest.raises(roc.BenchmarkError, match="overlap"):
        roc.evaluate_held_out(
            [0.2, 0.8], [0, 1], ["c1", "e2"], frozen["threshold"],
            frozen["calibration_sample_fingerprint"], ["c1", "c2", "c3", "c4"],
        )


def test_cluster_interval_uses_cluster_denominator():
    labels = [0] * 200
    cluster_ids = [f"c{i // 20}" for i in range(200)]
    report = roc.cluster_any_event_rate(labels, cluster_ids)
    assert report["n_clusters"] == 10
    assert report["wilson"]["n"] == 10
    assert report["k"] == 0
    assert report["independent_statistical_unit"] == "cluster"
    window = wilson_score_interval(0, 200)
    assert report["wilson"]["upper"] != window.upper
    assert report["wilson"]["n"] != 200


def test_underpowered_gate_is_smoke_only_no_verdict():
    def gen(seed, n):
        scores = [0.1, 0.9] * (n // 2)
        labels = [0, 1] * (n // 2)
        ids = [f"s{seed}_{i}" for i in range(n)]
        return scores, labels, ids

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
    assert "validated" not in str(out).lower()


def test_tie_aware_auc_and_stepwise_ap():
    auc = roc.compute_roc([0.1, 0.4, 0.4, 0.8], [0, 0, 1, 1])
    assert math.isclose(auc["auc"], 0.875)
    ap = roc.compute_roc([0.9, 0.8, 0.7, 0.1], [1, 0, 1, 0])
    assert math.isclose(ap["average_precision"], 5.0 / 6.0)
    trap = 0.5 * (1.0 + 2.0 / 3.0) * 0.5 + 0.5 * (2.0 / 3.0 + 0.5) * 0.5
    assert not math.isclose(ap["average_precision"], trap)


def test_endpoints_imbalance_and_undefined_rates():
    ends = roc.compute_roc([0.1, 0.9], [0, 1], thresholds=[float("inf"), float("-inf")])
    assert ends["operating_points"][0]["endpoint_note"] == "plus_inf_no_predicted_positives"
    assert ends["operating_points"][1]["counts"]["tn"] == 0
    single = roc.compute_roc([1.0, 2.0, 3.0], [1, 1, 1])
    assert single["auc"] is None
    assert single["auc_status"] == "undefined_single_class"
    op = roc.operating_point([1.0, 2.0], [1, 1], float("inf"))
    assert op["precision"] is None
    assert op["precision_status"] == "undefined_zero_denominator"


def test_wilson_parity_with_pr405():
    result = roc.compute_roc([0.1, 0.2, 0.3, 0.9], [0, 0, 0, 1], thresholds=[0.5])
    op = result["operating_points"][0]
    expected = wilson_score_interval(op["tpr_wilson"]["k"], op["tpr_wilson"]["n"])
    assert math.isclose(op["tpr_wilson"]["upper"], expected.upper)
    assert op["tpr_wilson"]["k"] == expected.k and op["tpr_wilson"]["n"] == expected.n
    assert wilson_score_interval(0, 0).status == "unavailable_zero_trials"
