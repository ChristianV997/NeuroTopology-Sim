"""Binomial operating-characteristic planning and uncertainty verification package.

This package provides dependency-light, mathematically rigorous tools for:
1. Exact Wilson score confidence intervals for proportions (e.g. FPR and TPR)
   with explicit non-estimate states for n=0.
2. Bounded trial-count planning for target confidence interval widths and
   zero-event upper bounds.
"""

from .planner import (
    SampleSizePlanResult,
    calculate_wilson_width_at_p,
    plan_sample_size,
    plan_zero_event_sample_size,
    zero_event_upper_bound,
)
from .wilson import (
    WilsonIntervalResult,
    get_z_score,
    wilson_score_interval,
)

__all__ = [
    "SampleSizePlanResult",
    "WilsonIntervalResult",
    "calculate_wilson_width_at_p",
    "get_z_score",
    "plan_sample_size",
    "plan_zero_event_sample_size",
    "wilson_score_interval",
    "zero_event_upper_bound",
]
