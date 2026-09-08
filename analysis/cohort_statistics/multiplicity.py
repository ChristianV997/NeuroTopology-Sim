"""Multiple hypothesis testing corrections for cohort metric comparisons.

Supports:
- Holm-Bonferroni step-down (Family-Wise Error Rate)
- Bonferroni single-step (FWER)
- Benjamini-Hochberg step-up (False Discovery Rate)
- Explicit multiplicity_unavailable handling when method is absent
- Graceful preservation of None/unavailable test results.
"""
from __future__ import annotations

from typing import Sequence

from .models import MultiplicityMethod


def resolve_multiplicity(
    p_values: Sequence[float | None],
    method: MultiplicityMethod | str | None = MultiplicityMethod.HOLM,
) -> tuple[list[float | None], str]:
    """Adjust p-values and return a tuple of (adjusted_p_values, multiplicity_status).

    If method is absent, None, or 'multiplicity_unavailable', returns explicit
    status 'multiplicity_unavailable' and all adjusted p-values as None.
    """
    if method is None or (isinstance(method, str) and method.lower() in ("absent", "unavailable", "multiplicity_unavailable")):
        return [None] * len(p_values), "multiplicity_unavailable"

    if isinstance(method, str):
        try:
            method = MultiplicityMethod(method.lower())
        except ValueError:
            return [None] * len(p_values), "multiplicity_unavailable"

    if method == MultiplicityMethod.UNAVAILABLE:
        return [None] * len(p_values), "multiplicity_unavailable"

    if method == MultiplicityMethod.NONE:
        return [p if p is not None else None for p in p_values], "none"

    adjusted = adjust_p_values(p_values, method=method)
    return adjusted, "corrected"


def adjust_p_values(
    p_values: Sequence[float | None],
    method: MultiplicityMethod | str | None = MultiplicityMethod.HOLM,
) -> list[float | None]:
    """Adjust a collection of p-values for multiple comparisons.

    Non-testable / unavailable p-values (None) are excluded from the comparison
    count m and preserved as None at their original positions.
    If method is absent or unavailable, returns all None to avoid treating multiple tests as single.
    """
    if method is None or (isinstance(method, str) and method.lower() in ("absent", "unavailable", "multiplicity_unavailable")):
        return [None] * len(p_values)

    if isinstance(method, str):
        try:
            method = MultiplicityMethod(method.lower())
        except ValueError:
            return [None] * len(p_values)

    if method == MultiplicityMethod.UNAVAILABLE:
        return [None] * len(p_values)

    if method == MultiplicityMethod.NONE:
        return [p if p is not None else None for p in p_values]

    # Filter valid p-values while preserving original indices
    valid_indices: list[int] = []
    valid_p: list[float] = []
    for idx, p in enumerate(p_values):
        if p is not None and 0.0 <= p <= 1.0:
            valid_indices.append(idx)
            valid_p.append(float(p))

    m = len(valid_p)
    out: list[float | None] = [None] * len(p_values)

    if m == 0:
        return out
    if m == 1:
        out[valid_indices[0]] = valid_p[0]
        return out

    if method == MultiplicityMethod.BONFERRONI:
        for orig_idx, p in zip(valid_indices, valid_p):
            out[orig_idx] = min(1.0, p * m)
        return out

    # Order valid p-values ascending: (p_val, original_valid_index)
    sorted_pairs = sorted(enumerate(valid_p), key=lambda item: item[1])
    ranked_indices = [item[0] for item in sorted_pairs]
    sorted_p = [item[1] for item in sorted_pairs]

    adjusted_sorted = [0.0] * m

    if method == MultiplicityMethod.HOLM:
        # Step-down: p_(k) * (m - k + 1), enforce non-decreasing
        cum_max = 0.0
        for k, p in enumerate(sorted_p):
            multiplier = m - k
            adj = min(1.0, p * multiplier)
            cum_max = max(cum_max, adj)
            adjusted_sorted[k] = cum_max

    elif method == MultiplicityMethod.FDR_BH:
        # Step-up: p_(k) * m / (k + 1), enforce non-increasing backwards
        cum_min = 1.0
        temp_adj = [min(1.0, p * m / (k + 1)) for k, p in enumerate(sorted_p)]
        for k in range(m - 1, -1, -1):
            cum_min = min(cum_min, temp_adj[k])
            adjusted_sorted[k] = cum_min

    # Map back to original list positions
    for rank_idx, adj_p in zip(ranked_indices, adjusted_sorted):
        orig_pos = valid_indices[rank_idx]
        out[orig_pos] = float(adj_p)

    return out
