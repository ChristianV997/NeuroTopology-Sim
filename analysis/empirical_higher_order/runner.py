"""Bounded-memory execution and proper-scoring report for empirical features."""
from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

from .schema import EVIDENCE_CLASS, FEATURE_FAMILIES, finite_json
from .validation import ReadinessState, ValidationResult, _load_array, validate_manifest


def _predict(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(np.column_stack([np.ones(len(x)), x]) @ weights, -30, 30)))


def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    if len(y) == 0:
        return {"rows": 0, "log_loss": None, "brier_score": None, "auroc": None, "auprc": None, "calibration_error": None}
    p = np.clip(p, 1e-7, 1 - 1e-7)
    log_loss = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    brier = float(np.mean((p - y) ** 2))
    unique = np.unique(y)
    auroc = None
    auprc = None
    if len(unique) == 2:
        positive_count = int(np.sum(y == 1))
        negative_count = int(np.sum(y == 0))
        _, inverse, counts = np.unique(p, return_inverse=True, return_counts=True)
        average_ranks = np.cumsum(counts) - (counts - 1) / 2.0
        positive_rank_sum = float(np.sum(average_ranks[inverse[y == 1]]))
        auroc = float(
            (positive_rank_sum - positive_count * (positive_count + 1) / 2)
            / (positive_count * negative_count)
        )
        scores = np.asarray(p)
        order = np.argsort(-scores, kind="mergesort")
        sorted_scores = scores[order]
        sorted_y = y[order]
        group_ends = np.flatnonzero(np.r_[sorted_scores[1:] != sorted_scores[:-1], True])
        cumulative_hits = np.cumsum(sorted_y)[group_ends]
        group_positive_counts = np.diff(np.r_[0, cumulative_hits])
        precision_at_threshold = cumulative_hits / (group_ends + 1)
        auprc = float(np.sum(group_positive_counts * precision_at_threshold) / positive_count)
    calibration = float(abs(float(np.mean(p)) - float(np.mean(y))))
    return {"rows": int(len(y)), "log_loss": log_loss, "brier_score": brier, "auroc": auroc, "auprc": auprc, "calibration_error": calibration}


def _load_recording(record: dict[str, Any]) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray]:
    paths = record["paths"]
    arrays: dict[str, np.ndarray] = {}
    for family in FEATURE_FAMILIES[:-1]:
        arrays[family] = np.asarray(_load_array(paths[family]), dtype=float)
    target = np.asarray(_load_array(paths["target"]), dtype=float).reshape(-1) if paths["target"] else np.array([], dtype=float)
    timestamps = np.asarray(_load_array(paths["timestamps"]), dtype=float).reshape(-1) if paths["timestamps"] else np.arange(len(target), dtype=float)
    n = len(target)
    for family, values in arrays.items():
        if values.ndim == 1:
            values = values[:, None]
            arrays[family] = values
        if values.ndim != 2 or len(values) != n:
            raise ValueError(f"{family} feature rows do not match target rows")
    if len(timestamps) != n or not np.all(np.isfinite(timestamps)):
        raise ValueError("timestamps do not match target rows or are non-finite")
    if not np.all(np.isfinite(target)) or not np.all(np.isin(target, [0, 1])):
        raise ValueError("target must contain finite binary labels")
    if np.any(timestamps[1:] < timestamps[:-1]):
        raise ValueError("timestamps are not monotonic")
    return target, arrays, timestamps


def _feature_matrix(arrays: dict[str, np.ndarray], feature_set: str) -> np.ndarray:
    selected = {"psd": ("psd",), "psd_plus_pairwise_fc": ("psd", "pairwise_fc"), "psd_plus_triadic_fc": ("psd", "pairwise_fc", "triadic_fc"), "psd_plus_directed_hypergraph": ("psd", "pairwise_fc", "directed_hypergraph")}[feature_set]
    return np.column_stack([arrays[name] for name in selected])


def _record_design(record: dict[str, Any], feature_set: str) -> tuple[np.ndarray, np.ndarray]:
    target, arrays, _ = _load_recording(record)
    return _feature_matrix(arrays, feature_set), target


def _iter_record_design(
    rows: list[tuple[str, dict[str, Any], float]], feature_set: str
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    for _, record, _ in rows:
        matrix, target = _record_design(record, feature_set)
        yield matrix, target
        del matrix, target


def _score_feature_set(rows: list[tuple[str, dict[str, Any], float]], feature_set: str) -> dict[str, Any]:
    if len(rows) < 2:
        return {"feature_family": feature_set, "status": "INSUFFICIENT_DATA", "subject_held_out": _metrics(np.array([]), np.array([])), "forward_time": _metrics(np.array([]), np.array([]))}
    subjects = sorted({item[0] for item in rows})
    held_out = subjects[-1]
    train = [item for item in rows if item[0] != held_out]
    test = [item for item in rows if item[0] == held_out]
    def evaluate(
        train_rows: list[tuple[str, dict[str, Any], float]],
        test_rows: list[tuple[str, dict[str, Any], float]],
    ) -> dict[str, Any]:
        if not train_rows or not test_rows:
            return _metrics(np.array([]), np.array([]))
        feature_sum = None
        row_count = 0
        for matrix, target in _iter_record_design(train_rows, feature_set):
            if feature_sum is None:
                feature_sum = np.zeros(matrix.shape[1], dtype=float)
            feature_sum += matrix.sum(axis=0)
            row_count += len(target)
            del matrix, target
        if feature_sum is None or row_count == 0:
            return _metrics(np.array([]), np.array([]))

        mean = feature_sum / row_count
        squared_deviation = np.zeros_like(mean)
        for matrix, target in _iter_record_design(train_rows, feature_set):
            centered = matrix - mean
            squared_deviation += np.square(centered).sum(axis=0)
            del matrix, target, centered
        scale = np.sqrt(squared_deviation / row_count)
        scale[scale < 1e-12] = 1.0

        weights = np.zeros(len(mean) + 1, dtype=float)
        for _ in range(80):
            gradient = np.zeros_like(weights)
            fit_row_count = 0
            for matrix, target in _iter_record_design(train_rows, feature_set):
                normalized = (matrix - mean) / scale
                design = np.column_stack([np.ones(len(normalized)), normalized])
                logits = np.clip(design @ weights, -30, 30)
                probabilities = 1.0 / (1.0 + np.exp(-logits))
                gradient += design.T @ (probabilities - target)
                fit_row_count += len(target)
                del matrix, target, normalized, design, logits, probabilities
            weights -= 0.08 * gradient / max(fit_row_count, 1)

        target_parts = []
        prediction_parts = []
        for matrix, target in _iter_record_design(test_rows, feature_set):
            prediction_parts.append(_predict((matrix - mean) / scale, weights))
            target_parts.append(np.asarray(target, dtype=float).copy())
            del matrix, target
        y_test = np.concatenate(target_parts)
        p_test = np.concatenate(prediction_parts)
        return _metrics(y_test, p_test)
    subject_metrics = evaluate(train, test)
    ordered = sorted(rows, key=lambda item: item[2])
    cutoff = ordered[max(1, len(ordered) // 2) - 1][2]
    forward_train = [item for item in ordered if item[2] <= cutoff]
    forward_test = [item for item in ordered if item[2] > cutoff]
    return {"feature_family": feature_set, "status": "VALIDATED", "subject_held_out": subject_metrics,
            "subject_split": {"train_subjects": sorted({item[0] for item in train}), "test_subjects": [held_out],
                               "overlap": sorted({item[0] for item in train}.intersection({held_out}))},
            "forward_time": evaluate(forward_train, forward_test)}


def run_empirical(manifest_path: str | Path) -> dict[str, Any]:
    validation = validate_manifest(manifest_path)
    base: dict[str, Any] = {
        "schema_version": "NeuroTopologySim.EmpiricalHigherOrderExecution.v1",
        "status": validation.status.value,
        "validation": validation.to_dict(),
        "model_ladder": [],
        "split_strategies": {"subject_held_out": "last subject held out; training-only normalization", "forward_time": "past timestamps train; future timestamps test"},
        "null_controls": ["label_permutation", "circular_time_shift", "block_shuffle", "matched_variance_surrogate", "matched_autocorrelation_surrogate_when_available"],
        "missingness": {},
        "bounded_memory": {
            "processing_unit": "one subject/session/run",
            "max_recordings_loaded": 1,
            "feature_arrays_retained_between_recordings": 0,
            "metric_vectors_retained_for_scoring": True,
        },
        "formal_bayes_factor": None,
        "scientific_pass": False,
        "evidence_class": EVIDENCE_CLASS,
        "synthetic": validation.status == ReadinessState.SYNTHETIC_DEMO_ONLY,
    }
    if validation.status is ReadinessState.READY_FOR_DESCRIPTIVE_ANALYSIS:
        return base
    if not validation.ok:
        return base
    rows: list[tuple[str, dict[str, Any], float]] = []
    missing_resp = 0
    try:
        for record in validation.recordings:
            raw = record["raw"]
            physiology = raw.get("physiology") if isinstance(raw.get("physiology"), dict) else {}
            if not physiology.get("respiration"):
                missing_resp += 1
            target, arrays, timestamps = _load_recording(record)
            target_times = raw.get("target_timestamps")
            if not isinstance(target_times, (list, tuple)):
                raise ValueError("TEMPORAL_LINEAGE_REQUIRED: explicit target_timestamps are required for forecasting")
            target_times_array = np.asarray(target_times, dtype=float).reshape(-1)
            if target_times_array.shape != timestamps.shape or not np.all(np.isfinite(target_times_array)):
                raise ValueError("TEMPORAL_LINEAGE_INVALID: target_timestamps must be finite and row-aligned")
            if np.any(target_times_array[1:] < target_times_array[:-1]):
                raise ValueError("TEMPORAL_LINEAGE_INVALID: target_timestamps are not monotonic")
            if np.any(timestamps > target_times_array):
                raise ValueError("LEAKAGE_DETECTED: feature timestamp occurs after target timestamp")
            rows.append((str(raw["subject_id"]), record, float(np.min(timestamps))))
            del target, arrays, timestamps, target_times_array
    except (OSError, ValueError, KeyError) as exc:
        base["status"] = "INCONCLUSIVE"
        base["validation"]["reasons"].append(str(exc))
        return base
    base["missingness"] = {"respiration": {"recordings_missing": missing_resp, "state": "MISSING_OPTIONAL_PHYSIOLOGY" if missing_resp else "AVAILABLE"}}
    names = ["psd", "psd_plus_pairwise_fc", "psd_plus_triadic_fc", "psd_plus_directed_hypergraph"]
    previous_loss = None
    for name in names:
        try:
            result = _score_feature_set(rows, name)
        except (OSError, ValueError, KeyError) as exc:
            base["status"] = ReadinessState.INCONCLUSIVE.value
            base["validation"]["reasons"].append(str(exc))
            return base
        loss = result["subject_held_out"]["log_loss"]
        result["incremental_gain"] = None if previous_loss is None or loss is None else float(previous_loss - loss)
        # A local proper-score improvement is a benchmark observation, not
        # independently adjudicated formal or scientific evidence.
        result["incremental_status"] = "BASELINE" if previous_loss is None else ("INCONCLUSIVE" if loss is not None and loss < previous_loss else "NO_INCREMENTAL_GAIN")
        if loss is not None:
            previous_loss = loss
        base["model_ladder"].append(result)
    base["model_ladder"].append({"feature_family": "higher_order_spectra", "status": ReadinessState.MISSING_OPTIONAL_DEPENDENCY.value, "reason": "optional feature artifact/dependency was not supplied"})
    base["status"] = ReadinessState.READY_FOR_FORECASTING.value
    base["checksum"] = hashlib.sha256(finite_json(base).encode("utf-8")).hexdigest()
    return base
