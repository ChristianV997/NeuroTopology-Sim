"""Locked out-of-sample transition forecasting with proper scoring rules.

This module consumes already-computed feature blocks. It deliberately does not
implement PSD, FC, triadic connectivity, or hypergraph construction. Thus the
benchmark can compare representations without changing another subsystem's
scientific semantics.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .splits import LockedSplit, locked_split, validate_split

SCHEMA_VERSION = "NTS.TransitionForecastBenchmark.v1"
FEATURE_KEYS = {
    "PSD": "psd",
    "PSD_PLUS_PAIRWISE_FC": "pairwise_fc",
    "PSD_PLUS_TRIADIC_FC": "triadic_fc",
    "PSD_PLUS_DIRECTED_HYPERGRAPH": "directed_hypergraph",
}
LADDER = tuple(FEATURE_KEYS)
CONTROL_KEYS = (
    "arousal", "respiration", "cardiac", "autonomic", "sampling_rate",
    "window_length",
)


class ForecastStatus(str, Enum):
    # Retained for parsing older artifacts only. This local benchmark never
    # emits this status because a predictive score is not independent evidence.
    FORMAL_FORECAST_EVIDENCE = "FORMAL_FORECAST_EVIDENCE"
    NO_INCREMENTAL_GAIN = "NO_INCREMENTAL_GAIN"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    LEAKAGE_DETECTED = "LEAKAGE_DETECTED"
    SYNTHETIC_DEMO_ONLY = "SYNTHETIC_DEMO_ONLY"
    INVALID_INPUT = "INVALID_INPUT"
    INCONCLUSIVE = "INCONCLUSIVE"


class LeakageDetected(ValueError):
    """Raised when a locked benchmark boundary is violated."""


@dataclass
class BenchmarkDataset:
    features: Mapping[str, np.ndarray]
    target: np.ndarray
    subjects: np.ndarray
    sessions: np.ndarray
    timestamps: np.ndarray
    prediction_horizon: float
    target_definition: str
    provenance: Mapping[str, Any] = field(default_factory=dict)
    controls: Mapping[str, np.ndarray] = field(default_factory=dict)
    feature_times: Mapping[str, np.ndarray] = field(default_factory=dict)
    synthetic: bool = False
    # Declarations are retained for auditability, but are never sufficient to
    # promote a local benchmark to formal or scientific evidence.
    adjudication_metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        n = len(np.asarray(self.target))
        arrays = {
            "subjects": self.subjects, "sessions": self.sessions,
            "timestamps": self.timestamps,
        }
        if n < 6:
            raise ValueError("at least six forecast rows are required")
        if not np.isfinite(float(self.prediction_horizon)) or self.prediction_horizon <= 0:
            raise ValueError("prediction_horizon must be positive and finite")
        target = np.asarray(self.target)
        if target.ndim != 1 or not np.all(np.isin(target, [0, 1])):
            raise ValueError("target must be a binary one-dimensional array")
        for name, value in arrays.items():
            if len(np.asarray(value)) != n:
                raise ValueError(f"{name} length does not match target")
        timestamps = np.asarray(self.timestamps, dtype=float)
        if timestamps.shape != (n,) or not np.all(np.isfinite(timestamps)):
            raise ValueError("timestamps must be a finite row-aligned vector")
        if np.any(np.diff(timestamps) < 0):
            raise ValueError("timestamps must be monotonic non-decreasing")
        for name, value in self.features.items():
            matrix = np.asarray(value, dtype=float)
            if matrix.ndim != 2 or matrix.shape[0] != n:
                raise ValueError(f"feature block {name!r} must have shape (rows, columns)")
            if matrix.shape[1] == 0 or not np.all(np.isfinite(matrix)):
                raise ValueError(f"feature block {name!r} must be finite and non-empty")
        for name, value in self.controls.items():
            arr = np.asarray(value, dtype=float)
            if arr.ndim not in (1, 2) or arr.shape[0] != n or not np.all(np.isfinite(arr)):
                raise ValueError(f"control {name!r} must be finite and row-aligned")
        if not isinstance(self.feature_times, Mapping):
            raise ValueError("feature_times must be a mapping for every feature block")
        feature_names = set(self.features)
        time_names = set(self.feature_times)
        missing_times = sorted(feature_names - time_names)
        unexpected_times = sorted(time_names - feature_names)
        if missing_times:
            raise ValueError(f"immutable feature-time lineage is required; missing feature_times for {missing_times}")
        if unexpected_times:
            raise ValueError(f"feature_times contains unknown feature blocks: {unexpected_times}")
        for name in sorted(feature_names):
            value = self.feature_times[name]
            arr = np.asarray(value, dtype=float)
            if arr.shape != (n,) or not np.all(np.isfinite(arr)):
                raise ValueError(f"feature_times[{name!r}] must be a finite row-aligned vector")
            if np.any(np.diff(arr) < 0):
                raise ValueError(f"feature_times[{name!r}] must be monotonic non-decreasing")
            if np.any(arr > timestamps):
                raise LeakageDetected(f"future-window feature detected for {name}")

    @property
    def n_rows(self) -> int:
        return len(np.asarray(self.target))

    def checksum(self) -> str:
        feature_times = self.feature_times if isinstance(self.feature_times, Mapping) else {}
        controls = self.controls if isinstance(self.controls, Mapping) else {}
        payload = {
            "schema_version": SCHEMA_VERSION,
            "target": np.asarray(self.target).tolist(),
            "subjects": np.asarray(self.subjects).tolist(),
            "sessions": np.asarray(self.sessions).tolist(),
            "timestamps": np.asarray(self.timestamps, dtype=float).tolist(),
            "features": {k: np.asarray(self.features[k], dtype=float).tolist() for k in sorted(self.features)},
            # Bind each output to the exact feature-time lineage used to
            # establish the causal forecasting boundary.
            "feature_times": {k: np.asarray(feature_times[k], dtype=float).tolist() for k in sorted(feature_times)},
            "controls": {k: np.asarray(controls[k], dtype=float).tolist() for k in sorted(controls)},
            "prediction_horizon": self.prediction_horizon,
            "target_definition": self.target_definition,
            "provenance": self.provenance,
            "synthetic": self.synthetic,
            "adjudication_metadata": self.adjudication_metadata,
        }
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IncrementalResult:
    model_family: str
    feature_family: str
    train_rows: int
    held_out_rows: int
    log_loss: Optional[float]
    brier_score: Optional[float]
    auroc: Optional[float]
    auprc: Optional[float]
    calibration_error: Optional[float]
    permutation_p_value: Optional[float]
    confidence_interval: Optional[tuple[float, float]]
    incremental_gain: Optional[float]
    status: str
    missingness: Mapping[str, Any]
    controls_used: tuple[str, ...]
    checksum: str

    def to_dict(self) -> dict[str, Any]:
        return _finite(self.__dict__)


@dataclass(frozen=True)
class BenchmarkReport:
    schema_version: str
    status: str
    dataset_provenance: Mapping[str, Any]
    subject_session_split: Mapping[str, Any]
    prediction_horizon: float
    target_definition: str
    model_family: str
    results: tuple[IncrementalResult, ...]
    null_comparisons: Mapping[str, Any]
    missingness: Mapping[str, Any]
    checksum: str
    synthetic: bool
    formal_bayes_factor: None = None
    scientific_pass: bool = False
    evidence_class: str = "forecast_benchmark"
    adjudication: Mapping[str, Any] = field(default_factory=dict)
    dataset_checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {
            "schema_version": self.schema_version,
            "status": self.status,
            "dataset_provenance": dict(self.dataset_provenance),
            "subject_session_split": dict(self.subject_session_split),
            "prediction_horizon": self.prediction_horizon,
            "target_definition": self.target_definition,
            "feature_family": "PSD → pairwise FC → triadic FC → directed hypergraph",
            "model_family": self.model_family,
            "training_rows": sum(r.train_rows for r in self.results),
            "held_out_rows": sum(r.held_out_rows for r in self.results),
            "results": [r.to_dict() for r in self.results],
            "null_comparisons": dict(self.null_comparisons),
            "missingness": dict(self.missingness),
            "checksum": self.checksum,
            "synthetic": self.synthetic,
            "formal_bayes_factor": None,
            "scientific_pass": False,
            "evidence_class": "forecast_benchmark",
            "adjudication": dict(self.adjudication),
            "dataset_checksum": self.dataset_checksum,
        }
        return _finite(data)

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def _finite(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _finite(value.tolist())
    if isinstance(value, np.generic):
        return _finite(value.item())
    if isinstance(value, Mapping):
        return {str(k): _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (int, np.integer, str, bool)) or value is None:
        return value
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(_finite(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _safe_dataset_checksum(dataset: BenchmarkDataset) -> str:
    """Return a stable identity when possible without masking an invalid input."""
    try:
        return dataset.checksum()
    except (TypeError, ValueError, KeyError):
        return ""


def _with_report_checksum(report: BenchmarkReport) -> BenchmarkReport:
    payload = report.to_dict()
    payload.pop("checksum", None)
    checksum = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return replace(report, checksum=checksum)


def _failure_report(dataset: BenchmarkDataset, status: ForecastStatus, message: str) -> BenchmarkReport:
    report = BenchmarkReport(
        SCHEMA_VERSION, status.value, {**dataset.provenance, "message": message}, {},
        float(dataset.prediction_horizon), dataset.target_definition, "deterministic_logistic",
        (), {}, {}, "", bool(dataset.synthetic),
        adjudication={
            "status": "BLOCKED",
            "external_independent_adjudication_required": True,
            "formal_evidence_emitted": False,
            "scientific_pass_emitted": False,
            "reason": message,
        },
        dataset_checksum=_safe_dataset_checksum(dataset) if len(np.asarray(dataset.target)) else "",
    )
    return _with_report_checksum(report)


def _metadata_is_missing(value: Any) -> bool:
    """Treat absent, empty, and explicitly unknown declarations as missing."""
    if value is None or value is False:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "unknown", "missing", "not_provided", "none", "unavailable"}
    if isinstance(value, Mapping):
        # A declaration is complete only when every field carries a value.
        return not value or any(_metadata_is_missing(item) for item in value.values())
    if isinstance(value, Sequence):
        return not value or any(_metadata_is_missing(item) for item in value)
    return False


def _adjudication_summary(dataset: BenchmarkDataset, split: LockedSplit) -> dict[str, Any]:
    """Describe what this local benchmark cannot adjudicate by itself.

    The fields are declarations for downstream reviewers, not authority to emit
    formal evidence. A caller cannot self-attest its way out of this boundary.
    """
    metadata = dataset.adjudication_metadata if isinstance(dataset.adjudication_metadata, Mapping) else {}
    required = {
        "null_models": "null_models",
        "calibration": "calibration",
        "locked_split": "locked_split",
        "multiplicity": "multiplicity",
    }
    missing = [label for label, key in required.items() if _metadata_is_missing(metadata.get(key))]
    formal_keys = {
        "formal_bayes_factor",
        "scientific_pass",
        "formal_forecast_evidence",
        "formal_evidence",
        "evidence_adjudicated",
    }
    ignored = sorted(
        key for source in (dataset.provenance, metadata)
        if isinstance(source, Mapping)
        for key in source
        if str(key) in formal_keys and not _metadata_is_missing(source[key])
    )
    return {
        "status": "INCONCLUSIVE" if missing else "EXTERNAL_INDEPENDENT_ADJUDICATION_REQUIRED",
        "missing_requirements": missing,
        "locked_split_strategy": split.strategy,
        "external_independent_adjudication_required": True,
        "formal_evidence_emitted": False,
        "scientific_pass_emitted": False,
        "caller_formal_metadata_ignored": ignored,
    }


def _validate_preprocessing_fit(train: Sequence[int], fit_indices: Optional[Sequence[int]]) -> None:
    if fit_indices is None:
        return
    if not set(int(i) for i in fit_indices).issubset(set(int(i) for i in train)):
        raise LeakageDetected("target-derived or normalization preprocessing used held-out rows")


def _design_matrix(dataset: BenchmarkDataset, family: str, fit_indices: Sequence[int]) -> tuple[np.ndarray, tuple[str, ...], dict[str, Any]]:
    key = FEATURE_KEYS[family]
    blocks = [np.asarray(dataset.features["psd"], dtype=float)]
    if family != "PSD":
        blocks.append(np.asarray(dataset.features[key], dtype=float))
    if family == "PSD_PLUS_TRIADIC_FC":
        blocks.insert(1, np.asarray(dataset.features["pairwise_fc"], dtype=float))
    if family == "PSD_PLUS_DIRECTED_HYPERGRAPH":
        blocks.insert(1, np.asarray(dataset.features["pairwise_fc"], dtype=float))
    names = ["psd"] + (["pairwise_fc"] if family in {"PSD_PLUS_TRIADIC_FC", "PSD_PLUS_DIRECTED_HYPERGRAPH"} else [])
    if family != "PSD" and family not in {"PSD_PLUS_TRIADIC_FC", "PSD_PLUS_DIRECTED_HYPERGRAPH"}:
        names.append(key)
    if family == "PSD_PLUS_TRIADIC_FC":
        names.append("triadic_fc")
    if family == "PSD_PLUS_DIRECTED_HYPERGRAPH":
        names.append("directed_hypergraph")
    controls = []
    control_names = []
    for name in CONTROL_KEYS:
        if name in dataset.controls:
            arr = np.asarray(dataset.controls[name], dtype=float)
            arr = arr[:, None] if arr.ndim == 1 else arr
            controls.append(arr)
            control_names.append(name)
    pair_count = dataset.controls.get("pairwise_feature_count")
    if pair_count is None:
        pair_count = np.full(dataset.n_rows, np.asarray(dataset.features.get("pairwise_fc", blocks[0])).shape[1], dtype=float)
    dim = dataset.controls.get("feature_dim")
    if dim is None:
        dim = np.full(dataset.n_rows, sum(block.shape[1] for block in blocks), dtype=float)
    controls.extend([np.asarray(pair_count, dtype=float)[:, None], np.asarray(dim, dtype=float)[:, None]])
    control_names.extend(["pairwise_feature_count", "feature_dim"])
    if controls:
        blocks.extend(controls)
    matrix = np.concatenate(blocks, axis=1)
    train = matrix[np.asarray(fit_indices, dtype=int)]
    mean = train.mean(axis=0)
    scale = train.std(axis=0)
    scale[scale < 1e-12] = 1.0
    return (matrix - mean) / scale, tuple(names + control_names), {
        "missing_controls": [name for name in CONTROL_KEYS if name not in dataset.controls],
        "feature_dim": int(matrix.shape[1]),
    }


def _fit_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray, reg: float) -> np.ndarray:
    x_train = np.column_stack([np.ones(len(x_train)), x_train])
    x_test = np.column_stack([np.ones(len(x_test)), x_test])
    weights = np.zeros(x_train.shape[1], dtype=float)
    scale = max(1.0, float(np.linalg.norm(x_train, ord=2) ** 2 / max(1, len(x_train))))
    lr = 0.8 / scale
    y_train = np.asarray(y_train, dtype=float)
    for _ in range(700):
        logits = np.clip(x_train @ weights, -30, 30)
        probs = 1.0 / (1.0 + np.exp(-logits))
        gradient = (x_train.T @ (probs - y_train)) / len(y_train)
        gradient[1:] += reg * weights[1:]
        weights -= lr * gradient
    return 1.0 / (1.0 + np.exp(-np.clip(x_test @ weights, -30, 30)))


def _log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=float), 1e-7, 1 - 1e-7)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log1p(-p)))


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def _auroc(y: np.ndarray, p: np.ndarray) -> Optional[float]:
    y = np.asarray(y, dtype=int)
    if len(np.unique(y)) < 2:
        return None
    scores = np.asarray(p, dtype=float)
    _, inverse, counts = np.unique(scores, return_inverse=True, return_counts=True)
    average_ranks = np.cumsum(counts) - (counts - 1) / 2.0
    positives = y == 1
    positive_count = int(positives.sum())
    positive_rank_sum = float(average_ranks[inverse[positives]].sum())
    return float(
        (positive_rank_sum - positive_count * (positive_count + 1) / 2)
        / (positive_count * (len(y) - positive_count))
    )


def _auprc(y: np.ndarray, p: np.ndarray) -> Optional[float]:
    y = np.asarray(y, dtype=int)
    positives = int(y.sum())
    if positives == 0:
        return None
    scores = np.asarray(p)
    order = np.argsort(-scores, kind="mergesort")
    sorted_scores = scores[order]
    sorted_y = y[order]
    group_ends = np.flatnonzero(np.r_[sorted_scores[1:] != sorted_scores[:-1], True])
    cumulative_hits = np.cumsum(sorted_y)[group_ends]
    group_positive_counts = np.diff(np.r_[0, cumulative_hits])
    precision_at_threshold = cumulative_hits / (group_ends + 1)
    return float(np.sum(group_positive_counts * precision_at_threshold) / positives)


def _ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    total = 0.0
    for low, high in zip(np.linspace(0, 1, bins + 1)[:-1], np.linspace(0, 1, bins + 1)[1:]):
        mask = (p >= low) & ((p < high) if high < 1 else (p <= high))
        if np.any(mask):
            total += float(mask.mean()) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return total


def _gain_p_value(y: np.ndarray, baseline: np.ndarray, candidate: np.ndarray, observed: float, seed: int) -> float:
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(100):
        shuffled = rng.permutation(y)
        null.append(_log_loss(shuffled, baseline) - _log_loss(shuffled, candidate))
    return float((1 + sum(value >= observed for value in null)) / (len(null) + 1))


def _bootstrap_ci(y: np.ndarray, baseline: np.ndarray, candidate: np.ndarray, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    gains = []
    for _ in range(100):
        indices = rng.integers(0, len(y), len(y))
        gains.append(_log_loss(y[indices], baseline[indices]) - _log_loss(y[indices], candidate[indices]))
    return float(np.quantile(gains, 0.025)), float(np.quantile(gains, 0.975))


def _null_target(target: np.ndarray, kind: str, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    target = np.asarray(target, dtype=int)
    kind = kind.lower().replace("_", "-")
    if kind == "label-permutation" or kind == "matched-variance-surrogate":
        return rng.permutation(target)
    if kind == "circular-time-shift":
        return np.roll(target, int(rng.integers(1, len(target))))
    if kind == "block-shuffle":
        size = max(2, len(target) // 5)
        blocks = [target[i:i + size] for i in range(0, len(target), size)]
        rng.shuffle(blocks)
        return np.concatenate(blocks)[:len(target)]
    if kind == "matched-autocorrelation-surrogate":
        # Circular shifts preserve the empirical autocorrelation exactly.
        return np.roll(target, int(rng.integers(1, len(target))))
    raise ValueError(f"unknown null comparison: {kind}")


def run_benchmark(
    dataset: BenchmarkDataset,
    *,
    split_strategy: str = "subject-held-out",
    test_subjects: Optional[Sequence[Any]] = None,
    test_sessions: Optional[Sequence[Any]] = None,
    cutoff: Optional[float] = None,
    validation_fraction: float = 0.2,
    preprocessing_fit_indices: Optional[Sequence[int]] = None,
    regularization_grid: Sequence[float] = (0.01, 0.1, 1.0),
    seed: int = 0,
) -> BenchmarkReport:
    """Run the four-model ladder with locked nested validation."""
    try:
        dataset.validate()
        if not dataset.synthetic and not bool(dataset.provenance.get("complete", False)):
            return _failure_report(dataset, ForecastStatus.INSUFFICIENT_DATA, "complete provenance is required for non-synthetic forecast evidence")
        split = locked_split(
            dataset.subjects, dataset.sessions, dataset.timestamps, split_strategy,
            test_subjects=test_subjects, test_sessions=test_sessions, cutoff=cutoff,
            validation_fraction=validation_fraction,
        )
        validate_split(split, dataset.subjects, dataset.sessions, dataset.timestamps)
        _validate_preprocessing_fit(split.train, preprocessing_fit_indices)
        required = {"psd", "pairwise_fc", "triadic_fc", "directed_hypergraph"}
        missing = sorted(required - set(dataset.features))
        if missing:
            return _failure_report(dataset, ForecastStatus.INSUFFICIENT_DATA, f"missing feature blocks: {missing}")
        if len(split.test) < 2 or len(set(np.asarray(dataset.target)[list(split.test)].tolist())) < 2:
            return _failure_report(dataset, ForecastStatus.INSUFFICIENT_DATA, "held-out target has insufficient class support")
    except LeakageDetected as exc:
        return _failure_report(dataset, ForecastStatus.LEAKAGE_DETECTED, str(exc))
    except (ValueError, KeyError, TypeError) as exc:
        status = ForecastStatus.INVALID_INPUT if "leak" not in str(exc).lower() else ForecastStatus.LEAKAGE_DETECTED
        return _failure_report(dataset, status, str(exc))

    train, validation, test = list(split.train), list(split.validation), list(split.test)
    y = np.asarray(dataset.target, dtype=int)
    results: list[IncrementalResult] = []
    predictions: dict[str, np.ndarray] = {}
    prior_loss: Optional[float] = None
    for index, family in enumerate(LADDER):
        x, controls_used, missingness = _design_matrix(dataset, family, train)
        candidates = list(regularization_grid)
        if not candidates or any(float(value) <= 0 or not np.isfinite(value) for value in candidates):
            return _failure_report(dataset, ForecastStatus.INVALID_INPUT, "regularization_grid must contain positive finite values")
        selected = float(candidates[0])
        if validation:
            scores = []
            for reg in candidates:
                p_val = _fit_predict(x[train], y[train], x[validation], float(reg))
                scores.append((_log_loss(y[validation], p_val), float(reg)))
            selected = min(scores, key=lambda item: (item[0], item[1]))[1]
        p = _fit_predict(x[train], y[train], x[test], selected)
        predictions[family] = p
        loss = _log_loss(y[test], p)
        gain = None if prior_loss is None else float(prior_loss - loss)
        beats_previous = prior_loss is None or loss < prior_loss
        if not beats_previous:
            status = ForecastStatus.NO_INCREMENTAL_GAIN.value
        elif dataset.synthetic:
            status = ForecastStatus.SYNTHETIC_DEMO_ONLY.value
        else:
            # A held-out proper-score improvement is useful benchmark output,
            # but cannot establish a formal, causal, or scientific conclusion.
            status = ForecastStatus.INCONCLUSIVE.value
        baseline_prediction = p if prior_loss is None else predictions[LADDER[index - 1]]
        p_value = None if prior_loss is None else _gain_p_value(y[test], baseline_prediction, p, gain or 0.0, seed + index)
        ci = None if prior_loss is None else _bootstrap_ci(y[test], baseline_prediction, p, seed + 100 + index)
        results.append(IncrementalResult(
            model_family="deterministic_logistic",
            feature_family=family,
            train_rows=len(train), held_out_rows=len(test), log_loss=loss,
            brier_score=_brier(y[test], p), auroc=_auroc(y[test], p), auprc=_auprc(y[test], p),
            calibration_error=_ece(y[test], p), permutation_p_value=p_value,
            confidence_interval=ci, incremental_gain=gain, status=status,
            missingness=missingness, controls_used=controls_used,
            checksum=hashlib.sha256(p.tobytes()).hexdigest(),
        ))
        prior_loss = loss

    nulls = {}
    final = results[-1]
    for kind in ("label-permutation", "circular-time-shift", "block-shuffle", "matched-variance-surrogate", "matched-autocorrelation-surrogate"):
        surrogate = _null_target(y[test], kind, seed + len(nulls))
        nulls[kind] = {"log_loss": _log_loss(surrogate, predictions[LADDER[-1]]), "synthetic": bool(dataset.synthetic)}
    adjudication = _adjudication_summary(dataset, split)
    if dataset.synthetic:
        overall = ForecastStatus.SYNTHETIC_DEMO_ONLY.value
    elif adjudication["missing_requirements"] or any(
        result.status == ForecastStatus.INCONCLUSIVE.value for result in results
    ):
        overall = ForecastStatus.INCONCLUSIVE.value
    else:
        overall = ForecastStatus.NO_INCREMENTAL_GAIN.value
    split_data = split.to_dict()
    split_data["nested_validation"] = True
    missingness = {r.feature_family: r.missingness for r in results}
    report = BenchmarkReport(
        SCHEMA_VERSION, overall, dataset.provenance, split_data, float(dataset.prediction_horizon),
        dataset.target_definition, "deterministic_logistic", tuple(results), nulls, missingness,
        "", bool(dataset.synthetic),
        adjudication=adjudication,
        dataset_checksum=dataset.checksum(),
    )
    return _with_report_checksum(report)


def null_target(target: np.ndarray, kind: str, seed: int = 0) -> np.ndarray:
    """Public deterministic null generator used by audit/test code."""
    return _null_target(target, kind, seed)
