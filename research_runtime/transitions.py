"""Leakage-safe discrete feature-state transition operators."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Any, Iterable, Sequence

import numpy as np


def _as_matrix(features: Sequence[Sequence[float]]) -> np.ndarray:
    matrix = np.asarray(features, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 2 or matrix.shape[1] < 1:
        raise ValueError("features must be a two-dimensional matrix with at least two rows")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("features must be finite")
    return matrix


@dataclass(frozen=True)
class FeatureStateModel:
    """Frozen standardization and k-means state representation."""

    means: tuple[float, ...]
    scales: tuple[float, ...]
    centroids: tuple[tuple[float, ...], ...]
    seed: int

    @property
    def n_states(self) -> int:
        return len(self.centroids)

    @property
    def n_features(self) -> int:
        return len(self.means)

    def transform(self, features: Sequence[Sequence[float]]) -> np.ndarray:
        matrix = _as_matrix(features)
        if matrix.shape[1] != self.n_features:
            raise ValueError("feature count does not match the frozen state model")
        standardized = (matrix - np.asarray(self.means)) / np.asarray(self.scales)
        centers = np.asarray(self.centroids)
        distances = ((standardized[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        return np.argmin(distances, axis=1).astype(int)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fit_feature_state_model(
    features: Sequence[Sequence[float]], *, n_states: int = 4, seed: int = 0, max_iter: int = 100
) -> FeatureStateModel:
    """Fit deterministic k-means on development features only."""
    matrix = _as_matrix(features)
    if n_states < 2 or n_states > matrix.shape[0]:
        raise ValueError("n_states must be between two and the number of rows")
    if max_iter < 1:
        raise ValueError("max_iter must be positive")
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales = np.where(scales > np.finfo(float).eps, scales, 1.0)
    standardized = (matrix - means) / scales
    rng = np.random.default_rng(seed)
    centers = standardized[rng.choice(len(standardized), size=n_states, replace=False)].copy()
    for _ in range(max_iter):
        distances = ((standardized[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels = np.argmin(distances, axis=1)
        updated = centers.copy()
        for state in range(n_states):
            members = standardized[labels == state]
            if len(members):
                updated[state] = members.mean(axis=0)
        if np.allclose(updated, centers, rtol=0.0, atol=1e-12):
            centers = updated
            break
        centers = updated
    return FeatureStateModel(tuple(means.tolist()), tuple(scales.tolist()), tuple(map(tuple, centers.tolist())), seed)


def _entropy(probabilities: np.ndarray) -> float:
    positive = probabilities[probabilities > 0]
    return float(-np.sum(positive * np.log2(positive)))


def transition_operator(state_ids: Sequence[int], sequence_ids: Sequence[str]) -> dict[str, Any]:
    """Build one row-normalized operator per sequence, never crossing boundaries."""
    states = np.asarray(state_ids, dtype=int)
    sequences = np.asarray(sequence_ids, dtype=str)
    if states.ndim != 1 or sequences.shape != states.shape:
        raise ValueError("state_ids and sequence_ids must be aligned one-dimensional arrays")
    if len(states) < 2 or np.any(states < 0):
        raise ValueError("at least two non-negative state observations are required")
    n_states = int(states.max()) + 1
    operators: dict[str, np.ndarray] = {}
    counts: dict[str, int] = {}
    for sequence in dict.fromkeys(sequences.tolist()):
        indices = np.flatnonzero(sequences == sequence)
        matrix = np.zeros((n_states, n_states), dtype=float)
        if len(indices) > 1:
            for left, right in zip(indices[:-1], indices[1:]):
                matrix[states[left], states[right]] += 1.0
        row_sums = matrix.sum(axis=1, keepdims=True)
        normalized = np.divide(matrix, row_sums, out=np.zeros_like(matrix), where=row_sums > 0)
        operators[str(sequence)] = normalized
        counts[str(sequence)] = int(matrix.sum())
    return {
        "n_states": n_states,
        "operators": {key: value.tolist() for key, value in operators.items()},
        "transition_counts": counts,
    }


def operator_metrics(operator: Sequence[Sequence[float]]) -> dict[str, float]:
    """Compute interpretable metrics for a row-normalized transition operator."""
    matrix = np.asarray(operator, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or not np.all(np.isfinite(matrix)):
        raise ValueError("operator must be a finite square matrix")
    row_entropies = np.asarray([_entropy(row) for row in matrix])
    occupancy = matrix.sum(axis=0)
    occupancy = occupancy / occupancy.sum() if occupancy.sum() else occupancy
    reversibility = float(np.mean(np.abs(matrix - matrix.T)))
    return {
        "transition_entropy": float(np.mean(row_entropies)),
        "self_transition_probability": float(np.trace(matrix) / matrix.shape[0]),
        "reversibility_asymmetry": reversibility,
        "occupancy_entropy": _entropy(occupancy) if occupancy.sum() else 0.0,
    }


def jensen_shannon_distance(first: Sequence[Sequence[float]], second: Sequence[Sequence[float]], alpha: float = 0.5) -> float:
    """Average row-wise Jensen-Shannon distance with additive smoothing."""
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    if a.shape != b.shape or a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise ValueError("operators must be aligned square matrices")
    a = (a + alpha) / (a + alpha).sum(axis=1, keepdims=True)
    b = (b + alpha) / (b + alpha).sum(axis=1, keepdims=True)
    midpoint = 0.5 * (a + b)
    divergence = 0.5 * np.sum(a * np.log2(a / midpoint), axis=1) + 0.5 * np.sum(b * np.log2(b / midpoint), axis=1)
    return float(np.mean(np.sqrt(np.maximum(divergence, 0.0))))
