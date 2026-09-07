"""Metric-family isolation.

Graph beta-1, spatial winding / topological charge, and scalar chirality
are distinct. This module never converts one into another.
"""

from __future__ import annotations

from .schema import METRIC_FAMILIES


def normalize_metric_family(name: str | None) -> str:
    raw = (name or "other").strip()
    if raw in METRIC_FAMILIES:
        return raw
    aliases = {
        "beta-1": "graph_beta1",
        "beta1": "graph_beta1",
        "graph_beta-1": "graph_beta1",
        "cycle_rank": "graph_beta1",
        "spatial_charge": "spatial_winding_q",
        "spatial_topological_charge": "spatial_winding_q",
        "winding": "spatial_winding_q",
        "chirality": "scalar_chirality",
    }
    return aliases.get(raw, "other")


def mean_statistic(series: list[float]) -> float:
    if not series:
        raise ValueError("cannot compute a mean of an empty series")
    return sum(series) / len(series)


def mean_difference(group_a: list[float], group_b: list[float]) -> float:
    return mean_statistic(group_a) - mean_statistic(group_b)
