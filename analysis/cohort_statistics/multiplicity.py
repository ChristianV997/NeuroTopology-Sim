"""Multiple testing corrections for paired-cohort statistical testing."""
from __future__ import annotations

from typing import Mapping
from .models import MultiplicityMethod


def adjust_p_values(
    p_values: Mapping[str, float | None],
    method: str | MultiplicityMethod = MultiplicityMethod.HOLM,
) -> dict[str, float | None]:
    """Applies multiple comparison correction across family of tested metrics.

    Preserves exact nulls for uncomputed or invalid tests. Supported methods:
    - holm (Holm-Bonferroni step-down)
    - bonferroni (Single-step Bonferroni)
    - fdr_bh (Benjamini-Hochberg False Discovery Rate)
    - none (Unadjusted raw p-values)
    """
    method_str = method.value if isinstance(method, MultiplicityMethod) else str(method).lower()
    adjusted: dict[str, float | None] = {k: None for k in p_values}

    # Extract valid, finite p-values in deterministic key order
    valid_items = [(k, float(v)) for k, v in sorted(p_values.items()) if v is not None]
    m = len(valid_items)

    if m == 0:
        return adjusted

    if method_str == MultiplicityMethod.NONE.value or method_str == "none":
        for k, v in valid_items:
            adjusted[k] = min(1.0, max(0.0, v))
        return adjusted

    if method_str == MultiplicityMethod.BONFERRONI.value or method_str == "bonferroni":
        for k, v in valid_items:
            adjusted[k] = min(1.0, max(0.0, v * m))
        return adjusted

    if method_str == MultiplicityMethod.HOLM.value or method_str == "holm":
        # Sort by p-value ascending, tie-breaking by key name for determinism
        sorted_by_p = sorted(valid_items, key=lambda item: (item[1], item[0]))
        running_max = 0.0
        for i, (k, p) in enumerate(sorted_by_p):
            rank = i + 1
            cand = (m - rank + 1) * p
            running_max = max(running_max, cand)
            adjusted[k] = min(1.0, max(0.0, running_max))
        return adjusted

    if method_str == MultiplicityMethod.FDR_BH.value or method_str == "fdr_bh":
        # Sort by p-value ascending
        sorted_by_p = sorted(valid_items, key=lambda item: (item[1], item[0]))
        # Step-up adjustment from highest to lowest rank
        adj_values = [0.0] * m
        running_min = 1.0
        for i in range(m - 1, -1, -1):
            k, p = sorted_by_p[i]
            rank = i + 1
            cand = (p * m) / rank
            running_min = min(running_min, cand)
            adj_values[i] = min(1.0, max(0.0, running_min))

        for (k, _), adj_p in zip(sorted_by_p, adj_values):
            adjusted[k] = adj_p
        return adjusted

    raise ValueError(f"Unsupported multiplicity correction method: {method_str}")
