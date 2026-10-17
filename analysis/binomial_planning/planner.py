"""Sample size planning for binomial operating characteristics.

Provides bounded, deterministic sample-size determination for Wilson score
precision targets (interval full-width, half-width / margin of error, and
zero-event upper bounds) for operating-characteristic quantities such as
False Positive Rate (FPR) and True Positive Rate (TPR).

Distinguishes between:
1. Pointwise precision guarantees at a declared design point p*.
2. Uniform worst-case precision guarantees across all p in [0, 1] (at p = 0.5).
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .wilson import get_z_score


@dataclass(frozen=True)
class SampleSizePlanResult:
    """Result of a sample size planning calculation.

    Attributes:
        target_metric: Metric targeted ("half_width", "full_width", or "zero_event_upper_bound").
        target_threshold: Declared target precision threshold.
        design_proportion: Assumed proportion p* for pointwise planning, or 0.5 for uniform.
        guarantee_type: "pointwise_at_p" or "uniform_worst_case".
        confidence_level: Declared confidence level (e.g., 0.95).
        z: Critical normal value used for calculation.
        required_n: Smallest integer n meeting the target, or None if exceeded max_n.
        achieved_metric_value: Exact metric value achieved at required_n, or None.
        search_bounded: True if a finite search bound was enforced.
        min_n_searched: Lower bound of search window.
        max_n_searched: Upper bound of search window.
        status: "found", "exceeded_max_n", or "invalid_target".
    """

    target_metric: str
    target_threshold: float
    design_proportion: float | None
    guarantee_type: str
    confidence_level: float
    z: float
    required_n: int | None
    achieved_metric_value: float | None
    search_bounded: bool
    min_n_searched: int
    max_n_searched: int
    status: str


def zero_event_upper_bound(
    n: int,
    confidence_level: float = 0.95,
    z: float | None = None,
) -> float:
    """Compute the Wilson score upper bound when zero events are observed (k = 0).

    Exact analytical formula:
        p_upper(0, n) = z^2 / (n + z^2)

    Example:
        For n = 16 and 95% confidence (z ~ 1.95996):
        p_upper = 3.8415 / (16 + 3.8415) = 19.36%
        A sample of 16 trials with 0 false positives only guarantees FPR < 19.4%,
        which cannot substantiate a strong low-FPR claim (< 5%).

    Args:
        n: Total number of trials (must be >= 1).
        confidence_level: Confidence level in (0, 1). Default 0.95.
        z: Explicit normal critical value.

    Returns:
        Upper bound in (0, 1).

    Raises:
        ValueError: If n < 1.
    """
    if isinstance(n, bool) or not isinstance(n, (int,)):
        raise TypeError(f"n must be an integer, got {type(n).__name__}")
    if n < 1:
        raise ValueError(f"n must be >= 1 to evaluate zero-event upper bound, got {n}")

    z_val = get_z_score(confidence_level=confidence_level, z=z)
    z2 = z_val * z_val
    return float(z2 / (float(n) + z2))


def plan_zero_event_sample_size(
    target_upper: float,
    confidence_level: float = 0.95,
    z: float | None = None,
    min_n: int = 1,
    max_n: int = 10_000_000,
) -> SampleSizePlanResult:
    """Find the smallest trial count n ensuring p_upper(0, n) <= target_upper.

    Analytical inversion of the Wilson zero-event formula:
        z^2 / (n + z^2) <= target_upper
        n >= z^2 * (1 / target_upper - 1)
        n* = ceil(z^2 * (1 / target_upper - 1))

    Args:
        target_upper: Required upper bound when k = 0 (e.g., 0.05 for 5% FPR upper bound).
        confidence_level: Confidence level in (0, 1). Default 0.95.
        z: Explicit normal critical value.
        min_n: Minimum trials to return (default 1).
        max_n: Maximum search bound before declaring exceeded (default 10,000,000).

    Returns:
        SampleSizePlanResult instance.
    """
    if not math.isfinite(target_upper) or not (0.0 < target_upper < 1.0):
        raise ValueError(f"target_upper must be in (0, 1), got {target_upper}")
    if min_n < 1:
        raise ValueError(f"min_n must be >= 1, got {min_n}")
    if max_n < min_n:
        raise ValueError(f"max_n ({max_n}) must be >= min_n ({min_n})")

    z_val = get_z_score(confidence_level=confidence_level, z=z)
    z2 = z_val * z_val

    # Analytical inversion
    raw_n = z2 * (1.0 / target_upper - 1.0)
    required_n = max(min_n, math.ceil(raw_n))

    if required_n > max_n:
        return SampleSizePlanResult(
            target_metric="zero_event_upper_bound",
            target_threshold=target_upper,
            design_proportion=0.0,
            guarantee_type="pointwise_at_p",
            confidence_level=confidence_level,
            z=z_val,
            required_n=None,
            achieved_metric_value=None,
            search_bounded=True,
            min_n_searched=min_n,
            max_n_searched=max_n,
            status="exceeded_max_n",
        )

    achieved = zero_event_upper_bound(required_n, confidence_level=confidence_level, z=z_val)

    return SampleSizePlanResult(
        target_metric="zero_event_upper_bound",
        target_threshold=target_upper,
        design_proportion=0.0,
        guarantee_type="pointwise_at_p",
        confidence_level=confidence_level,
        z=z_val,
        required_n=required_n,
        achieved_metric_value=achieved,
        search_bounded=True,
        min_n_searched=min_n,
        max_n_searched=max_n,
        status="found",
    )


def calculate_wilson_width_at_p(
    p: float,
    n: int,
    confidence_level: float = 0.95,
    z: float | None = None,
) -> float:
    """Compute the theoretical full width of a Wilson interval at proportion p.

    Formula:
        W(p, n) = (2 * z / (n + z^2)) * sqrt(n * p * (1 - p) + z^2 / 4)

    Special case at p = 0.5 (Uniform worst-case width):
        W(0.5, n) = z / sqrt(n + z^2)

    Args:
        p: Assumed or true proportion in [0, 1].
        n: Total number of trials (must be >= 1).
        confidence_level: Confidence level in (0, 1). Default 0.95.
        z: Explicit normal critical value.

    Returns:
        Full interval width in (0, 1].
    """
    if not math.isfinite(p) or not (0.0 <= p <= 1.0):
        raise ValueError(f"p must be in [0, 1], got {p}")
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"n must be an integer, got {type(n).__name__}")
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")

    z_val = get_z_score(confidence_level=confidence_level, z=z)
    z2 = z_val * z_val
    n_f = float(n)

    # Fast path for p = 0.5: W = z / sqrt(n + z^2)
    if math.isclose(p, 0.5, abs_tol=1e-15):
        return float(z_val / math.sqrt(n_f + z2))

    inner = n_f * p * (1.0 - p) + 0.25 * z2
    width = (2.0 * z_val / (n_f + z2)) * math.sqrt(max(0.0, inner))
    return float(width)


def plan_sample_size(
    target_width: float,
    design_p: float | None = None,
    is_half_width: bool = False,
    confidence_level: float = 0.95,
    z: float | None = None,
    min_n: int = 1,
    max_n: int = 10_000_000,
) -> SampleSizePlanResult:
    """Find the minimal trial count n meeting a Wilson precision criteria.

    Precision Guarantees:
        - Pointwise Guarantee (design_p is specified):
          Guarantees that when the empirical proportion is near design_p, the interval
          width <= target_width. Does NOT guarantee precision if the true proportion deviates.
        - Uniform Worst-Case Guarantee (design_p is None):
          Evaluates at p = 0.5 (maximum variance), guaranteeing that the interval width <= target_width
          regardless of what proportion is observed across the entire parameter space [0, 1].

    Args:
        target_width: Maximum acceptable interval width (or half-width if is_half_width=True).
        design_p: Assumed proportion in [0, 1] for pointwise guarantee, or None for uniform.
        is_half_width: If True, target_width is interpreted as half-width (margin of error).
        confidence_level: Confidence level in (0, 1). Default 0.95.
        z: Explicit normal critical value.
        min_n: Lower bound of search window (default 1).
        max_n: Upper bound of search window (default 10,000,000).

    Returns:
        SampleSizePlanResult instance.

    Raises:
        ValueError: If target_width is non-positive or >= 1.0 (or >= 0.5 for half-width).
    """
    if not math.isfinite(target_width) or target_width <= 0.0:
        raise ValueError(f"target_width must be positive and finite, got {target_width}")

    if is_half_width:
        if target_width >= 0.5:
            raise ValueError(f"target half-width must be < 0.5, got {target_width}")
        target_full_width = 2.0 * target_width
        metric_name = "half_width"
    else:
        if target_width >= 1.0:
            raise ValueError(f"target full-width must be < 1.0, got {target_width}")
        target_full_width = target_width
        metric_name = "full_width"

    if min_n < 1:
        raise ValueError(f"min_n must be >= 1, got {min_n}")
    if max_n < min_n:
        raise ValueError(f"max_n ({max_n}) must be >= min_n ({min_n})")

    z_val = get_z_score(confidence_level=confidence_level, z=z)

    if design_p is not None:
        if not math.isfinite(design_p) or not (0.0 <= design_p <= 1.0):
            raise ValueError(f"design_p must be in [0, 1], got {design_p}")
        eval_p = float(design_p)
        guarantee = "pointwise_at_p"
    else:
        eval_p = 0.5
        guarantee = "uniform_worst_case"

    # Fast analytical check for p = 0.5:
    # W(0.5, n) = z / sqrt(n + z^2) <= target_full_width
    # n + z^2 >= z^2 / W^2 => n >= z^2 * (1 / W^2 - 1)
    if math.isclose(eval_p, 0.5, abs_tol=1e-15):
        z2 = z_val * z_val
        w2 = target_full_width * target_full_width
        raw_n = z2 * (1.0 / w2 - 1.0)
        analytical_n = max(min_n, math.ceil(raw_n))

        if analytical_n > max_n:
            return SampleSizePlanResult(
                target_metric=metric_name,
                target_threshold=target_width,
                design_proportion=eval_p,
                guarantee_type=guarantee,
                confidence_level=confidence_level,
                z=z_val,
                required_n=None,
                achieved_metric_value=None,
                search_bounded=True,
                min_n_searched=min_n,
                max_n_searched=max_n,
                status="exceeded_max_n",
            )

        achieved_full_w = calculate_wilson_width_at_p(
            eval_p, analytical_n, confidence_level=confidence_level, z=z_val
        )
        achieved_metric = achieved_full_w / 2.0 if is_half_width else achieved_full_w

        return SampleSizePlanResult(
            target_metric=metric_name,
            target_threshold=target_width,
            design_proportion=eval_p,
            guarantee_type=guarantee,
            confidence_level=confidence_level,
            z=z_val,
            required_n=analytical_n,
            achieved_metric_value=achieved_metric,
            search_bounded=True,
            min_n_searched=min_n,
            max_n_searched=max_n,
            status="found",
        )

    # General p*: Monotonic integer binary search over [min_n, max_n]
    # W(p, n) strictly decreases with n.
    low = min_n
    high = max_n

    # Check if max_n is sufficient
    w_max = calculate_wilson_width_at_p(eval_p, max_n, confidence_level=confidence_level, z=z_val)
    if w_max > target_full_width:
        return SampleSizePlanResult(
            target_metric=metric_name,
            target_threshold=target_width,
            design_proportion=eval_p,
            guarantee_type=guarantee,
            confidence_level=confidence_level,
            z=z_val,
            required_n=None,
            achieved_metric_value=None,
            search_bounded=True,
            min_n_searched=min_n,
            max_n_searched=max_n,
            status="exceeded_max_n",
        )

    # Check if min_n is already sufficient
    w_min = calculate_wilson_width_at_p(eval_p, min_n, confidence_level=confidence_level, z=z_val)
    if w_min <= target_full_width:
        achieved_metric = w_min / 2.0 if is_half_width else w_min
        return SampleSizePlanResult(
            target_metric=metric_name,
            target_threshold=target_width,
            design_proportion=eval_p,
            guarantee_type=guarantee,
            confidence_level=confidence_level,
            z=z_val,
            required_n=min_n,
            achieved_metric_value=achieved_metric,
            search_bounded=True,
            min_n_searched=min_n,
            max_n_searched=max_n,
            status="found",
        )

    # Binary search: invariant is W(eval_p, low) > target and W(eval_p, high) <= target
    best_n = high
    while low <= high:
        mid = (low + high) // 2
        w_mid = calculate_wilson_width_at_p(eval_p, mid, confidence_level=confidence_level, z=z_val)
        if w_mid <= target_full_width:
            best_n = mid
            high = mid - 1  # Try smaller n
        else:
            low = mid + 1  # Need larger n

    achieved_full_w = calculate_wilson_width_at_p(
        eval_p, best_n, confidence_level=confidence_level, z=z_val
    )
    achieved_metric = achieved_full_w / 2.0 if is_half_width else achieved_full_w

    return SampleSizePlanResult(
        target_metric=metric_name,
        target_threshold=target_width,
        design_proportion=eval_p,
        guarantee_type=guarantee,
        confidence_level=confidence_level,
        z=z_val,
        required_n=best_n,
        achieved_metric_value=achieved_metric,
        search_bounded=True,
        min_n_searched=min_n,
        max_n_searched=max_n,
        status="found",
    )
