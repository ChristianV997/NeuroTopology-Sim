"""Generic, modality-agnostic transition-trajectory summaries.

Every function here operates on plain numeric arrays/lists — no EEG, fMRI,
or topology-specific assumptions, no neuroscience interpretation, and no
statistical overclaiming. Malformed input raises ValueError with a clear
message; genuinely insufficient data (too few timepoints, no recovery leg,
...) returns an explicit `{"status": "insufficient_data", ...}` dict rather
than fabricating a number. All return values are plain, JSON-serializable
Python (no numpy scalar/array leakage).
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Sequence

import numpy as np


def _to_matrix(trajectory: Sequence[Sequence[float]] | Sequence[float]) -> np.ndarray:
    matrix = np.asarray(trajectory, dtype=float)
    if matrix.ndim == 1:
        matrix = matrix.reshape(-1, 1)
    if matrix.ndim != 2 or matrix.shape[0] < 1 or matrix.shape[1] < 1:
        raise ValueError(
            "trajectory must be a non-empty 1D sequence or 2D (n_timepoints, n_features) sequence"
        )
    if not np.all(np.isfinite(matrix)):
        raise ValueError("trajectory must contain only finite values")
    return matrix


def trajectory_mean_delta(trajectory: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Endpoint-to-endpoint change per feature: matrix[-1] - matrix[0]."""
    matrix = _to_matrix(trajectory)
    if matrix.shape[0] < 2:
        raise ValueError("trajectory_mean_delta requires at least two timepoints")
    delta = matrix[-1] - matrix[0]
    return {
        "status": "ok",
        "delta_per_feature": delta.tolist(),
        "mean_abs_delta": float(np.mean(np.abs(delta))),
        "n_timepoints": int(matrix.shape[0]),
        "n_features": int(matrix.shape[1]),
    }


def transition_velocity(
    trajectory: Sequence[Sequence[float]], timestamps: Sequence[float] | None = None
) -> dict[str, Any]:
    """First-difference rate of change per feature, per unit time.

    `timestamps` defaults to unit sample steps (0, 1, 2, ...) if omitted.
    """
    matrix = _to_matrix(trajectory)
    n = matrix.shape[0]
    if n < 2:
        raise ValueError("transition_velocity requires at least two timepoints")
    ts = np.asarray(timestamps, dtype=float) if timestamps is not None else np.arange(n, dtype=float)
    if ts.shape[0] != n:
        raise ValueError("timestamps length must match the number of trajectory timepoints")
    dt = np.diff(ts)
    if np.any(dt <= 0):
        raise ValueError("timestamps must be strictly increasing")
    velocity = np.diff(matrix, axis=0) / dt[:, None]
    speed = np.linalg.norm(velocity, axis=1)
    return {
        "status": "ok",
        "velocity_per_step": velocity.tolist(),
        "mean_speed": float(np.mean(speed)),
        "max_speed": float(np.max(speed)),
        "n_steps": int(velocity.shape[0]),
    }


def transition_acceleration(
    trajectory: Sequence[Sequence[float]], timestamps: Sequence[float] | None = None
) -> dict[str, Any]:
    """Second-difference rate of change per feature. Needs >= 3 timepoints."""
    matrix = _to_matrix(trajectory)
    n = matrix.shape[0]
    if n < 3:
        return {
            "status": "insufficient_data",
            "reason": "transition_acceleration requires at least three timepoints",
        }
    ts = np.asarray(timestamps, dtype=float) if timestamps is not None else np.arange(n, dtype=float)
    if ts.shape[0] != n:
        raise ValueError("timestamps length must match the number of trajectory timepoints")
    dt = np.diff(ts)
    if np.any(dt <= 0):
        raise ValueError("timestamps must be strictly increasing")
    velocity = np.diff(matrix, axis=0) / dt[:, None]
    vt = ts[:-1] + dt / 2.0  # velocity samples are centered between original timestamps
    dvt = np.diff(vt)
    if np.any(dvt <= 0):
        raise ValueError("degenerate timestamp spacing for acceleration computation")
    acceleration = np.diff(velocity, axis=0) / dvt[:, None]
    magnitude = np.linalg.norm(acceleration, axis=1)
    return {
        "status": "ok",
        "acceleration_per_step": acceleration.tolist(),
        "mean_magnitude": float(np.mean(magnitude)),
        "n_steps": int(acceleration.shape[0]),
    }


def transition_variance(trajectory: Sequence[Sequence[float]]) -> dict[str, Any]:
    matrix = _to_matrix(trajectory)
    variance = matrix.var(axis=0)
    return {
        "status": "ok",
        "variance_per_feature": variance.tolist(),
        "mean_variance": float(np.mean(variance)),
        "n_timepoints": int(matrix.shape[0]),
    }


def dwell_time_summary(
    labels: Sequence[str], sample_duration_s: float | None = None
) -> dict[str, Any]:
    """Consecutive-run-length summary of a categorical label sequence.

    Sample-count based by default (no time unit assumed); pass
    `sample_duration_s` (uniform inter-sample interval) to also report
    seconds-based dwell times.
    """
    seq = list(labels)
    if not seq:
        raise ValueError("dwell_time_summary requires at least one label")

    runs: list[tuple[str, int]] = []
    current_label = seq[0]
    current_len = 1
    for label in seq[1:]:
        if label == current_label:
            current_len += 1
        else:
            runs.append((current_label, current_len))
            current_label = label
            current_len = 1
    runs.append((current_label, current_len))

    per_label_run_lengths: dict[str, list[int]] = {}
    for label, length in runs:
        per_label_run_lengths.setdefault(label, []).append(length)

    per_label_summary: dict[str, dict[str, Any]] = {}
    for label, lengths in per_label_run_lengths.items():
        total_samples = sum(lengths)
        entry: dict[str, Any] = {
            "n_runs": len(lengths),
            "total_samples": total_samples,
            "mean_run_length_samples": float(np.mean(lengths)),
            "fraction_of_sequence": total_samples / len(seq),
        }
        if sample_duration_s is not None:
            entry["mean_run_length_s"] = float(np.mean(lengths)) * sample_duration_s
            entry["total_duration_s"] = total_samples * sample_duration_s
        per_label_summary[label] = entry

    return {
        "status": "ok",
        "n_samples": len(seq),
        "n_runs": len(runs),
        "per_label": per_label_summary,
        "time_unit": "seconds" if sample_duration_s is not None else "samples",
    }


def hysteresis_summary(
    forward_trajectory: Sequence[Sequence[float]],
    backward_trajectory: Sequence[Sequence[float]] | None,
) -> dict[str, Any]:
    """Coarse forward-vs-return path divergence, resampled to a common length.

    Returns `insufficient_data` if no return/recovery leg is available —
    hysteresis is only meaningful when a transition and its reverse both
    exist. This is a structural distance indicator only, not a claim about
    reversibility or any particular mechanism.
    """
    if backward_trajectory is None or len(backward_trajectory) == 0:
        return {
            "status": "insufficient_data",
            "reason": "no return/recovery trajectory was provided",
        }

    forward = _to_matrix(forward_trajectory)
    backward = _to_matrix(backward_trajectory)
    if forward.shape[1] != backward.shape[1]:
        raise ValueError("forward and backward trajectories must have the same feature count")
    if forward.shape[0] < 2 or backward.shape[0] < 2:
        return {
            "status": "insufficient_data",
            "reason": "both legs require at least two timepoints",
        }

    forward_path = forward.mean(axis=1)
    backward_path = backward.mean(axis=1)[::-1]  # reverse so both legs run start->end

    n_common = max(len(forward_path), len(backward_path))
    x_forward = np.linspace(0.0, 1.0, len(forward_path))
    x_backward = np.linspace(0.0, 1.0, len(backward_path))
    x_common = np.linspace(0.0, 1.0, n_common)
    forward_resampled = np.interp(x_common, x_forward, forward_path)
    backward_resampled = np.interp(x_common, x_backward, backward_path)

    gap = np.abs(forward_resampled - backward_resampled)
    return {
        "status": "ok",
        "hysteresis_gap_mean": float(np.mean(gap)),
        "hysteresis_gap_max": float(np.max(gap)),
        "n_resample_points": int(n_common),
    }


def label_balance_check(labels: Sequence[str]) -> dict[str, Any]:
    seq = list(labels)
    if not seq:
        raise ValueError("label_balance_check requires at least one label")
    counts = Counter(seq)
    total = len(seq)
    proportions = {label: count / total for label, count in counts.items()}
    imbalance_ratio = (
        max(counts.values()) / min(counts.values()) if len(counts) > 1 else None
    )
    return {
        "status": "ok",
        "counts": dict(counts),
        "proportions": proportions,
        "n_classes": len(counts),
        "imbalance_ratio": imbalance_ratio,
    }


def subject_pairing_check(
    subject_ids_a: Sequence[str], subject_ids_b: Sequence[str]
) -> dict[str, Any]:
    """Which subjects appear on both sides of a two-condition comparison."""
    set_a, set_b = set(subject_ids_a), set(subject_ids_b)
    paired = sorted(set_a & set_b)
    result = {
        "status": "ok" if paired else "insufficient_data",
        "n_paired": len(paired),
        "paired_subjects": paired,
        "unpaired_a": sorted(set_a - set_b),
        "unpaired_b": sorted(set_b - set_a),
    }
    if not paired:
        result["reason"] = "no subject appears on both sides of the comparison"
    return result
