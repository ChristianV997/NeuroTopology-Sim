"""Synthetic operating-characteristics benchmark API (HOLD / SYNTHETIC_ONLY).

Accepts injected score generators for unit fixtures and dry runs.
Fails closed or reports BLOCKED when required scientific prerequisites
are absent. Does not execute parameter grids or publish detector performance
or biological validity.

Contract (operating characteristics):
- Higher score is positive.
- ROC AUC = Mann–Whitney U with midrank ties (not a trapezoidal ROC area).
- Average precision = stepwise / weighted precision-at-recall (not trapezoidal PR area).
- Endpoint thresholds (+inf: no predicted positives; -inf: all predicted positives).
- Undefined rates (zero denominator, single-class AUC/AP) returned as None with explicit status, never silently zero.
- Wilson score intervals reused from analysis.binomial_planning.wilson (PR #405). Numerator k and denominator n reported beside every rate.
- Threshold selected on calibration data only under a predeclared rule and frozen before held-out evaluation. Overlap and evaluation-based retuning rejected.
- Sample-ID disjointness checked directly on the raw ID sets. When a data digest is requested during held-out evaluation, the caller must provide the frozen calibration record and original score/label bundle so the selection, ID fingerprint, threshold, and digest can be recomputed together. SHA-256 fingerprints are consistency checks only — not external signatures or proof against an attacker who can rewrite the record and data.
- Independent statistical unit must be declared. If observations are clustered, ordinary window-level Wilson intervals are not applied as if windows were independent. cluster_any_event_rate first reduces each independent cluster to one binary any-event outcome and uses cluster count as n. A pooled window rate may be reported as a point estimate only unless a justified cluster bootstrap or GLMM is implemented.
- Minimum sample counts are an engineering gate, not a power guarantee. Correlated windows are not counted as independent samples.

Project status remains HOLD / SYNTHETIC_ONLY.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np

from analysis.binomial_planning.wilson import wilson_score_interval

PROJECT_STATUS = "HOLD / SYNTHETIC_ONLY"
HIGHER_SCORE_IS_POSITIVE = True
HASH_NOTE = (
    "SHA-256 fingerprints are tamper-evident consistency checks, not external "
    "signatures or proof against an attacker who can rewrite the record and source data."
)


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
    try:
        s = np.asarray(scores, dtype=float)
        lab = np.asarray(labels)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BenchmarkError("scores and labels must be valid one-dimensional arrays") from exc
    if s.ndim != 1 or lab.ndim != 1:
        raise BenchmarkError("scores and labels must be one-dimensional")
    if len(s) == 0 or len(lab) == 0 or len(s) != len(lab):
        raise BenchmarkError("scores and labels must have equal nonzero length")
    if not np.all(np.isfinite(s)):
        raise BenchmarkError("scores must be finite")
    if lab.dtype == bool:
        lab = lab.astype(int)
    if not np.all(np.isin(lab, [0, 1])):
        raise BenchmarkError("labels must be binary 0/1 or bool")
    return s, lab.astype(int)


def _validate_ids(ids: Sequence, name: str = "ids", unique: bool = True) -> list[str]:
    """Reject empty or non-string IDs. Optionally reject duplicates within a split.

    Sample IDs require unique=True. Cluster IDs use unique=False because one
    independent cluster may contain multiple observations/windows.
    """
    if ids is None or isinstance(ids, (str, bytes, Mapping)):
        raise BenchmarkError(f"{name} must be a sequence of non-empty strings")
    try:
        values = list(ids)
    except TypeError as exc:
        raise BenchmarkError(f"{name} must be a sequence of non-empty strings") from exc
    if len(values) == 0:
        raise BenchmarkError(f"{name} must be non-empty")
    str_ids: list[str] = []
    for x in values:
        if not isinstance(x, str) or not x.strip():
            raise BenchmarkError(f"{name} must be non-empty strings")
        str_ids.append(x)
    if unique and len(set(str_ids)) != len(str_ids):
        raise BenchmarkError(f"duplicate {name} within split")
    return str_ids


def _validate_threshold(threshold) -> float:
    if isinstance(threshold, (bool, np.bool_)):
        raise BenchmarkError("threshold must be a real number, not bool")
    try:
        value = float(threshold)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BenchmarkError("threshold must be a real number") from exc
    if math.isnan(value):
        raise BenchmarkError("threshold must not be NaN")
    return value


def _data_digest(scores, labels) -> str:
    """Canonical digest of calibration scores and labels for consistency check."""
    payload = json.dumps(
        {
            "scores": [float(x) for x in scores],
            "labels": [int(x) for x in labels],
        },
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint_sample_ids(sample_ids: Sequence) -> str:
    """Canonical JSON-array SHA-256 of sorted non-empty string IDs.

    Embedded newlines or other delimiters cannot collide. Hash is a
    tamper-evident consistency check only.
    """
    ids = _validate_ids(sample_ids, "sample_ids")
    payload = json.dumps(sorted(ids), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        ranks[order[i : j + 1]] = mid
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


def cluster_any_event_rate(labels, cluster_ids):
    """Reduce each independent cluster to one binary any-event outcome.

    Independent statistical unit is the cluster. Ordinary window-level Wilson
    intervals are not applied. n = number of clusters.
    """
    y = np.asarray(labels)
    if y.dtype == bool:
        y = y.astype(int)
    if not np.all(np.isin(y, [0, 1])) or y.ndim != 1:
        raise BenchmarkError("labels must be binary 0/1 or bool; 1-D required")
    cids = _validate_ids(cluster_ids, "cluster_ids", unique=False)
    if len(cids) != len(y):
        raise BenchmarkError("cluster_ids length must equal labels")
    groups: dict[str, list[int]] = defaultdict(list)
    for cid, lab in zip(cids, y.astype(int)):
        groups[cid].append(int(lab))
    any_events = [1 if max(labs) == 1 else 0 for labs in groups.values()]
    n_clusters = len(any_events)
    k = int(sum(any_events))
    rate, status, wilson = _rate_with_status(k, n_clusters)
    return {
        "cluster_any_event_rate": rate,
        "status": status,
        "k": k,
        "n_clusters": n_clusters,
        "wilson": wilson,
        "independent_statistical_unit": "cluster",
        "note": (
            "Each independent cluster reduced to one binary any-event outcome. "
            "Window-level Wilson intervals are not applied as if windows were independent. "
            "Pooled window rate is a point estimate only unless a justified cluster method is used."
        ),
    }


def confusion_at_threshold(scores, labels, threshold):
    scores, labels = _validate_scores_labels(scores, labels)
    threshold = _validate_threshold(threshold)
    return _confusion_at_threshold_validated(scores, labels, threshold)


def _confusion_at_threshold_validated(scores, labels, threshold):
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


def operating_point(scores, labels, threshold, cluster_ids=None):
    scores, labels = _validate_scores_labels(scores, labels)
    threshold = _validate_threshold(threshold)
    if cluster_ids is not None:
        cluster_ids = _validate_ids(cluster_ids, "cluster_ids", unique=False)
        if len(cluster_ids) != len(scores):
            raise BenchmarkError("cluster_ids length must equal scores/labels")
    counts, note = _confusion_at_threshold_validated(scores, labels, threshold)
    tpr, tpr_st, tpr_w = _rate_with_status(counts.tp, counts.n_positive)
    fpr, fpr_st, fpr_w = _rate_with_status(counts.fp, counts.n_negative)
    prec, prec_st, prec_w = _rate_with_status(counts.tp, counts.n_predicted_positive)
    result = {
        "threshold": float(threshold),
        "counts": counts.to_dict(),
        "tpr": tpr, "fpr": fpr, "precision": prec,
        "tpr_status": tpr_st, "fpr_status": fpr_st, "precision_status": prec_st,
        "tpr_wilson": tpr_w, "fpr_wilson": fpr_w, "precision_wilson": prec_w,
        "endpoint_note": note,
        "independent_statistical_unit": "observation",
    }
    if cluster_ids is not None:
        if tpr is not None:
            result["tpr_status"] = "point_estimate_clustered"
        if fpr is not None:
            result["fpr_status"] = "point_estimate_clustered"
        if prec is not None:
            result["precision_status"] = "point_estimate_clustered"
        result["tpr_wilson"] = None
        result["fpr_wilson"] = None
        result["precision_wilson"] = None
        result["cluster_any_event"] = cluster_any_event_rate(labels, cluster_ids)
        result["window_rate_note"] = (
            "Window-level rates are point estimates only when observations are clustered. "
            "No window-level Wilson intervals are reported as if observations were independent."
        )
    return result


def compute_roc(scores, labels, thresholds=None, cluster_ids=None):
    s, y = _validate_scores_labels(scores, labels)
    if cluster_ids is not None:
        cluster_ids = _validate_ids(cluster_ids, "cluster_ids", unique=False)
        if len(cluster_ids) != len(s):
            raise BenchmarkError("cluster_ids length must equal scores/labels")
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
    else:
        try:
            thresholds = list(thresholds)
        except TypeError as exc:
            raise BenchmarkError("thresholds must be a non-empty sequence") from exc
        if not thresholds:
            raise BenchmarkError("thresholds must be a non-empty sequence")
        thresholds = [_validate_threshold(threshold) for threshold in thresholds]
    ops = [operating_point(s, y, thr, cluster_ids=cluster_ids) for thr in thresholds]
    result = {
        "auc": auc, "auc_status": auc_st,
        "average_precision": ap, "ap_status": ap_st,
        "n_positive": int(y.sum()), "n_negative": int((y == 0).sum()),
        "n_tied_groups": n_tied, "operating_points": ops,
        "warnings": warnings, "higher_score_is_positive": HIGHER_SCORE_IS_POSITIVE,
        "project_status": PROJECT_STATUS,
        "independent_statistical_unit": "observation",
        "cluster_any_event_independent_unit": "cluster" if cluster_ids is not None else None,
    }
    if cluster_ids is not None:
        result["clustered_evaluation_note"] = (
            "ROC/AUC and pooled window rates are descriptive point estimates; "
            "observations within clusters are not treated as independent. "
            "Cluster-level any-event Wilson intervals use the number of clusters."
        )
    return result


def select_threshold_on_calibration(scores, labels, sample_ids, criterion):
    s, y = _validate_scores_labels(scores, labels)
    ids = _validate_ids(sample_ids, "sample_ids")
    if len(ids) != len(s):
        raise BenchmarkError("sample_ids length must equal scores/labels")
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
    # Frozen selection fields (a plain dict for API compatibility, not immutable).
    # Digest verification revalidates the record against the supplied data bundle.
    return {
        "threshold": float(best_thr),
        "criterion": criterion,
        "criterion_value": float(best_val),
        "selection_rule": (
            f"max {criterion} on calibration operating points (endpoints skipped); "
            "ties retain the highest non-endpoint threshold"
        ),
        "calibration_sample_fingerprint": fingerprint_sample_ids(ids),
        "calibration_data_digest": _data_digest(s, y),
        "n_calibration": len(ids),
        "project_status": PROJECT_STATUS,
        "hash_note": HASH_NOTE,
    }


def assert_no_sample_overlap(calibration_ids, evaluation_ids):
    """Direct raw-ID disjointness check. Does not rely on hashes."""
    cal = set(_validate_ids(calibration_ids, "calibration_ids"))
    ev = set(_validate_ids(evaluation_ids, "evaluation_ids"))
    overlap = cal & ev
    if overlap:
        raise BenchmarkError(f"sample-ID overlap: {len(overlap)} ids")


def evaluate_held_out(
    scores,
    labels,
    evaluation_ids,
    frozen_threshold,
    calibration_fingerprint,
    calibration_ids,
    calibration_data_digest=None,
    frozen_calibration_record=None,
    calibration_bundle=None,
):
    """Evaluate frozen threshold on held-out samples.

    Rejects overlap and any retuning. Recomputes the calibration ID fingerprint
    as a consistency check. If digest verification is requested, the caller must
    provide the frozen selection record and calibration score/label bundle;
    the bundle is revalidated and threshold selection is recomputed before the
    held-out observations are evaluated. A digest is not a signature or proof of
    authenticity.
    """
    calibration_ids = _validate_ids(calibration_ids, "calibration_ids")
    evaluation_ids = _validate_ids(evaluation_ids, "evaluation_ids")
    assert_no_sample_overlap(calibration_ids, evaluation_ids)
    recomputed_fp = fingerprint_sample_ids(calibration_ids)
    if recomputed_fp != calibration_fingerprint:
        raise BenchmarkError("calibration fingerprint mismatch")
    s, y = _validate_scores_labels(scores, labels)
    ev_ids = evaluation_ids
    if len(ev_ids) != len(s):
        raise BenchmarkError("evaluation_ids length mismatch")
    verification_requested = (
        calibration_data_digest is not None
        or frozen_calibration_record is not None
        or calibration_bundle is not None
    )
    if verification_requested:
        if (
            not isinstance(frozen_calibration_record, Mapping)
            or not isinstance(calibration_bundle, Mapping)
            or calibration_data_digest is None
        ):
            raise BenchmarkError(
                "calibration digest verification requires the frozen record, "
                "calibration bundle, and expected digest"
            )
        if "scores" not in calibration_bundle or "labels" not in calibration_bundle:
            raise BenchmarkError("calibration bundle must contain scores and labels")
        recomputed_record = select_threshold_on_calibration(
            calibration_bundle["scores"],
            calibration_bundle["labels"],
            calibration_ids,
            frozen_calibration_record.get("criterion"),
        )
        verified_fields = (
            "threshold",
            "criterion",
            "criterion_value",
            "selection_rule",
            "calibration_sample_fingerprint",
            "calibration_data_digest",
            "n_calibration",
            "project_status",
            "hash_note",
        )
        if any(
            frozen_calibration_record.get(field) != recomputed_record[field]
            for field in verified_fields
        ):
            raise BenchmarkError("frozen calibration record mismatch")
        if calibration_data_digest != recomputed_record["calibration_data_digest"]:
            raise BenchmarkError("calibration data digest mismatch")
        if calibration_fingerprint != recomputed_record["calibration_sample_fingerprint"]:
            raise BenchmarkError("calibration fingerprint mismatch")
        if frozen_threshold != recomputed_record["threshold"]:
            raise BenchmarkError("frozen threshold does not match calibration selection")
    op = operating_point(s, y, frozen_threshold)
    return {
        "threshold": frozen_threshold,
        "calibration_fingerprint": calibration_fingerprint,
        "operating_point": op,
        "project_status": PROJECT_STATUS,
        "warnings": [
            "held_out_evaluation_only",
            "sample_overlap_check_does_not_prove_no_leakage",
            HASH_NOTE,
        ],
    }


REQUIRED_PREREQUISITES = (
    "source_pinned_four_sphere_model",
    "valid_planar_geometry_and_winding_hodge",
    "csd_conformance",
    "phase_surrogate_calibration",
)


def prerequisite_gate_report(available=None):
    if available is None:
        available = {}
    elif not isinstance(available, Mapping):
        raise BenchmarkError("prerequisites must be a mapping of names to booleans")
    status = {}
    blocked = []
    for key in REQUIRED_PREREQUISITES:
        value = available.get(key, False)
        is_boolean = isinstance(value, (bool, np.bool_))
        present = is_boolean and bool(value)
        status[key] = (
            "present" if present else "invalid" if key in available and not is_boolean else "absent"
        )
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
    if not isinstance(allow_full_forward_model, (bool, np.bool_)):
        raise BenchmarkError("allow_full_forward_model must be a boolean")
    for name in ("n_calibration", "n_evaluation"):
        value = getattr(config, name, None)
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 1:
            raise BenchmarkError("n_calibration and n_evaluation must be positive integers")
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
    held = evaluate_held_out(
        ev_scores, ev_labels, ev_ids, frozen["threshold"],
        frozen["calibration_sample_fingerprint"], cal_ids,
        calibration_data_digest=frozen.get("calibration_data_digest"),
        frozen_calibration_record=frozen,
        calibration_bundle={"scores": cal_scores, "labels": cal_labels},
    )
    roc = compute_roc(ev_scores, ev_labels)
    result.update({
        "status": "FIXTURE_RUN_COMPLETE", "experiment_ran": True, "performance_published": False,
        "frozen_threshold": frozen, "held_out": held,
        "held_out_roc_auc": roc["auc"], "held_out_roc_auc_status": roc["auc_status"],
        "sample_size_gate": {
            "n_calibration": config.n_calibration, "n_evaluation": config.n_evaluation,
            "target_per_split": 100,
            "meets_target": config.n_calibration >= 100 and config.n_evaluation >= 100,
            "note": (
                "engineering gate only; not a power guarantee. "
                "Do not count correlated windows as independent samples."
            ),
        },
        "independent_statistical_unit": "observation",
        "limitations": [
            "injected synthetic scores only",
            "does not validate biological construct",
            PROJECT_STATUS,
            HASH_NOTE,
        ],
    })
    return result


def json_safe(obj):
    """Serialize results without emitting non-standard JSON NaN or Infinity values."""

    def normalize(value):
        if isinstance(value, Mapping):
            return {str(key): normalize(item) for key, item in value.items()}
        if isinstance(value, np.ndarray):
            return normalize(value.tolist())
        if isinstance(value, np.generic):
            return normalize(value.item())
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if isinstance(value, float):
            if math.isnan(value):
                raise BenchmarkError("JSON results cannot contain NaN")
            if math.isinf(value):
                return "+Infinity" if value > 0 else "-Infinity"
        return value

    return json.dumps(normalize(obj), allow_nan=False, indent=2)
