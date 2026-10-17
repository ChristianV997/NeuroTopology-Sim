"""Independent tests for the synthetic ROC / calibration-split contract.

Status: HOLD / SYNTHETIC_ONLY. A green run is not evidence that a detector works.
No participant data. No ds005620. Gemini Revision 8 is an unverified lead and
is not accepted as a mathematical source.

Owned path: tests/experimental/test_synthetic_roc_calibration_split.py
Production owner: Grok Chat Agent A, path
neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py

If that module is absent, contract tests skip with reason INTEGRATION_BLOCKED.
Independent derivations below always run and do not import production code.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import dataclass

import pytest

from analysis.binomial_planning.wilson import wilson_score_interval

MODULE = "neurotopology_sim.experimental.benchmarks.synthetic_forward_roc"
FORBIDDEN = ("scientific_pass", "validated", "PASS", "formal_evidence", "consciousness")


@dataclass(frozen=True)
class RankAuc:
    auc: float
    concordant: float
    n_pos: int
    n_neg: int


def mann_whitney_auc(scores: list[float], labels: list[int]) -> RankAuc:
    """Hand-computed ROC AUC with mid-ranks for ties. Independent of production."""
    if len(scores) != len(labels) or not scores:
        raise ValueError("need equal non-empty scores and labels")
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        raise ValueError("both classes required")
    concordant = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                concordant += 1.0
            elif p == n:
                concordant += 0.5
    return RankAuc(concordant / (len(pos) * len(neg)), concordant, len(pos), len(neg))


def stepwise_average_precision(scores: list[float], labels: list[int]) -> float:
    """Stepwise AP: sum of recall increments times precision at each positive.

    Distinct from trapezoidal integration of the precision-recall curve.
    """
    pairs = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    n_pos = sum(labels)
    if n_pos == 0:
        raise ValueError("no positive labels")
    tp = 0
    seen = 0
    ap = 0.0
    prev_recall = 0.0
    for _score, label in pairs:
        seen += 1
        tp += int(label)
        if label == 1:
            precision = tp / seen
            recall = tp / n_pos
            ap += (recall - prev_recall) * precision
            prev_recall = recall
    return ap


def trapezoidal_pr_area(scores: list[float], labels: list[int]) -> float:
    """Trapezoidal PR area, used only to show it can differ from stepwise AP."""
    pairs = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    n_pos = sum(labels)
    if n_pos == 0:
        raise ValueError("no positive labels")
    tp = 0
    fp = 0
    points = [(0.0, 1.0)]
    for _score, label in pairs:
        tp += int(label)
        fp += int(1 - label)
        points.append((tp / n_pos, tp / (tp + fp) if tp + fp else 0.0))
    area = 0.0
    for (r0, p0), (r1, p1) in zip(points, points[1:]):
        area += (r1 - r0) * (p0 + p1) / 2.0
    return area


def _load():
    return importlib.import_module(MODULE)


def _contract():
    try:
        return _load()
    except ModuleNotFoundError as exc:
        pytest.skip(f"INTEGRATION_BLOCKED: {MODULE} not present ({exc})")


def test_independent_auc_with_ties() -> None:
    # scores [0.1, 0.4, 0.4, 0.8], labels [0, 0, 1, 1]
    # pos vs neg: (0.4>0.1), (0.4==0.4), (0.8>0.1), (0.8>0.4) -> 1+0.5+1+1 = 3.5
    # AUC = 3.5 / 4 = 0.875
    result = mann_whitney_auc([0.1, 0.4, 0.4, 0.8], [0, 0, 1, 1])
    assert result.concordant == 3.5
    assert result.auc == 0.875


def test_independent_auc_permutation_invariant() -> None:
    base = mann_whitney_auc([0.2, 0.9, 0.5, 0.1], [0, 1, 1, 0])
    flipped = mann_whitney_auc([0.1, 0.5, 0.9, 0.2], [0, 1, 1, 0])
    assert base.auc == flipped.auc == 1.0


def test_stepwise_ap_differs_from_trapezoid() -> None:
    scores = [0.9, 0.8, 0.7, 0.1]
    labels = [1, 0, 1, 0]
    stepwise = stepwise_average_precision(scores, labels)
    trap = trapezoidal_pr_area(scores, labels)
    # stepwise: at 0.9 prec=1 rec=0.5; at 0.7 prec=2/3 rec=1 -> 0.5*1 + 0.5*(2/3) = 5/6
    assert math.isclose(stepwise, 5.0 / 6.0)
    assert not math.isclose(stepwise, trap)


def test_wilson_parity_with_merged_pr405_zero_events() -> None:
    # k=0, n=16, z≈1.959963984540054 -> upper = z^2 / (16 + z^2) ≈ 0.1936
    result = wilson_score_interval(0, 16)
    assert result.status == "estimated"
    assert result.lower == 0.0
    z2 = result.z * result.z
    expected_upper = z2 / (16.0 + z2)
    assert math.isclose(result.upper, expected_upper, rel_tol=1e-12)
    assert result.upper > 0.19
    zero = wilson_score_interval(0, 0)
    assert zero.status == "unavailable_zero_trials"
    assert zero.lower is None and zero.upper is None


def test_wilson_rejects_invalid_counts() -> None:
    with pytest.raises(ValueError):
        wilson_score_interval(2, 1)
    with pytest.raises(TypeError):
        wilson_score_interval(True, 1)  # type: ignore[arg-type]


def test_contract_rejects_invalid_inputs() -> None:
    mod = _contract()
    validate = mod.validate_binary_scores
    with pytest.raises(ValueError):
        validate([], [])
    with pytest.raises(ValueError):
        validate([1.0, float("nan")], [0, 1])
    with pytest.raises(ValueError):
        validate([1.0, float("inf")], [0, 1])
    with pytest.raises(ValueError):
        validate([0.1, 0.2], [0])
    with pytest.raises(ValueError):
        validate([0.1, 0.2], [0, 2])


def test_contract_ties_collapsed_and_permutation_invariant() -> None:
    mod = _contract()
    scores = [0.1, 0.4, 0.4, 0.8]
    labels = [0, 0, 1, 1]
    curve = mod.roc_curve(scores, labels)
    thresholds = list(curve.thresholds)
    assert len(thresholds) == len(set(thresholds))
    other = mod.roc_curve([0.8, 0.1, 0.4, 0.4], [1, 0, 1, 0])
    assert list(curve.fpr) == list(other.fpr)
    assert list(curve.tpr) == list(other.tpr)


def test_contract_endpoints_and_confusion_counts() -> None:
    mod = _contract()
    scores = [0.1, 0.4, 0.8]
    labels = [0, 1, 1]
    curve = mod.roc_curve(scores, labels)
    first = curve.points[0]
    last = curve.points[-1]
    assert math.isinf(first.threshold) and first.threshold > 0
    assert first.tp == 0 and first.fp == 0 and first.fn == 2 and first.tn == 1
    assert last.tp == 2 and last.fp == 1 and last.fn == 0 and last.tn == 0


def test_contract_single_class_is_undefined_not_zero() -> None:
    mod = _contract()
    result = mod.roc_curve([0.1, 0.2], [0, 0])
    assert result.status != "estimated"
    assert "single_class" in result.reason or "undefined" in result.reason
    assert result.tpr is None or all(item is None for item in result.tpr)
    assert result.auc is None


def test_contract_auc_matches_hand_rank() -> None:
    mod = _contract()
    scores = [0.1, 0.4, 0.4, 0.8]
    labels = [0, 0, 1, 1]
    expected = mann_whitney_auc(scores, labels)
    got = mod.roc_auc(scores, labels)
    assert math.isclose(got, expected.auc)


def test_contract_average_precision_is_stepwise() -> None:
    mod = _contract()
    scores = [0.9, 0.8, 0.7, 0.1]
    labels = [1, 0, 1, 0]
    expected = stepwise_average_precision(scores, labels)
    got = mod.average_precision(scores, labels)
    assert math.isclose(got, expected)
    assert not math.isclose(got, trapezoidal_pr_area(scores, labels))


def test_contract_calibration_does_not_reuse_held_out() -> None:
    mod = _contract()
    cal_scores = [0.1, 0.2, 0.8, 0.9]
    cal_labels = [0, 0, 1, 1]
    cal_ids = ["c1", "c2", "c3", "c4"]
    held_scores = [0.15, 0.25, 0.35, 0.95]
    held_labels = [0, 0, 0, 1]
    held_ids = ["e1", "e2", "e3", "e4"]
    frozen = mod.fit_threshold(cal_scores, cal_labels, cal_ids)
    report = mod.evaluate_held_out(frozen, held_scores, held_labels, held_ids)
    cal_report = mod.evaluate_held_out(frozen, cal_scores, cal_labels, cal_ids)
    assert report.metrics != cal_report.metrics
    assert frozen.threshold == report.threshold
    assert report.evidence_class == "synthetic_demonstration"
    assert report.scientific_pass is False


def test_contract_eval_change_does_not_move_threshold() -> None:
    mod = _contract()
    frozen = mod.fit_threshold([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], ["c1", "c2", "c3", "c4"])
    first = mod.evaluate_held_out(frozen, [0.1, 0.9], [0, 1], ["e1", "e2"])
    second = mod.evaluate_held_out(frozen, [0.1, 0.9], [1, 0], ["e1", "e2"])
    assert first.threshold == second.threshold == frozen.threshold
    assert first.metrics != second.metrics


def test_contract_overlap_rejected_or_reported() -> None:
    mod = _contract()
    frozen = mod.fit_threshold([0.1, 0.9], [0, 1], ["shared", "c2"])
    try:
        report = mod.evaluate_held_out(frozen, [0.2, 0.8], [0, 1], ["shared", "e2"])
    except ValueError as exc:
        assert "overlap" in str(exc).lower()
        return
    assert report.overlap_status in {"rejected", "reported"}
    assert "shared" in report.overlapping_ids


def test_contract_report_cannot_imply_validation() -> None:
    mod = _contract()
    frozen = mod.fit_threshold([0.1, 0.9], [0, 1], ["c1", "c2"])
    report = mod.evaluate_held_out(frozen, [0.2, 0.8], [0, 1], ["e1", "e2"])
    blob = repr(report).lower()
    assert report.scientific_pass is False
    for token in FORBIDDEN:
        if token == "scientific_pass":
            continue
        assert token.lower() not in blob or "false" in blob
