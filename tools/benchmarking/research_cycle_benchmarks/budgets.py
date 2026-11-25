"""Configurable resource budgets and comparison logic.

Budgets are opt-in and configurable (no fragile hardcoded thresholds). Missing
metrics compare to ``None`` (unknown), never to a pass-by-omission. Runtime and
RSS are hardware-dependent and flagged advisory; tracemalloc peak and disk usage
are the primary, more comparable signals.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ResourceBudgets:
    """Per-target resource budgets. ``None`` disables that check."""
    memory_bytes: Optional[int] = None       # tracemalloc peak budget (comparable)
    disk_bytes: Optional[int] = None          # export/disk footprint budget (comparable)
    runtime_s: Optional[float] = None         # advisory (hardware dependent)
    rss_bytes: Optional[int] = None           # advisory (hardware/allocator dependent)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _within(metric: Optional[float], budget: Optional[float]) -> Optional[bool]:
    if budget is None:
        return None                 # no budget configured -> not evaluated
    if metric is None:
        return None                 # unknown metric -> unknown (never a pass)
    return metric <= budget


def compare_budget(metrics: Dict[str, Any], budgets: ResourceBudgets) -> Dict[str, Any]:
    """Compare a candidate's metrics against ``budgets``.

    Returns per-metric verdicts (``True``/``False``/``None``), an overall
    ``within_budget`` (None when nothing evaluable), and which checks are advisory.
    """
    checks = {
        "memory_within_budget": _within(metrics.get("tracemalloc_peak_bytes"), budgets.memory_bytes),
        "disk_within_budget": _within(metrics.get("disk_bytes"), budgets.disk_bytes),
        "runtime_within_budget": _within(metrics.get("runtime_best_s"), budgets.runtime_s),
        "rss_within_budget": _within(metrics.get("rss_after_bytes"), budgets.rss_bytes),
    }
    evaluated = [v for v in checks.values() if v is not None]
    within = all(evaluated) if evaluated else None
    return {
        "within_budget": within,
        "checks": checks,
        "advisory_checks": ["runtime_within_budget", "rss_within_budget"],
        "authoritative_checks": ["memory_within_budget", "disk_within_budget"],
        "budgets": budgets.to_dict(),
    }
