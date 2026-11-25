"""Bounded-memory execution and proper-scoring report for empirical features."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np

from .schema import EVIDENCE_CLASS, FEATURE_FAMILIES, finite_json
from .validation import ReadinessState, ValidationResult, _load_array, validate_manifest


def _logistic_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x = np.column_stack([np.ones(len(x)), x])
    weights = np.zeros(x.shape[1])
    for _ in range(80):
        logits = np.clip(x @ weights, -30, 30)
        prob = 1.0 / (1.0 + np.exp(-logits))
        weights -= 0.08 * (x.T @ (prob - y)) / max(len(x), 1)
    return weights


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
        positives = p[y == 1]
        negatives = p[y == 0]
        auroc = float(np.mean(positives[:, None] > negatives[None, :]) + 0.5 * np.mean(positives[:, None] == negatives[None, :]))
        order = np.argsort(-p)
        sorted_y = y[order]
        cumulative = np.cumsum(sorted_y)
        denom = max(int(np.sum(y)), 1)
        auprc = float(np.sum((cumulative / np.arange(1, len(y) + 1)) * sorted_y) / denom)
    calibration = float(abs(float(np.mean(p)) - float(np.mean(y))))
    return {"rows": int(len(y)), "log_loss": log_loss, "brier_score": brier, "auroc": auroc, "auprc": auprc, "calibration_error": calibration}


def _load_recording(record: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], np.ndarray]:
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
    return np.column_stack([arrays["psd"]]), target.astype(float), arrays, timestamps


def _feature_matrix(arrays: dict[str, np.ndarray], feature_set: str) -> np.ndarray:
    selected = {"psd": ("psd",), "psd_plus_pairwise_fc": ("psd", "pairwise_fc"), "psd_plus_triadic_fc": ("psd", "pairwise_fc", "triadic_fc"), "psd_plus_directed_hypergraph": ("psd", "pairwise_fc", "directed_hypergraph")}[feature_set]
    return np.column_stack([arrays[name] for name in selected])


def _score_feature_set(rows: list[tuple[str, np.ndarray, np.ndarray, float]], feature_set: str) -> dict[str, Any]:
    if len(rows) < 2:
        return {"feature_family": feature_set, "status": "INSUFFICIENT_DATA", "subject_held_out": _metrics(np.array([]), np.array([])), "forward_time": _metrics(np.array([]), np.array([]))}
    subjects = sorted({item[0] for item in rows})
    held_out = subjects[-1]
    train = [item for item in rows if item[0] != held_out]
    test = [item for item in rows if item[0] == held_out]
    def evaluate(train_rows: list[tuple[str, np.ndarray, np.ndarray, float]], test_rows: list[tuple[str, np.ndarray, np.ndarray, float]]) -> dict[str, Any]:
        if not train_rows or not test_rows:
            return _metrics(np.array([]), np.array([]))
        x_train = np.vstack([_feature_matrix(item[1], feature_set) for item in train_rows])
        y_train = np.concatenate([item[2] for item in train_rows])
        x_test = np.vstack([_feature_matrix(item[1], feature_set) for item in test_rows])
        y_test = np.concatenate([item[2] for item in test_rows])
        mean = x_train.mean(axis=0); scale = x_train.std(axis=0); scale[scale < 1e-12] = 1.0
        return _metrics(y_test, _predict((x_test - mean) / scale, _logistic_fit((x_train - mean) / scale, y_train)))
    subject_metrics = evaluate(train, test)
    ordered = sorted(rows, key=lambda item: item[3])
    cutoff = ordered[max(1, len(ordered) // 2) - 1][3]
    forward_train = [item for item in ordered if item[3] <= cutoff]
    forward_test = [item for item in ordered if item[3] > cutoff]
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
        "bounded_memory": {"processing_unit": "one subject/session/run", "max_recordings_loaded": 1},
        "formal_bayes_factor": None,
        "scientific_pass": False,
        "evidence_class": EVIDENCE_CLASS,
        "synthetic": validation.status == ReadinessState.SYNTHETIC_DEMO_ONLY,
    }
    if validation.status is ReadinessState.READY_FOR_DESCRIPTIVE_ANALYSIS:
        return base
    if not validation.ok:
        return base
    rows: list[tuple[str, dict[str, np.ndarray], np.ndarray, float]] = []
    missing_resp = 0
    try:
        for record in validation.recordings:
            raw = record["raw"]
            physiology = raw.get("physiology") if isinstance(raw.get("physiology"), dict) else {}
            if not physiology.get("respiration"):
                missing_resp += 1
            _, target, arrays, timestamps = _load_recording(record)
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
            rows.append((str(raw["subject_id"]), arrays, target, float(np.min(timestamps))))
    except (OSError, ValueError, KeyError) as exc:
        base["status"] = "INCONCLUSIVE"
        base["validation"]["reasons"].append(str(exc))
        return base
    base["missingness"] = {"respiration": {"recordings_missing": missing_resp, "state": "MISSING_OPTIONAL_PHYSIOLOGY" if missing_resp else "AVAILABLE"}}
    names = ["psd", "psd_plus_pairwise_fc", "psd_plus_triadic_fc", "psd_plus_directed_hypergraph"]
    previous_loss = None
    for name in names:
        result = _score_feature_set(rows, name)
        loss = result["subject_held_out"]["log_loss"]
        result["incremental_gain"] = None if previous_loss is None or loss is None else float(previous_loss - loss)
        result["incremental_status"] = "BASELINE" if previous_loss is None else ("FORMAL_FORECAST_EVIDENCE" if loss is not None and loss < previous_loss else "NO_INCREMENTAL_GAIN")
        if loss is not None:
            previous_loss = loss
        base["model_ladder"].append(result)
    base["model_ladder"].append({"feature_family": "higher_order_spectra", "status": ReadinessState.MISSING_OPTIONAL_DEPENDENCY.value, "reason": "optional feature artifact/dependency was not supplied"})
    base["status"] = ReadinessState.READY_FOR_FORECASTING.value
    base["checksum"] = hashlib.sha256(finite_json(base).encode("utf-8")).hexdigest()
    return base
