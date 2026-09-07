"""Descriptive null summaries and multiple-comparison metadata."""

from __future__ import annotations

import math

from .json_util import finite_or_none
from .schema import CORRECTION_METHODS


def effective_sample_size(n: int, lag1: float | None) -> float | None:
    if n <= 0:
        return None
    if lag1 is None or not math.isfinite(lag1) or abs(lag1) >= 1.0:
        return float(n)
    ess = n * (1.0 - lag1) / (1.0 + lag1)
    if not math.isfinite(ess) or ess <= 0:
        return float(n)
    return float(min(n, ess))


def empirical_percentile(observed: float | None, nulls: list[float]) -> float | None:
    if observed is None or not nulls:
        return None
    count = sum(1 for value in nulls if value <= observed)
    return count / len(nulls)


def exceedance_count(observed: float | None, nulls: list[float], *, tails: str = "two") -> int | None:
    if observed is None or not nulls:
        return None
    if tails == "greater":
        return sum(1 for value in nulls if value >= observed)
    if tails == "less":
        return sum(1 for value in nulls if value <= observed)
    return sum(1 for value in nulls if abs(value) >= abs(observed))


def permutation_p_value(observed: float | None, nulls: list[float], *, tails: str = "two") -> float | None:
    """(exceedances + 1) / (n + 1). Returns null if the null pool is empty."""
    if observed is None or not nulls:
        return None
    exceed = exceedance_count(observed, nulls, tails=tails)
    if exceed is None:
        return None
    return (exceed + 1) / (len(nulls) + 1)


def correct_p(p_value: float | None, *, method: str, n_tests: int | None) -> dict:
    method_l = (method or "none").lower()
    if method_l not in CORRECTION_METHODS:
        method_l = "none"
    tests = n_tests
    if tests is None:
        return {
            "correction_method": method_l,
            "n_tests": None,
            "multiplicity_status": "unknown",
            "p_value_corrected": None,
            "multiplicity_note": "n_tests is unknown; not silently treated as one test",
        }
    try:
        tests = int(tests)
    except (TypeError, ValueError):
        return {
            "correction_method": method_l,
            "n_tests": None,
            "multiplicity_status": "unknown",
            "p_value_corrected": None,
            "multiplicity_note": "n_tests is not an integer",
        }
    if tests < 1:
        return {
            "correction_method": method_l,
            "n_tests": tests,
            "multiplicity_status": "unknown",
            "p_value_corrected": None,
            "multiplicity_note": "n_tests < 1 is not a valid comparison count",
        }
    if p_value is None:
        corrected = None
    elif method_l == "none":
        corrected = p_value
    else:
        corrected = min(1.0, p_value * tests)
    return {
        "correction_method": method_l,
        "n_tests": tests,
        "multiplicity_status": method_l if tests > 1 or method_l != "none" else "single_test",
        "p_value_corrected": finite_or_none(corrected) if corrected is not None else None,
        "multiplicity_note": None,
    }
