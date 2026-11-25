"""Bounded triadic functional-connectivity estimators.

The measures in this module are statistical dependence features.  They are not
causal influence, biological mechanism, consciousness, or quantum-coherence
measures.  They are also deliberately separate from graph beta-1, spatial
phase winding/charge, scalar chirality, and directed causal estimators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


SCHEMA_VERSION = "triadic-functional-connectivity-v1"
DIAGNOSTIC_STATUS_FINITE = "FINITE"
SUPPORTED_SURROGATES = ("amplitude_shuffle", "phase_shuffle", "circular_shift", "block_shift")


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_safe(value: Any) -> Any:
    """Convert dataclasses/NumPy values to strict JSON-compatible values."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, np.floating)):
        return _finite_float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize a value deterministically and reject non-finite numbers."""

    safe = _json_safe(value)
    return json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def canonical_checksum(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def array_checksum(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array, dtype=np.float64)
    header = canonical_json({"dtype": str(contiguous.dtype), "shape": list(contiguous.shape)})
    digest = sha256()
    digest.update(header.encode("utf-8"))
    digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def _validate_matrix(data: Any, *, name: str = "data") -> np.ndarray:
    array = np.asarray(data, dtype=np.float64)
    if array.ndim != 2:
        raise ValueError(f"{name} must have shape (channels, samples), got {array.shape}")
    if array.shape[0] < 3:
        raise ValueError(f"{name} shape {array.shape} must contain at least three channels")
    if array.shape[1] < 4:
        raise ValueError(f"{name} shape {array.shape} must contain at least four samples")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains NaN or Infinity")
    return array


def _validate_labels(labels: Sequence[Any] | None, size: int, *, name: str) -> tuple[str, ...] | None:
    if labels is None:
        return None
    if len(labels) != size:
        raise ValueError(f"{name} length {len(labels)} does not match expected length {size}")
    result = tuple(str(item) for item in labels)
    if any(not item for item in result):
        raise ValueError(f"{name} cannot contain empty labels")
    return result


@dataclass(frozen=True)
class SignalWindow:
    """Validated input signal or feature window.

    ``data`` always uses channels-by-samples orientation.  A feature matrix is
    accepted through the same record because each row is still an input feature
    channel and each column is an observation.  No implicit transpose occurs.
    """

    data: np.ndarray
    sample_rate_hz: float | None = None
    timestamps: tuple[float, ...] | None = None
    channel_labels: tuple[str, ...] | None = None
    condition_labels: tuple[str, ...] | None = None
    source_id: str = "unknown"
    input_kind: str = "signal"
    synthetic_demo: bool = False

    def __post_init__(self) -> None:
        array = _validate_matrix(self.data)
        object.__setattr__(self, "data", array)
        if self.sample_rate_hz is not None:
            rate = _finite_float(self.sample_rate_hz)
            if rate is None or rate <= 0:
                raise ValueError("sample_rate_hz must be finite and positive")
            object.__setattr__(self, "sample_rate_hz", rate)
        channels, samples = array.shape
        channel_labels = _validate_labels(self.channel_labels, channels, name="channel_labels")
        if channel_labels is not None and len(set(channel_labels)) != len(channel_labels):
            raise ValueError("channel_labels must be unique")
        object.__setattr__(self, "channel_labels", channel_labels)
        condition_labels = _validate_labels(self.condition_labels, samples, name="condition_labels")
        object.__setattr__(self, "condition_labels", condition_labels)
        if self.timestamps is not None:
            timestamps = tuple(float(item) for item in self.timestamps)
            if len(timestamps) != samples or not np.isfinite(timestamps).all():
                raise ValueError("timestamps must be finite and have shape (samples,)")
            if any(right <= left for left, right in zip(timestamps, timestamps[1:])):
                raise ValueError("timestamps must be strictly increasing")
            object.__setattr__(self, "timestamps", timestamps)
        if self.input_kind not in {"signal", "feature_matrix"}:
            raise ValueError("input_kind must be 'signal' or 'feature_matrix'")
        if not isinstance(self.source_id, str) or not self.source_id:
            raise ValueError("source_id must be a non-empty string")

    @property
    def source_checksum(self) -> str:
        return array_checksum(self.data)

    @property
    def channel_count(self) -> int:
        return int(self.data.shape[0])

    @property
    def sample_count(self) -> int:
        return int(self.data.shape[1])


@dataclass(frozen=True)
class Provenance:
    source_id: str
    source_checksum: str
    parameter_checksum: str
    synthetic_demo: bool
    input_kind: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_checksum": self.source_checksum,
            "parameter_checksum": self.parameter_checksum,
            "synthetic_demo": self.synthetic_demo,
            "input_kind": self.input_kind,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class TriadicInteraction:
    channels: tuple[int, int, int]
    channel_labels: tuple[str, str, str]
    matrix_entropy_score: float | None
    nonlinear_interaction_score: float | None
    combined_score: float | None
    sample_count: int
    condition_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "channels": list(self.channels),
            "channel_labels": list(self.channel_labels),
            "matrix_entropy_score": self.matrix_entropy_score,
            "nonlinear_interaction_score": self.nonlinear_interaction_score,
            "combined_score": self.combined_score,
            "sample_count": self.sample_count,
            "condition_label": self.condition_label,
        }


@dataclass(frozen=True)
class TriadicEntropySummary:
    estimator: str
    triad_count: int
    top_k: int
    mean_score: float | None
    median_score: float | None
    max_score: float | None
    finite_value_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimator": self.estimator,
            "triad_count": self.triad_count,
            "top_k": self.top_k,
            "mean_score": self.mean_score,
            "median_score": self.median_score,
            "max_score": self.max_score,
            "finite_value_status": self.finite_value_status,
        }


@dataclass(frozen=True)
class SurrogateComparison:
    method: str
    seed: int
    n_surrogates: int
    observed_score: float | None
    surrogate_scores: tuple[float, ...]
    null_mean: float | None
    null_std: float | None
    z_score: float | None
    p_value: float | None
    finite_value_status: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "seed": self.seed,
            "n_surrogates": self.n_surrogates,
            "observed_score": self.observed_score,
            "surrogate_scores": list(self.surrogate_scores),
            "null_mean": self.null_mean,
            "null_std": self.null_std,
            "z_score": self.z_score,
            "p_value": self.p_value,
            "finite_value_status": self.finite_value_status,
            "status": self.status,
        }


@dataclass(frozen=True)
class TriadicConnectivityResult:
    schema_version: str
    interactions: tuple[TriadicInteraction, ...]
    top_triads: tuple[TriadicInteraction, ...]
    entropy_summaries: tuple[TriadicEntropySummary, ...]
    surrogate_comparisons: tuple[SurrogateComparison, ...]
    effective_channel_count: int
    pairwise_control: dict[str, Any]
    psd_control: dict[str, Any]
    community_summary: dict[str, Any]
    hierarchy_summary: dict[str, Any]
    condition_summary: dict[str, int]
    optional_dependency_status: dict[str, str]
    complexity_telemetry: dict[str, Any]
    finite_value_status: str
    provenance: Provenance
    provenance_checksum: str
    warnings: tuple[str, ...] = ()

    def to_dict(self, *, include_checksum: bool = True) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "interactions": [item.to_dict() for item in self.interactions],
            "top_triads": [item.to_dict() for item in self.top_triads],
            "entropy_summaries": [item.to_dict() for item in self.entropy_summaries],
            "surrogate_comparisons": [item.to_dict() for item in self.surrogate_comparisons],
            "effective_channel_count": self.effective_channel_count,
            "pairwise_control": self.pairwise_control,
            "psd_control": self.psd_control,
            "community_summary": self.community_summary,
            "hierarchy_summary": self.hierarchy_summary,
            "condition_summary": self.condition_summary,
            "optional_dependency_status": self.optional_dependency_status,
            "complexity_telemetry": self.complexity_telemetry,
            "finite_value_status": self.finite_value_status,
            "provenance": self.provenance.to_dict(),
            "warnings": list(self.warnings),
        }
        if include_checksum:
            payload["provenance_checksum"] = self.provenance_checksum
        return _json_safe(payload)

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    def write_json(self, path: str | Path) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.to_json() + "\n", encoding="utf-8")


def _standardize(row: np.ndarray) -> np.ndarray:
    centered = row - float(np.mean(row))
    scale = float(np.std(centered))
    return centered / scale if scale > 1e-12 else np.zeros_like(centered)


def _pairwise_correlation(data: np.ndarray) -> np.ndarray:
    standardized = np.vstack([_standardize(row) for row in data])
    correlation = standardized @ standardized.T / max(data.shape[1] - 1, 1)
    correlation = np.clip((correlation + correlation.T) / 2.0, -1.0, 1.0)
    diagonal = np.diag(correlation).copy()
    for index, value in enumerate(diagonal):
        if value <= 1e-12:
            correlation[index, index] = 1.0
    return correlation


def _matrix_entropy_dependence(rows: np.ndarray) -> float | None:
    correlation = _pairwise_correlation(rows)
    eigenvalues = np.linalg.eigvalsh((correlation + correlation.T) / 2.0)
    eigenvalues = np.clip(eigenvalues, 0.0, None)
    total = float(np.sum(eigenvalues))
    if total <= 1e-12:
        return None
    probabilities = eigenvalues / total
    entropy = -float(np.sum(probabilities[probabilities > 0] * np.log(probabilities[probabilities > 0])))
    maximum = math.log(rows.shape[0])
    return _finite_float(max(0.0, min(1.0, (maximum - entropy) / maximum)))


def _residual(target: np.ndarray, predictors: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(target.size), predictors.T])
    coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
    return target - design @ coefficients


def _nonlinear_interaction(rows: np.ndarray) -> float | None:
    residuals = np.vstack(
        [
            _residual(rows[0], rows[1:]),
            _residual(rows[1], rows[[0, 2]]),
            _residual(rows[2], rows[:2]),
        ]
    )
    product = residuals[0] * residuals[1] * residuals[2]
    denominator = float(np.sqrt(np.mean(product * product)))
    if denominator <= 1e-12:
        return None
    return _finite_float(min(1.0, abs(float(np.mean(product))) / denominator))


def _score_triads(data: np.ndarray, candidates: Sequence[tuple[int, int, int]], labels: Sequence[str]) -> list[TriadicInteraction]:
    interactions: list[TriadicInteraction] = []
    for triad in candidates:
        ordered_triad = tuple(sorted(triad, key=lambda index: labels[index]))
        rows = data[list(ordered_triad)]
        entropy_score = _matrix_entropy_dependence(rows)
        nonlinear_score = _nonlinear_interaction(rows)
        values = [value for value in (entropy_score, nonlinear_score) if value is not None]
        combined = _finite_float(max(values)) if values else None
        interactions.append(
            TriadicInteraction(
                channels=ordered_triad,
                channel_labels=tuple(labels[index] for index in ordered_triad),
                matrix_entropy_score=entropy_score,
                nonlinear_interaction_score=nonlinear_score,
                combined_score=combined,
                sample_count=int(data.shape[1]),
            )
        )
    return interactions


def _candidate_channels(data: np.ndarray, labels: Sequence[str], max_channels: int) -> tuple[int, ...]:
    variances = np.var(data, axis=1)
    order = sorted(range(data.shape[0]), key=lambda index: (-float(variances[index]), labels[index], index))
    return tuple(sorted(order[:max_channels]))


def _candidate_triads(channels: Sequence[int], max_triads: int) -> tuple[tuple[int, int, int], str, int]:
    count = math.comb(len(channels), 3)
    if count <= max_triads:
        return tuple(combinations(channels, 3)), "exhaustive_bounded", count

    # Sparse deterministic stencil.  The width is selected from the requested
    # cap, so the generator never walks all O(N^3) combinations.
    width = max(2, int(math.sqrt(max_triads / max(len(channels), 1))) + 2)
    generated: set[tuple[int, int, int]] = set()
    for anchor, first in enumerate(channels):
        for offset_j in range(1, width + 1):
            second_index = anchor + offset_j
            if second_index >= len(channels):
                break
            for offset_k in range(offset_j + 1, width + 2):
                third_index = anchor + offset_k
                if third_index >= len(channels):
                    break
                generated.add((first, channels[second_index], channels[third_index]))
                if len(generated) >= max_triads:
                    ordered = tuple(sorted(generated))[:max_triads]
                    return ordered, "sparse_bounded", count
    return tuple(sorted(generated))[:max_triads], "sparse_bounded", count


def _pairwise_control(correlation: np.ndarray) -> dict[str, Any]:
    upper = np.abs(correlation[np.triu_indices(correlation.shape[0], k=1)])
    return {
        "method": "Pearson correlation control",
        "mean_absolute_connectivity": _finite_float(np.mean(upper)) if upper.size else None,
        "max_absolute_connectivity": _finite_float(np.max(upper)) if upper.size else None,
        "finite_value_status": DIAGNOSTIC_STATUS_FINITE,
    }


def _psd_control(correlation: np.ndarray) -> dict[str, Any]:
    eigenvalues = np.linalg.eigvalsh((correlation + correlation.T) / 2.0)
    minimum = float(np.min(eigenvalues))
    return {
        "matrix": "pairwise_correlation",
        "minimum_eigenvalue": _finite_float(minimum),
        "is_psd_with_tolerance": bool(minimum >= -1e-8),
        "tolerance": 1e-8,
        "finite_value_status": DIAGNOSTIC_STATUS_FINITE,
    }


def _community_summary(correlation: np.ndarray, labels: Sequence[str], threshold: float = 0.5) -> dict[str, Any]:
    parent = list(range(len(labels)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for left, right in combinations(range(len(labels)), 2):
        if abs(float(correlation[left, right])) >= threshold:
            union(left, right)
    groups: dict[int, list[str]] = {}
    for index, label in enumerate(labels):
        groups.setdefault(find(index), []).append(label)
    communities = sorted((sorted(items) for items in groups.values()), key=lambda items: (items[0], len(items)))
    return {
        "method": "thresholded pairwise connectivity components",
        "threshold": threshold,
        "communities": [{"channels": items, "size": len(items)} for items in communities],
        "interpretation": "descriptive grouping; not a causal or biological hierarchy",
    }


def _hierarchy_summary(correlation: np.ndarray, labels: Sequence[str]) -> dict[str, Any]:
    strengths = np.mean(np.abs(correlation - np.eye(correlation.shape[0])), axis=1)
    ranked = sorted(range(len(labels)), key=lambda index: (-float(strengths[index]), labels[index]))
    return {
        "method": "ranked pairwise strength",
        "levels": [
            {"rank": rank + 1, "channel": labels[index], "strength": _finite_float(strengths[index])}
            for rank, index in enumerate(ranked)
        ],
        "interpretation": "descriptive ranking; not directed influence or mechanism",
    }


def _surrogate(data: np.ndarray, method: str, rng: np.random.Generator, block_size: int | None) -> np.ndarray:
    if method == "amplitude_shuffle":
        return np.vstack([row[rng.permutation(row.size)] for row in data])
    if method == "phase_shuffle":
        result = np.empty_like(data)
        for index, row in enumerate(data):
            spectrum = np.fft.rfft(row)
            phases = rng.uniform(-math.pi, math.pi, spectrum.size)
            phases[0] = 0.0
            if row.size % 2 == 0:
                phases[-1] = 0.0
            result[index] = np.fft.irfft(np.abs(spectrum) * np.exp(1j * phases), n=row.size)
        return result
    if method in {"circular_shift", "block_shift"}:
        result = np.empty_like(data)
        size = max(1, int(block_size or max(1, data.shape[1] // 4)))
        for index, row in enumerate(data):
            shift = int(rng.integers(1, max(2, row.size)))
            if method == "block_shift":
                shift = (shift // size) * size
                shift = shift % row.size
            result[index] = np.roll(row, shift)
        return result
    raise ValueError(f"unsupported surrogate method: {method}")


def _summary(estimator: str, values: Sequence[float | None], top_k: int) -> TriadicEntropySummary:
    finite = np.asarray([value for value in values if value is not None and math.isfinite(float(value))], dtype=float)
    return TriadicEntropySummary(
        estimator=estimator,
        triad_count=len(values),
        top_k=top_k,
        mean_score=_finite_float(np.mean(finite)) if finite.size else None,
        median_score=_finite_float(np.median(finite)) if finite.size else None,
        max_score=_finite_float(np.max(finite)) if finite.size else None,
        finite_value_status=DIAGNOSTIC_STATUS_FINITE,
    )


def estimate_triadic_connectivity(
    data: Any = None,
    *,
    feature_matrix: Any = None,
    channel_labels: Sequence[Any] | None = None,
    condition_labels: Sequence[Any] | None = None,
    timestamps: Sequence[float] | None = None,
    sample_rate_hz: float | None = None,
    source_id: str = "unknown",
    input_kind: str = "signal",
    synthetic_demo: bool = False,
    top_k: int = 10,
    max_triads: int = 256,
    max_channels: int = 64,
    max_memory_mb: float = 256.0,
    surrogate_methods: Sequence[str] = (),
    n_surrogates: int = 0,
    seed: int = 0,
    block_size: int | None = None,
) -> TriadicConnectivityResult:
    """Estimate bounded triadic dependence from signals or feature matrices.

    The input orientation is strictly ``(channels, samples)``.  Candidate
    triads are exhaustive only while their count remains under ``max_triads``;
    otherwise a deterministic sparse stencil is used.  The estimator never
    materializes all combinations for an unbounded channel count.
    """

    if data is not None and feature_matrix is not None:
        raise ValueError("provide either data or feature_matrix, not both")
    source = feature_matrix if feature_matrix is not None else data
    if source is None:
        raise ValueError("data or feature_matrix is required")
    if isinstance(source, SignalWindow):
        window = source
        if any(item is not None for item in (channel_labels, condition_labels, timestamps, sample_rate_hz)):
            window = SignalWindow(
                data=source.data,
                sample_rate_hz=sample_rate_hz if sample_rate_hz is not None else source.sample_rate_hz,
                timestamps=tuple(timestamps) if timestamps is not None else source.timestamps,
                channel_labels=tuple(channel_labels) if channel_labels is not None else source.channel_labels,
                condition_labels=tuple(condition_labels) if condition_labels is not None else source.condition_labels,
                source_id=source_id if source_id != "unknown" else source.source_id,
                input_kind=input_kind if input_kind != "signal" else source.input_kind,
                synthetic_demo=synthetic_demo or source.synthetic_demo,
            )
    else:
        window = SignalWindow(
            data=_validate_matrix(source),
            sample_rate_hz=sample_rate_hz,
            timestamps=tuple(timestamps) if timestamps is not None else None,
            channel_labels=tuple(str(item) for item in channel_labels) if channel_labels is not None else None,
            condition_labels=tuple(str(item) for item in condition_labels) if condition_labels is not None else None,
            source_id=source_id,
            input_kind="feature_matrix" if feature_matrix is not None else input_kind,
            synthetic_demo=synthetic_demo,
        )
    if top_k < 1 or max_triads < 1 or max_channels < 3:
        raise ValueError("top_k and max_triads must be positive; max_channels must be at least three")
    if n_surrogates < 0 or n_surrogates > 1000:
        raise ValueError("n_surrogates must be between 0 and 1000")
    if max_memory_mb <= 0 or not math.isfinite(float(max_memory_mb)):
        raise ValueError("max_memory_mb must be finite and positive")
    estimated_input_mb = window.data.nbytes / (1024 * 1024)
    if estimated_input_mb > max_memory_mb:
        raise MemoryError(f"input requires {estimated_input_mb:.3f} MiB, exceeds max_memory_mb={max_memory_mb}")
    methods = tuple(str(method) for method in surrogate_methods)
    unknown_methods = sorted(set(methods) - set(SUPPORTED_SURROGATES))
    if unknown_methods:
        raise ValueError(f"unsupported surrogate methods: {unknown_methods}")
    if methods and n_surrogates < 1:
        raise ValueError("n_surrogates must be positive when surrogate_methods are requested")

    labels = window.channel_labels or tuple(f"ch-{index:04d}" for index in range(window.channel_count))
    selected_channels = _candidate_channels(window.data, labels, min(max_channels, window.channel_count))
    candidates, generation_mode, theoretical_count = _candidate_triads(selected_channels, max_triads)
    selected_data = window.data[list(selected_channels)]
    selected_labels = tuple(labels[index] for index in selected_channels)
    correlation = _pairwise_correlation(selected_data)
    interactions = _score_triads(window.data, candidates, labels)
    ordered = tuple(
        sorted(
            interactions,
            key=lambda item: (-(item.combined_score if item.combined_score is not None else -1.0), item.channel_labels),
        )
    )
    top_triads = ordered[: min(top_k, len(ordered))]
    entropy_summaries = (
        _summary("matrix_entropy_covariance", [item.matrix_entropy_score for item in interactions], top_k),
        _summary("residualized_three_variable_dependence", [item.nonlinear_interaction_score for item in interactions], top_k),
    )

    observed_values = [item.combined_score for item in top_triads if item.combined_score is not None]
    observed_score = _finite_float(np.mean(observed_values)) if observed_values else None
    comparisons: list[SurrogateComparison] = []
    for method_index, method in enumerate(methods):
        rng = np.random.default_rng(int(seed) + method_index)
        null_scores: list[float] = []
        for _ in range(n_surrogates):
            surrogate_data = _surrogate(window.data, method, rng, block_size)
            surrogate_interactions = _score_triads(surrogate_data, candidates, labels)
            values = [item.combined_score for item in surrogate_interactions if item.combined_score is not None]
            if values:
                null_scores.append(float(np.mean(sorted(values, reverse=True)[: min(top_k, len(values))])))
        null_array = np.asarray(null_scores, dtype=float)
        null_mean = _finite_float(np.mean(null_array)) if null_array.size else None
        null_std = _finite_float(np.std(null_array, ddof=1)) if null_array.size > 1 else None
        z_score = None
        if observed_score is not None and null_mean is not None and null_std is not None and null_std > 1e-12:
            z_score = _finite_float((observed_score - null_mean) / null_std)
        p_value = None
        if observed_score is not None and null_array.size:
            p_value = _finite_float((1.0 + float(np.sum(null_array >= observed_score))) / (null_array.size + 1.0))
        comparisons.append(
            SurrogateComparison(
                method=method,
                seed=int(seed) + method_index,
                n_surrogates=n_surrogates,
                observed_score=observed_score,
                surrogate_scores=tuple(float(item) for item in null_array),
                null_mean=null_mean,
                null_std=null_std,
                z_score=z_score,
                p_value=p_value,
                finite_value_status=DIAGNOSTIC_STATUS_FINITE,
                status="COMPUTED" if null_array.size else "INCONCLUSIVE",
            )
        )

    variances = np.std(selected_data, axis=1)
    effective_channels = int(np.sum(variances > 1e-12))
    parameters = {
        "top_k": top_k,
        "max_triads": max_triads,
        "max_channels": max_channels,
        "max_memory_mb": max_memory_mb,
        "surrogate_methods": methods,
        "n_surrogates": n_surrogates,
        "seed": seed,
        "block_size": block_size,
    }
    provenance = Provenance(
        source_id=window.source_id,
        source_checksum=window.source_checksum,
        parameter_checksum=canonical_checksum(parameters),
        synthetic_demo=window.synthetic_demo,
        input_kind=window.input_kind,
        notes=(
            "Statistical triadic dependence only; not causal influence.",
            "Synthetic data is engineering validation, not empirical evidence." if window.synthetic_demo else "",
        ),
    )
    notes = tuple(item for item in provenance.notes if item)
    provenance = Provenance(**{**provenance.__dict__, "notes": notes})
    result_without_checksum = {
        "schema_version": SCHEMA_VERSION,
        "source_checksum": provenance.source_checksum,
        "parameter_checksum": provenance.parameter_checksum,
        "synthetic_demo": provenance.synthetic_demo,
        "top_triads": [item.to_dict() for item in top_triads],
        "surrogates": [item.to_dict() for item in comparisons],
    }
    provenance_checksum = canonical_checksum(result_without_checksum)
    telemetry = {
        "input_channels": window.channel_count,
        "input_samples": window.sample_count,
        "effective_channels": effective_channels,
        "candidate_channels": len(selected_channels),
        "candidate_triads": len(candidates),
        "theoretical_all_triads_for_selected_channels": theoretical_count,
        "triad_generation": generation_mode,
        "max_triads": max_triads,
        "estimated_input_memory_bytes": int(window.data.nbytes),
        "estimated_candidate_memory_bytes": int(len(candidates) * 3 * 8),
        "bounded": True,
    }
    return TriadicConnectivityResult(
        schema_version=SCHEMA_VERSION,
        interactions=tuple(interactions),
        top_triads=tuple(top_triads),
        entropy_summaries=entropy_summaries,
        surrogate_comparisons=tuple(comparisons),
        effective_channel_count=effective_channels,
        pairwise_control=_pairwise_control(correlation),
        psd_control=_psd_control(correlation),
        community_summary=_community_summary(correlation, selected_labels),
        hierarchy_summary=_hierarchy_summary(correlation, selected_labels),
        condition_summary={
            label: window.condition_labels.count(label)
            for label in sorted(set(window.condition_labels or ()))
        },
        optional_dependency_status={
            "numpy": "available_required",
            "scipy": "not_required",
            "mne": "not_required",
        },
        complexity_telemetry=telemetry,
        finite_value_status=DIAGNOSTIC_STATUS_FINITE,
        provenance=provenance,
        provenance_checksum=provenance_checksum,
        warnings=(
            "Triadic dependence is statistical and does not establish causation or biological mechanism.",
            "Graph beta-1, spatial phase winding/charge, scalar chirality, and directed causal influence are separate features.",
        ),
    )


__all__ = [
    "SCHEMA_VERSION",
    "SUPPORTED_SURROGATES",
    "SignalWindow",
    "Provenance",
    "TriadicInteraction",
    "TriadicEntropySummary",
    "SurrogateComparison",
    "TriadicConnectivityResult",
    "array_checksum",
    "canonical_checksum",
    "canonical_json",
    "estimate_triadic_connectivity",
]
