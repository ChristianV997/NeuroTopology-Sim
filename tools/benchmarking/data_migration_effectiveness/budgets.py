"""Resource budgets. Missing metrics compare as unknown, never zero."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ResourceBudgets:
    memory_bytes: Optional[int] = None
    disk_bytes: Optional[int] = None
    runtime_s: Optional[float] = None
    rss_bytes: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _within(metric: Optional[float], budget: Optional[float]) -> Optional[bool]:
    if budget is None or metric is None:
        return None
    return metric <= budget


def compare_budget(metrics: Dict[str, Any], budgets: ResourceBudgets) -> Dict[str, Any]:
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
