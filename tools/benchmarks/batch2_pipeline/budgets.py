"""Configurable resource budgets. Missing metrics compare to None, never zero."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ResourceBudgets:
    """Per-target resource budgets. ``None`` disables that check."""

    memory_bytes: Optional[int] = None
    disk_bytes: Optional[int] = None
    runtime_s: Optional[float] = None
    rss_bytes: Optional[int] = None
    max_workers: Optional[int] = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _within(metric: Optional[float], budget: Optional[float]) -> Optional[bool]:
    if budget is None:
        return None
    if metric is None:
        return None
    return metric <= budget


def compare_budget(metrics: Dict[str, Any], budgets: ResourceBudgets) -> Dict[str, Any]:
    """Compare candidate metrics against ``budgets``.

    Missing metric or unset budget → ``None`` (unknown), never a pass-by-omission.
    """
    worker = metrics.get("worker_count")
    worker_ok: Optional[bool]
    if budgets.max_workers is None:
        worker_ok = None
    elif worker is None:
        worker_ok = None
    else:
        worker_ok = int(worker) <= int(budgets.max_workers)

    checks = {
        "memory_within_budget": _within(metrics.get("tracemalloc_peak_bytes"), budgets.memory_bytes),
        "disk_within_budget": _within(metrics.get("disk_bytes"), budgets.disk_bytes),
        "runtime_within_budget": _within(metrics.get("runtime_best_s"), budgets.runtime_s),
        "rss_within_budget": _within(metrics.get("rss_after_bytes"), budgets.rss_bytes),
        "workers_within_budget": worker_ok,
    }
    evaluated = [v for v in checks.values() if v is not None]
    within = all(evaluated) if evaluated else None
    return {
        "within_budget": within,
        "checks": checks,
        "advisory_checks": ["runtime_within_budget", "rss_within_budget"],
        "authoritative_checks": [
            "memory_within_budget",
            "disk_within_budget",
            "workers_within_budget",
        ],
        "budgets": budgets.to_dict(),
    }
