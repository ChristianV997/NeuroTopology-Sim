"""Wilson score confidence interval for binomial proportions.

Provides exact Wilson score confidence intervals for binomial events (e.g.,
False Positive Rate, True Positive Rate, sensitivity, specificity) with
declared critical values, explicit boundary validation (0 <= k <= n), and
explicit non-estimate reporting when evaluation trial count is zero (n = 0).
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
from typing import Any
import numpy as np


def get_z_score(confidence_level: float = 0.95, z: float | None = None) -> float:
    """Return standard normal critical value z for a two-sided confidence interval.

    Args:
        confidence_level: Confidence level in (0, 1). Defaults to 0.95.
        z: Optional explicitly declared z critical value. If provided, overrides confidence_level.

    Returns:
        Positive float z value.

    Raises:
        ValueError: If confidence_level is not in (0, 1) or z is not positive.
    """
    if z is not None:
        if not math.isfinite(z) or z <= 0.0:
            raise ValueError(f"Declared z critical value must be finite and positive, got {z}")
        return float(z)

    if not math.isfinite(confidence_level) or not (0.0 < confidence_level < 1.0):
        raise ValueError(
            f"confidence_level must be strictly between 0 and 1, got {confidence_level}"
        )

    # Standard normal two-sided quantile: Phi^{-1}(1 - alpha / 2)
    alpha = 1.0 - confidence_level
    p = 1.0 - alpha / 2.0
    return float(statistics.NormalDist().inv_cdf(p))


@dataclass(frozen=True)
class WilsonIntervalResult:
    """Result of a Wilson score confidence interval calculation.

    Attributes:
        k: Observed event count (0 <= k <= n).
        n: Total trial count (n >= 0).
        proportion: Point estimate k / n, or None if n == 0.
        confidence_level: Declared confidence level (e.g., 0.95).
        z: Critical normal value used for interval calculation.
        lower: Lower confidence bound in [0, 1], or None if n == 0.
        upper: Upper confidence bound in [0, 1], or None if n == 0.
        half_width: (upper - lower) / 2, or None if n == 0.
        full_width: upper - lower, or None if n == 0.
        status: "estimated" if n > 0 else "unavailable_zero_trials".
        is_available: True if n > 0, False if n == 0.
        continuity_corrected: Whether continuity correction was applied.
    """

    k: int
    n: int
    proportion: float | None
    confidence_level: float
    z: float
    lower: float | None
    upper: float | None
    half_width: float | None
    full_width: float | None
    status: str
    is_available: bool
    continuity_corrected: bool = False


def _validate_counts(k: Any, n: Any) -> tuple[int, int]:
    """Validate that k and n are valid non-negative integers satisfying 0 <= k <= n."""
    # Disallow bool (which is a subclass of int in Python)
    if isinstance(k, bool) or isinstance(n, bool):
        raise TypeError("Counts k and n must be integers, not booleans.")

    if not isinstance(k, (int, np.integer)) or not isinstance(n, (int, np.integer)):
        raise TypeError(
            f"Counts k and n must be integers, got k: {type(k).__name__}, n: {type(n).__name__}"
        )

    k_int = int(k)
    n_int = int(n)

    if k_int < 0:
        raise ValueError(f"Event count k must be non-negative, got {k_int}")
    if n_int < 0:
        raise ValueError(f"Total trials n must be non-negative, got {n_int}")
    if k_int > n_int:
        raise ValueError(f"Observed count k ({k_int}) cannot exceed total trials n ({n_int})")

    return k_int, n_int


def wilson_score_interval(
    k: int,
    n: int,
    confidence_level: float = 0.95,
    z: float | None = None,
    continuity_correction: bool = False,
) -> WilsonIntervalResult:
    """Calculate the Wilson score confidence interval for a binomial proportion.

    Formula (Standard Wilson):
        p_tilde = (k + z^2 / 2) / (n + z^2)
        margin = (z / (n + z^2)) * sqrt(k * (n - k) / n + z^2 / 4)
        lower = max(0.0, p_tilde - margin)
        upper = min(1.0, p_tilde + margin)

    Boundary Cases:
        - k = 0: lower = 0.0, upper = z^2 / (n + z^2)
        - k = n: lower = 1.0 - z^2 / (n + z^2), upper = 1.0
        - n = 0: status="unavailable_zero_trials", bounds=None

    Args:
        k: Number of observed events (e.g. false positives).
        n: Total number of independent evaluation trials.
        confidence_level: Two-sided confidence level in (0, 1). Default 0.95.
        z: Explicit normal critical value (e.g. 1.959963984540054).
        continuity_correction: If True, applies standard continuity correction.

    Returns:
        WilsonIntervalResult instance.

    Raises:
        TypeError: If k or n are non-integers or booleans.
        ValueError: If k < 0, n < 0, or k > n.
    """
    k_val, n_val = _validate_counts(k, n)
    z_val = get_z_score(confidence_level=confidence_level, z=z)

    # Explicit guard: Zero-trial evaluation cannot support any empirical measurement
    if n_val == 0:
        return WilsonIntervalResult(
            k=0,
            n=0,
            proportion=None,
            confidence_level=confidence_level,
            z=z_val,
            lower=None,
            upper=None,
            half_width=None,
            full_width=None,
            status="unavailable_zero_trials",
            is_available=False,
            continuity_corrected=continuity_correction,
        )

    p_hat = k_val / float(n_val)
    z2 = z_val * z_val
    denom = float(n_val) + z2

    if not continuity_correction:
        p_tilde = (float(k_val) + 0.5 * z2) / denom
        variance_term = (float(k_val * (n_val - k_val)) / float(n_val)) + 0.25 * z2
        margin = (z_val / denom) * math.sqrt(max(0.0, variance_term))

        lower_bound = max(0.0, p_tilde - margin)
        upper_bound = min(1.0, p_tilde + margin)
    else:
        # Continuity-corrected Wilson interval (Newcombe, 1998)
        if k_val == 0:
            lower_bound = 0.0
            upper_bound = min(1.0, (z2 + 1.0 + z_val * math.sqrt(z2 + 2.0)) / (float(n_val) + z2))
        elif k_val == n_val:
            lower_bound = max(0.0, 1.0 - (z2 + 1.0 + z_val * math.sqrt(z2 + 2.0)) / (float(n_val) + z2))
            upper_bound = 1.0
        else:
            # Lower bound with continuity correction
            term_l = 2.0 * float(k_val) + z2 - 1.0 - z_val * math.sqrt(
                z2 - (2.0 + 1.0 / float(n_val)) + 4.0 * p_hat * (float(n_val) * (1.0 - p_hat) + 1.0)
            )
            lower_bound = max(0.0, term_l / (2.0 * denom))

            # Upper bound with continuity correction
            term_u = 2.0 * float(k_val) + z2 + 1.0 + z_val * math.sqrt(
                z2 + (2.0 - 1.0 / float(n_val)) + 4.0 * p_hat * (float(n_val) * (1.0 - p_hat) - 1.0)
            )
            upper_bound = min(1.0, term_u / (2.0 * denom))

    full_w = upper_bound - lower_bound
    half_w = full_w / 2.0

    return WilsonIntervalResult(
        k=k_val,
        n=n_val,
        proportion=p_hat,
        confidence_level=confidence_level,
        z=z_val,
        lower=lower_bound,
        upper=upper_bound,
        half_width=half_w,
        full_width=full_w,
        status="estimated",
        is_available=True,
        continuity_corrected=continuity_correction,
    )
