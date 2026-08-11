"""Normalization modes for phase-space coordinates.

Three modes, all deliberately transparent -- no fitted parameters, no
learned scaling, no black-box transform. Each returns either a numeric value
or an explicit `None` plus a reason, so a caller can never mistake "could not
normalize" for "normalized to zero".
"""
from __future__ import annotations

from typing import Optional, Sequence

RAW = "raw"
WITHIN_RECORD = "within_record"
ZSCORE_IF_AVAILABLE = "zscore_if_available"

MODES: tuple[str, ...] = (RAW, WITHIN_RECORD, ZSCORE_IF_AVAILABLE)


class NormalizationError(ValueError):
    """Raised when an unknown normalization mode is requested."""


def normalize_raw(contributing_deltas: Sequence[float]) -> tuple[Optional[float], Optional[str]]:
    """Mean of the contributing signed deltas, in the source units.

    Unbounded and unit-carrying by design: `raw` is a pass-through aggregate,
    useful only when the caller already knows the source units and does not
    intend to compare across features or datasets.
    """
    values = list(contributing_deltas)
    if not values:
        return None, "no contributing feature deltas"
    return sum(values) / len(values), None


def normalize_within_record(
    contributing_deltas: Sequence[float], all_deltas: Sequence[float]
) -> tuple[Optional[float], Optional[str]]:
    """Signed share of the record's total absolute feature-change mass.

    value = sum(contributing_deltas) / sum(|all_deltas|)

    This is bounded to [-1, 1] by construction, with no clamping:

        |sum(contributing)| <= sum(|contributing|) <= sum(|all|) = denominator

    so the ratio cannot escape the interval as long as the denominator is
    non-zero. It is interpretable as "the signed fraction of everything that
    changed in this record which is attributable to this axis's features".

    Returns `(None, reason)` when the record shows no change at all, since a
    share of zero total change is undefined rather than zero.
    """
    contributing = list(contributing_deltas)
    if not contributing:
        return None, "no contributing feature deltas"

    denominator = sum(abs(v) for v in all_deltas)
    if denominator <= 0.0:
        return None, (
            "record reports zero total absolute feature change; a share of "
            "zero change is undefined, not zero"
        )

    return sum(contributing) / denominator, None


def normalize_zscore_if_available(
    contributing_deltas: Sequence[float],
    reference_stats: Optional[dict] = None,
    feature_names: Optional[Sequence[str]] = None,
) -> tuple[Optional[float], Optional[str]]:
    """Z-score against an explicit external reference distribution.

    Requires `reference_stats` mapping each contributing feature name to a
    `{"mean": float, "std": float}` entry, supplied by the caller from the
    transition record's own metadata. This repository's transition records do
    not currently carry such a reference, so in practice this mode returns
    `(None, reason)` -- which is the honest answer, not a fallback to another
    mode.
    """
    contributing = list(contributing_deltas)
    if not contributing:
        return None, "no contributing feature deltas"
    if not reference_stats:
        return None, (
            "no reference mean/std distribution available on the transition "
            "record (metadata.feature_reference_stats); z-scoring is not "
            "possible and is not silently substituted with another mode"
        )

    names = list(feature_names or [])
    if len(names) != len(contributing):
        return None, "reference stats requested but feature names are unaligned"

    scores: list[float] = []
    for name, delta in zip(names, contributing):
        stats = reference_stats.get(name)
        if not isinstance(stats, dict):
            return None, f"no reference stats entry for feature '{name}'"
        mean, std = stats.get("mean"), stats.get("std")
        if not isinstance(mean, (int, float)) or not isinstance(std, (int, float)):
            return None, f"reference stats for '{name}' lack numeric mean/std"
        if std <= 0:
            return None, f"reference std for '{name}' is non-positive"
        scores.append((delta - mean) / std)

    return sum(scores) / len(scores), None


def apply(
    mode: str,
    *,
    contributing_deltas: Sequence[float],
    all_deltas: Sequence[float],
    reference_stats: Optional[dict] = None,
    contributing_names: Optional[Sequence[str]] = None,
) -> tuple[Optional[float], Optional[str]]:
    """Dispatch to the requested mode. Unknown modes fail loudly."""
    if mode == RAW:
        return normalize_raw(contributing_deltas)
    if mode == WITHIN_RECORD:
        return normalize_within_record(contributing_deltas, all_deltas)
    if mode == ZSCORE_IF_AVAILABLE:
        return normalize_zscore_if_available(
            contributing_deltas, reference_stats, contributing_names
        )
    raise NormalizationError(
        f"unknown normalization mode '{mode}'; choose one of {list(MODES)}"
    )
