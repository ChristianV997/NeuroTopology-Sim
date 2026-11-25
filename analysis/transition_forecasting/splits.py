"""Deterministic, leakage-resistant split construction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Union

import numpy as np


@dataclass(frozen=True)
class LockedSplit:
    strategy: str
    train: tuple[int, ...]
    validation: tuple[int, ...]
    test: tuple[int, ...]
    cutoff: Optional[float] = None
    locked: bool = True
    purged: tuple[int, ...] = ()
    prediction_horizon: float = 0.0
    embargo: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "train": list(self.train),
            "validation": list(self.validation),
            "test": list(self.test),
            "purged": list(self.purged),
            "cutoff": self.cutoff,
            "prediction_horizon": self.prediction_horizon,
            "embargo": self.embargo,
            "locked": self.locked,
        }


def _as_tuple(values: Iterable[int]) -> tuple[int, ...]:
    return tuple(int(value) for value in values)


def _validate_non_negative_scalar(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative finite number, not bool")
    val = float(value)
    if not np.isfinite(val) or val < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return val


def _validate_group_labels(values: np.ndarray, name: str) -> None:
    if values.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    for item in values.tolist():
        if item is None:
            raise ValueError(f"{name} contains missing (None) group label")
        if isinstance(item, (float, np.floating)) and not np.isfinite(float(item)):
            raise ValueError(f"{name} contains non-finite group label")
        if isinstance(item, str) and not item.strip():
            raise ValueError(f"{name} contains empty group label")


def _validate_window_lengths(
    window_lengths: Optional[Union[float, np.ndarray]],
    n: int,
) -> np.ndarray:
    if window_lengths is None:
        return np.zeros(n, dtype=float)
    if isinstance(window_lengths, bool):
        raise ValueError("window_lengths must not be bool")
    arr = np.asarray(window_lengths)
    if arr.dtype == bool:
        raise ValueError("window_lengths must not be boolean")
    if arr.ndim == 0:
        val = _validate_non_negative_scalar(arr.item(), "window_lengths")
        return np.full(n, val, dtype=float)
    arr = np.asarray(arr, dtype=float)
    if arr.shape != (n,) or not np.all(np.isfinite(arr)) or np.any(arr < 0.0):
        raise ValueError("window_lengths must be finite, non-negative, and row-aligned")
    return arr


def _validate_metadata(
    subjects: Any,
    sessions: Any,
    timestamps: Any,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    subj = np.asarray(subjects)
    sess = np.asarray(sessions)
    ts_raw = np.asarray(timestamps)
    if ts_raw.dtype == bool:
        raise ValueError("timestamps must be numeric, not boolean")
    ts = np.asarray(ts_raw, dtype=float)
    if subj.ndim != 1 or sess.ndim != 1 or ts.ndim != 1:
        raise ValueError("subjects, sessions, and timestamps must be one-dimensional")
    n = len(subj)
    if not (len(sess) == len(ts) == n):
        raise ValueError("subjects, sessions, and timestamps must have equal length")
    if not np.all(np.isfinite(ts)):
        raise ValueError("timestamps must be finite")
    _validate_group_labels(subj, "subjects")
    _validate_group_labels(sess, "sessions")
    return subj, sess, ts


def locked_split(
    subjects: np.ndarray,
    sessions: np.ndarray,
    timestamps: np.ndarray,
    strategy: str,
    *,
    test_subjects: Optional[Iterable[Any]] = None,
    test_sessions: Optional[Iterable[Any]] = None,
    cutoff: Optional[float] = None,
    validation_fraction: float = 0.2,
    prediction_horizon: float = 0.0,
    window_lengths: Optional[Union[float, np.ndarray]] = None,
    embargo: float = 0.0,
) -> LockedSplit:
    """Create a group- and time-aware split without inspecting features or targets.

    Subject and session splits are group-disjoint across train, validation, and
    test. Forward-time splits use a caller-declared cutoff, sort by timestamps
    (never assuming monotonic input order), and purge overlapping feature
    windows, target horizons, and embargo intervals across both outer and
    nested boundaries.
    """
    subjects, sessions, timestamps = _validate_metadata(subjects, sessions, timestamps)
    n = len(subjects)
    if n < 3:
        raise ValueError("at least three rows are required for a locked split")
    if isinstance(validation_fraction, bool) or not np.isfinite(float(validation_fraction)):
        raise ValueError("validation_fraction must be a finite number in [0, 1)")
    validation_fraction = float(validation_fraction)
    if not 0.0 <= validation_fraction < 1.0:
        raise ValueError("validation_fraction must be in [0, 1)")
    horizon = _validate_non_negative_scalar(prediction_horizon, "prediction_horizon")
    embargo_val = _validate_non_negative_scalar(embargo, "embargo")
    win = _validate_window_lengths(window_lengths, n)

    strategy = strategy.lower().replace("_", "-")
    all_indices = np.arange(n)
    if strategy == "subject-held-out":
        groups = list(dict.fromkeys(subjects.tolist()))
        held = set(test_subjects if test_subjects is not None else groups[-1:])
        test = all_indices[np.isin(subjects, list(held))]
        train = all_indices[~np.isin(subjects, list(held))]
        return _nested_group(
            train, test, subjects, "subject-held-out", validation_fraction,
            horizon=horizon, embargo=embargo_val,
        )
    if strategy == "session-held-out":
        groups = list(dict.fromkeys(sessions.tolist()))
        held = set(test_sessions if test_sessions is not None else groups[-1:])
        test = all_indices[np.isin(sessions, list(held))]
        train = all_indices[~np.isin(sessions, list(held))]
        return _nested_group(
            train, test, sessions, "session-held-out", validation_fraction,
            horizon=horizon, embargo=embargo_val,
        )
    if strategy == "forward-time":
        if cutoff is None or isinstance(cutoff, bool) or not np.isfinite(float(cutoff)):
            raise ValueError("forward-time requires a finite, declared cutoff")
        cutoff_val = float(cutoff)
        test = all_indices[timestamps >= cutoff_val]
        raw_train = all_indices[timestamps < cutoff_val]
        if len(raw_train) == 0 or len(test) == 0:
            raise ValueError("locked split must have non-empty train and test groups")
        test_earliest_start = float(np.min(timestamps[test] - win[test]))
        purge_limit = min(cutoff_val, test_earliest_start)
        keep_mask = (timestamps[raw_train] + horizon + embargo_val) <= purge_limit
        outer_purged = raw_train[~keep_mask]
        clean_train = raw_train[keep_mask]
        return _nested_forward_time(
            clean_train, test, outer_purged, timestamps, win,
            validation_fraction=validation_fraction,
            cutoff=cutoff_val,
            horizon=horizon,
            embargo=embargo_val,
        )
    raise ValueError(f"unknown locked split strategy: {strategy}")


def _nested_group(
    train: np.ndarray,
    test: np.ndarray,
    groups: np.ndarray,
    strategy: str,
    validation_fraction: float,
    *,
    horizon: float = 0.0,
    embargo: float = 0.0,
) -> LockedSplit:
    if len(train) == 0 or len(test) == 0:
        raise ValueError("locked split must have non-empty train and test groups")
    if validation_fraction == 0.0:
        return LockedSplit(
            strategy, _as_tuple(np.sort(train)), (), _as_tuple(np.sort(test)),
            cutoff=None, prediction_horizon=horizon, embargo=embargo,
        )
    train_groups = list(dict.fromkeys(groups[train].tolist()))
    if len(train_groups) < 2:
        raise ValueError(f"{strategy} nested validation requires at least two training groups")
    n_val_groups = int(np.floor(len(train_groups) * validation_fraction))
    if n_val_groups == 0:
        n_val_groups = 1
    if n_val_groups >= len(train_groups):
        n_val_groups = len(train_groups) - 1
    val_group_set = set(train_groups[-n_val_groups:])
    val_mask = np.isin(groups[train], list(val_group_set))
    validation = np.sort(train[val_mask])
    inner_train = np.sort(train[~val_mask])
    if len(inner_train) == 0 or len(validation) == 0:
        raise ValueError("nested group validation failed to produce non-empty train and validation splits")
    return LockedSplit(
        strategy, _as_tuple(inner_train), _as_tuple(validation), _as_tuple(np.sort(test)),
        cutoff=None, prediction_horizon=horizon, embargo=embargo,
    )


def _nested_forward_time(
    train: np.ndarray,
    test: np.ndarray,
    outer_purged: np.ndarray,
    timestamps: np.ndarray,
    window_lengths: np.ndarray,
    *,
    validation_fraction: float,
    cutoff: float,
    horizon: float,
    embargo: float,
) -> LockedSplit:
    if len(train) == 0 or len(test) == 0:
        raise ValueError("locked split must have non-empty train and test groups after horizon/window purging")
    order = train[np.argsort(timestamps[train], kind="mergesort")]
    if validation_fraction == 0.0:
        return LockedSplit(
            "forward-time", _as_tuple(np.sort(order)), (), _as_tuple(np.sort(test)),
            cutoff=cutoff, purged=_as_tuple(np.sort(outer_purged)),
            prediction_horizon=horizon, embargo=embargo,
        )
    unique_times = np.unique(timestamps[order])
    if len(unique_times) < 2:
        raise ValueError("forward-time nested validation requires at least two distinct training timestamps")
    n_val = int(np.floor(len(order) * validation_fraction))
    if n_val == 0 and len(order) > 2:
        n_val = 1
    if n_val >= len(order):
        n_val = len(order) - 1
    val_cutoff = float(timestamps[order[-n_val]])
    validation = order[timestamps[order] >= val_cutoff]
    raw_inner = order[timestamps[order] < val_cutoff]
    if len(raw_inner) == 0 or len(validation) == 0:
        raise ValueError("forward-time nested validation consumed all training rows")
    val_earliest_start = float(np.min(timestamps[validation] - window_lengths[validation]))
    inner_limit = min(val_cutoff, val_earliest_start)
    inner_keep = (timestamps[raw_inner] + horizon + embargo) <= inner_limit
    inner_purged = raw_inner[~inner_keep]
    inner_train = raw_inner[inner_keep]
    if len(inner_train) == 0:
        raise ValueError("forward-time nested purging consumed all inner training rows")
    all_purged = np.concatenate([outer_purged, inner_purged]) if len(inner_purged) else outer_purged
    return LockedSplit(
        "forward-time",
        _as_tuple(np.sort(inner_train)),
        _as_tuple(np.sort(validation)),
        _as_tuple(np.sort(test)),
        cutoff=cutoff,
        purged=_as_tuple(np.sort(all_purged)),
        prediction_horizon=horizon,
        embargo=embargo,
    )


def validate_split(
    split: LockedSplit,
    subjects: np.ndarray,
    sessions: np.ndarray,
    timestamps: np.ndarray,
    *,
    prediction_horizon: Optional[float] = None,
    window_lengths: Optional[Union[float, np.ndarray]] = None,
    embargo: Optional[float] = None,
) -> None:
    """Fail closed on subject, session, temporal, horizon, or window-overlap leakage."""
    subjects, sessions, timestamps = _validate_metadata(subjects, sessions, timestamps)
    n = len(subjects)
    train = np.asarray(split.train, dtype=int)
    test = np.asarray(split.test, dtype=int)
    validation = np.asarray(split.validation, dtype=int)
    purged = np.asarray(split.purged, dtype=int)
    for part_name, part in (("train", train), ("validation", validation), ("test", test), ("purged", purged)):
        if len(part) and (int(np.min(part)) < 0 or int(np.max(part)) >= n):
            raise ValueError(f"locked split {part_name} contains out-of-bounds indices")
    sets = (set(train.tolist()), set(validation.tolist()), set(test.tolist()), set(purged.tolist()))
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            if sets[i] & sets[j]:
                raise ValueError("locked split contains overlapping row indices")
    if split.strategy == "subject-held-out":
        for a, b in ((train, test), (train, validation), (validation, test)):
            if len(a) and len(b) and (set(subjects[a].tolist()) & set(subjects[b].tolist())):
                raise ValueError("subject leakage detected")
    if split.strategy == "session-held-out":
        for a, b in ((train, test), (train, validation), (validation, test)):
            if len(a) and len(b) and (set(sessions[a].tolist()) & set(sessions[b].tolist())):
                raise ValueError("session leakage detected")
    if split.strategy == "forward-time":
        horizon = _validate_non_negative_scalar(
            split.prediction_horizon if prediction_horizon is None else prediction_horizon,
            "prediction_horizon",
        )
        embargo_val = _validate_non_negative_scalar(
            split.embargo if embargo is None else embargo,
            "embargo",
        )
        win = _validate_window_lengths(window_lengths, n)
        for earlier, later in ((train, validation), (train, test), (validation, test)):
            if len(earlier) and len(later):
                earliest_later_ts = float(np.min(timestamps[later]))
                earliest_later_start = float(np.min(timestamps[later] - win[later]))
                max_earlier_ts = float(np.max(timestamps[earlier]))
                max_earlier_end = float(np.max(timestamps[earlier] + horizon + embargo_val))
                if max_earlier_ts >= earliest_later_ts:
                    raise ValueError("temporal leakage detected")
                if max_earlier_end > earliest_later_start:
                    raise ValueError("horizon or overlapping-window leakage detected")
