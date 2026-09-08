"""Deterministic, leakage-resistant split construction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

import numpy as np


@dataclass(frozen=True)
class LockedSplit:
    strategy: str
    train: tuple[int, ...]
    validation: tuple[int, ...]
    test: tuple[int, ...]
    cutoff: Optional[float] = None
    locked: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "train": list(self.train),
            "validation": list(self.validation),
            "test": list(self.test),
            "cutoff": self.cutoff,
            "locked": self.locked,
        }


def _as_tuple(values: Iterable[int]) -> tuple[int, ...]:
    return tuple(int(value) for value in values)


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
) -> LockedSplit:
    """Create a split without inspecting features or targets.

    Subject and session splits are group-disjoint. Forward-time splits use a
    caller-declared cutoff, and nested validation takes its validation rows
    from the training side only. No default is inferred from target values.
    """
    subjects = np.asarray(subjects)
    sessions = np.asarray(sessions)
    timestamps = np.asarray(timestamps, dtype=float)
    n = len(subjects)
    if not (len(sessions) == len(timestamps) == n):
        raise ValueError("subjects, sessions, and timestamps must have equal length")
    if n < 3:
        raise ValueError("at least three rows are required for a locked split")
    strategy = strategy.lower().replace("_", "-")
    all_indices = np.arange(n)
    if strategy == "subject-held-out":
        groups = list(dict.fromkeys(subjects.tolist()))
        held = set(test_subjects if test_subjects is not None else groups[-1:])
        test = all_indices[np.isin(subjects, list(held))]
        train = all_indices[~np.isin(subjects, list(held))]
        return _nested(train, test, "subject-held-out", validation_fraction)
    if strategy == "session-held-out":
        groups = list(dict.fromkeys(sessions.tolist()))
        held = set(test_sessions if test_sessions is not None else groups[-1:])
        test = all_indices[np.isin(sessions, list(held))]
        train = all_indices[~np.isin(sessions, list(held))]
        return _nested(train, test, "session-held-out", validation_fraction)
    if strategy == "forward-time":
        if cutoff is None or not np.isfinite(cutoff):
            raise ValueError("forward-time requires a finite, declared cutoff")
        train = all_indices[timestamps < cutoff]
        test = all_indices[timestamps >= cutoff]
        return _nested(train, test, "forward-time", validation_fraction, float(cutoff))
    raise ValueError(f"unknown locked split strategy: {strategy}")


def _nested(
    train: np.ndarray,
    test: np.ndarray,
    strategy: str,
    validation_fraction: float,
    cutoff: Optional[float] = None,
) -> LockedSplit:
    if len(train) == 0 or len(test) == 0:
        raise ValueError("locked split must have non-empty train and test groups")
    if not 0 <= validation_fraction < 1:
        raise ValueError("validation_fraction must be in [0, 1)")
    ordered = np.sort(train)
    n_validation = int(np.floor(len(ordered) * validation_fraction))
    if validation_fraction and n_validation == 0 and len(ordered) > 2:
        n_validation = 1
    validation = ordered[-n_validation:] if n_validation else np.array([], dtype=int)
    inner_train = ordered[:-n_validation] if n_validation else ordered
    if len(inner_train) == 0:
        raise ValueError("nested validation consumed all training rows")
    return LockedSplit(strategy, _as_tuple(inner_train), _as_tuple(validation), _as_tuple(np.sort(test)), cutoff)


def validate_split(
    split: LockedSplit,
    subjects: np.ndarray,
    sessions: np.ndarray,
    timestamps: np.ndarray,
) -> None:
    """Fail closed on subject/session/time overlap."""
    train = np.asarray(split.train, dtype=int)
    test = np.asarray(split.test, dtype=int)
    validation = np.asarray(split.validation, dtype=int)
    if set(train) & set(test) or set(train) & set(validation) or set(test) & set(validation):
        raise ValueError("locked split contains overlapping row indices")
    if split.strategy == "subject-held-out":
        if set(np.asarray(subjects)[train].tolist()) & set(np.asarray(subjects)[test].tolist()):
            raise ValueError("subject leakage detected")
    if split.strategy == "session-held-out":
        if set(np.asarray(sessions)[train].tolist()) & set(np.asarray(sessions)[test].tolist()):
            raise ValueError("session leakage detected")
    if split.strategy == "forward-time" and len(train) and len(test):
        if float(np.max(np.asarray(timestamps)[train])) >= float(np.min(np.asarray(timestamps)[test])):
            raise ValueError("temporal leakage detected")
