"""Synthetic operating-characteristics benchmark API (HOLD / SYNTHETIC_ONLY).

Accepts injected score generators for unit fixtures and dry runs.
Fails closed or reports BLOCKED when required scientific prerequisites
are absent. Does not execute parameter grids or publish detector performance.

Higher score is positive. ROC AUC uses Mann–Whitney with midrank ties.
Average precision is the standard weighted definition, not trapezoidal PR area.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from analysis.binomial_planning.wilson import wilson_score_interval

PROJECT_STATUS = "HOLD / SYNTHETIC_ONLY"
HIGHER_SCORE_IS_POSITIVE = True


class BenchmarkError(ValueError):
    pass


@dataclass(frozen=True)
class ConfusionCounts:
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def n_positive(self) -> int:
        return self.tp + self.fn

    @property
    def n_negative(self) -> int:
        return self.tn + self.fp

    @property
    def n_predicted_positive(self) -> int:
        return self.tp + self.fp

    def to_dict(self) -> dict[str, int]:
        return {
            "tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn,
            "n_positive": self.n_positive, "n_negative": self.n_negative,
            "n_predicted_positive": self.n_predicted_positive,
        }


def _validate_scores_labels(scores, labels):
    if len(scores) == 0 or len(labels) == 0 or len(scores) != len(labels):
        raise BenchmarkError("scores and labels must have equal nonzero length")
    s = np.asarray(scores, dtype=float)
    if not np.all(np.isfinite(s)):
        raise BenchmarkError("scores must be finite")
    lab = np.asarray(labels)
    if lab.dtype == bool:
        lab = lab.astype(int)
    if not np.all(np.isin(lab, [0, 1])) or lab.ndim != 1 or s.ndim != 1:
        raise BenchmarkError("labels must be binary 0/1 or bool; 1-D required")
    return s, lab.astype(int)


def _midrank_auc(scores, labels):
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    n_pos, n_neg = len(pos), len(neg)
    if n_pos == 0 or n_neg == 0:
        return None, "undefined_single_class", 0
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=float)
    sorted_scores = scores[order]
    i = n_tied = 0
    while i < len(scores):
        j = i
        while j + 1 < len(scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        mid = 0.5 * ((i + 1) + (j + 1))
        ranks[order[i:j + 1]] = mid
        if j > i:
            n_tied += 1
        i = j + 1
    rank_sum_pos = float(ranks[labels == 1].sum())
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return float(u / (n_pos * n_neg)), "estimated", n_tied


def _average_precision(scores, labels):
    n_pos = int(labels.sum())
    if n_pos == 0:
        return None, "undefined_no_positives"
    if int((labels == 0).sum()) == 0:
        return None, "undefined_no_negatives"
    order = np.argsort(-scores, kind="mergesort")
    s_sorted, y_sorted = scores[order], labels[order]
    ap = prev_recall = 0.0
    tp = fp = i = 0
    n = len(scores)
    while i < n:
        j = i
        while j + 1 < n and s_sorted[j + 1] == s_sorted[i]:
            j += 1
        for k in range(i, j + 1):
            if y_sorted[k] == 1:
                tp += 1
            else:
                fp += 1
        precision = tp / (tp + fp) if (tp + fp) > 0 else None
        recall = tp / n_pos
        if precision is not None:
            ap += (recall - prev_recall) * precision
        prev_recall = recall
        i = j + 1
    return float(ap), "estimated"


def _rate_with_status(successes, trials):
    if trials == 0:
        return None, "undefined_zero_denominator", None
    wi = wilson_score_interval(successes, trials)
    return float(successes / trials), "estimated", {
        "k": wi.k, "n": wi.n, "lower": wi.lower, "upper": wi.upper, "status": wi.status
    }


def confusion_at_threshold(scores, labels, threshold):
    note = None
    if math.isinf(threshold) and threshold > 0:
        pred = np.zeros_like(labels)
        note = "plus_inf_no_predicted_positives"
    elif math.isinf(threshold) and threshold < 0:
        pred = np.ones_like(labels)
        note = "minus_inf_all_predicted_positives"
    else:
        pred = (scores >= threshold).astype(int)
    tp = int(((pred == 1) & (labels == 1)).sum())
    fp = int(((pred == 1) & (labels == 0)).sum())
    tn = int(((pred == 0) & (labels == 0)).sum())
    fn = int(((pred == 0) & (labels == 1)).sum())
    return ConfusionCounts(tp, fp, tn, fn), note


def operating_point(scores, labels, threshold):
    counts, note = confusion_at_threshold(scores, labels, threshold)
    tpr, tpr_st, tpr_w = _rate_with_status(counts.tp, counts.n_positive)
    fpr, fpr_st, fpr_w = _rate_with_status(counts.fp, counts.n_negative)
    prec, prec_st, prec_w = _rate_with_status(counts.tp, counts.n_predicted_positive)
    return {
        "threshold": float(threshold),
        "counts": counts.to_dict(),
        "tpr": tpr, "fpr": fpr, "precision": prec,
        "tpr_status": tpr_st, "fpr_status": fpr_st, "precision_status": prec_st,
        "tpr_wilson": tpr_w, "fpr_wilson": fpr_w, "precision_wilson": prec_w,
        "endpoint_note": note,
    }


def compute_roc(scores, labels, thresholds=None):
    s, y = _validate_scores_labels(scores, labels)
    auc, auc_st, n_tied = _midrank_auc(s, y)
    ap, ap_st = _average_precision(s, y)
    warnings = []
    if auc_st != "estimated":
        warnings.append(f"auc:{auc_st}")
    if ap_st != "estimated":
        warnings.append(f"ap:{ap_st}")
    if thresholds is None:
        uniq = np.unique(s)
        thresholds = [float("inf")] + sorted(uniq.tolist(), reverse=True) + [float("-inf")]
    ops = [operating_point(s, y, thr) for thr in thresholds]
    return {
        "auc": auc, "auc_status": auc_st,
        "average_precision": ap, "ap_status": ap_st,
        "n_positive": int(y.sum()), "n_negative": int((y == 0).sum()),
        "n_tied_groups": n_tied, "operating_points": ops,
        "warnings": warnings, "higher_score_is_positive": HIGHER_SCORE_IS_POSITIVE,
        "project_status": PROJECT_STATUS,
    }


def fingerprint_sample_ids(sample_ids):
    payload = "\n".join(sorted(str(x) for x in sample_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_threshold_on_calibration(scores, labels, sample_ids, criterion):
    s, y = _validate_scores_labels(scores, labels)
    if criterion not in {"youden", "f1"}:
        raise BenchmarkError(f"unsupported criterion: {criterion}")
    if len(np.unique(y)) < 2:
        raise BenchmarkError("threshold selection requires both classes")
    roc = compute_roc(s, y)
    best_thr, best_val = None, -math.inf
    for op in roc["operating_points"]:
        if op["endpoint_note"] is not None or op["tpr"] is None or op["fpr"] is None:
            continue
        if criterion == "youden":
            val = op["tpr"] - op["fpr"]
        else:
            if op["precision"] is None or (op["precision"] + op["tpr"]) == 0:
                continue
            val = 2 * op["precision"] * op["tpr"] / (op["precision"] + op["tpr"])
        if val > best_val:
            best_val, best_thr = val, op["threshold"]
    if best_thr is None:
        raise BenchmarkError("no valid threshold")
    return {
        "threshold": float(best_thr), "criterion": criterion,
        "criterion_value": float(best_val),
        "calibration_sample_fingerprint": fingerprint_sample_ids(sample_ids),
        "n_calibration": len(sample_ids), "project_status": PROJECT_STATUS,
    }


def assert_no_sample_overlap(calibration_ids, evaluation_ids):
    cal = set(str(x) for x in calibration_ids)
    ev = set(str(x) for x in evaluation_ids)
    overlap = cal & ev
    if overlap:
        raise BenchmarkError(f"sample-ID overlap: {len(overlap)} ids")


def evaluate_held_out(scores, labels, evaluation_ids, frozen_threshold, calibration_fingerprint, calibration_ids):
    assert_no_sample_overlap(calibration_ids, evaluation_ids)
    if fingerprint_sample_ids(calibration_ids) != calibration_fingerprint:
        raise BenchmarkError("calibration fingerprint mismatch")
    s, y = _validate_scores_labels(scores, labels)
    if len(evaluation_ids) != len(s):
        raise BenchmarkError("evaluation_ids length mismatch")
    op = operating_point(s, y, frozen_threshold)
    return {
        "threshold": frozen_threshold,
        "calibration_fingerprint": calibration_fingerprint,
        "operating_point": op,
        "project_status": PROJECT_STATUS,
        "warnings": ["held_out_evaluation_only", "sample_overlap_check_does_not_prove_no_leakage"],
    }


REQUIRED_PREREQUISITES = (
    "source_pinned_four_sphere_model",
    "valid_planar_geometry_and_winding_hodge",
    "csd_conformance",
    "phase_surrogate_calibration",
)


def prerequisite_gate_report(available=None):
    available = dict(available or {})
    status = {}
    blocked = []
    for key in REQUIRED_PREREQUISITES:
        present = bool(available.get(key, False))
        status[key] = "present" if present else "absent"
        if not present:
            blocked.append(key)
    overall = "BLOCKED" if blocked else "READY_FOR_FORWARD_MODEL_ROC"
    return {
        "overall": overall, "blocked_reasons": blocked, "component_status": status,
        "project_status": PROJECT_STATUS,
        "note": "Full forward-model ROC blocked until prerequisites independently verified and authorized. Injected generators permitted for fixtures.",
    }


@dataclass
class SyntheticRunnerConfig:
    seed: int
    model_id: str
    null_id: str
    config_hash: str
    n_calibration: int
    n_evaluation: int
    score_generator: Callable | None = None


def run_synthetic_operating_characteristics(config, prerequisites=None, allow_full_forward_model=False):
    gate = prerequisite_gate_report(prerequisites)
    result = {
        "project_status": PROJECT_STATUS, "gate": gate,
        "seed": config.seed, "model_id": config.model_id, "null_id": config.null_id,
        "config_hash": config.config_hash, "experiment_ran": False, "performance_published": False,
    }
    if gate["overall"] == "BLOCKED" and allow_full_forward_model:
        result["status"] = "BLOCKED"
        result["reason"] = "required scientific components absent"
        return result
    if config.score_generator is None:
        result["status"] = "DRY_RUN_OR_BLOCKED"
        result["reason"] = "no injected score generator"
        return result
    if config.n_calibration < 1 or config.n_evaluation < 1:
        raise BenchmarkError("sizes must be positive")
    cal_scores, cal_labels, cal_ids = config.score_generator(config.seed, config.n_calibration)
    ev_scores, ev_labels, ev_ids = config.score_generator(config.seed + 1, config.n_evaluation)
    frozen = select_threshold_on_calibration(cal_scores, cal_labels, cal_ids, "youden")
    held = evaluate_held_out(ev_scores, ev_labels, ev_ids, frozen["threshold"], frozen["calibration_sample_fingerprint"], cal_ids)
    roc = compute_roc(ev_scores, ev_labels)
    result.update({
        "status": "FIXTURE_RUN_COMPLETE", "experiment_ran": True, "performance_published": False,
        "frozen_threshold": frozen, "held_out": held,
        "held_out_roc_auc": roc["auc"], "held_out_roc_auc_status": roc["auc_status"],
        "sample_size_gate": {
            "n_calibration": config.n_calibration, "n_evaluation": config.n_evaluation,
            "target_per_split": 100,
            "meets_target": config.n_calibration >= 100 and config.n_evaluation >= 100,
            "note": "engineering gate only; not a power guarantee",
        },
        "limitations": ["injected synthetic scores only", "does not validate biological construct", PROJECT_STATUS],
    })
    return result


def json_safe(obj):
    return json.dumps(obj, allow_nan=False, indent=2)
