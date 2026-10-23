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
    # Wall-clock / RSS are host-dependent advisory signals only. They must not
    # drive within_budget or TargetStatus.BUDGET_OVERRUN (brittle CI gates).
    advisory_checks = ("runtime_within_budget", "rss_within_budget")
    authoritative_checks = (
        "memory_within_budget",
        "disk_within_budget",
        "workers_within_budget",
    )
    configured_checks = [
        ("memory_within_budget", budgets.memory_bytes),
        ("disk_within_budget", budgets.disk_bytes),
        ("workers_within_budget", budgets.max_workers),
    ]
    evaluated = [checks[name] for name, limit in configured_checks if limit is not None]
    if any(value is False for value in evaluated):
        within = False
    elif any(value is None for value in evaluated):
        # A configured authoritative limit with no measurement is unknown. Do
        # not let another passing metric turn the incomplete check into success.
        within = None
    elif evaluated:
        within = True
    else:
        within = None
    return {
        "within_budget": within,
        "checks": checks,
        "advisory_checks": list(advisory_checks),
        "authoritative_checks": list(authoritative_checks),
        "budgets": budgets.to_dict(),
    }


def budget_result_is_consistent(
    result: Any,
    metrics: Any = None,
    declared_budgets: Any = None,
) -> bool:
    """Check checks against declared limits, telemetry, and their aggregate.

    A missing measurement under an enabled limit is unknown, not a pass. Runtime
    and RSS remain advisory and are deliberately excluded from this aggregate.
    """
    if not isinstance(result, dict):
        return False
    checks = result.get("checks")
    budgets = result.get("budgets")
    if (
        not isinstance(checks, dict)
        or not isinstance(budgets, dict)
        or not isinstance(declared_budgets, dict)
    ):
        return False

    mapping = (
        ("memory_within_budget", "memory_bytes", "tracemalloc_peak_bytes", True),
        ("disk_within_budget", "disk_bytes", "disk_bytes", True),
        ("workers_within_budget", "max_workers", "worker_count", True),
        ("runtime_within_budget", "runtime_s", None, False),
        ("rss_within_budget", "rss_bytes", None, False),
    )
    for check_name, budget_name, metric_name, is_authoritative in mapping:
        if (
            check_name not in checks
            or budget_name not in budgets
            or budget_name not in declared_budgets
        ):
            return False
        row_limit = budgets[budget_name]
        declared_limit = declared_budgets[budget_name]
        if row_limit is None or declared_limit is None:
            if row_limit is not declared_limit:
                return False
        elif type(row_limit) is not type(declared_limit) or row_limit != declared_limit:
            return False
        check = checks[check_name]
        if check is not True and check is not False and check is not None:
            return False
        if row_limit is None and check is not None:
            return False
        if is_authoritative:
            limit = row_limit
            metric = metrics.get(metric_name) if isinstance(metrics, dict) else None
            if limit is None or metric is None:
                expected_check: Optional[bool] = None
            elif (
                type(limit) is not int
                or limit < 0
                or type(metric) is not int
                or metric < 0
            ):
                return False
            else:
                expected_check = metric <= limit
            if check is not expected_check:
                return False

    authoritative = [
        checks[check_name]
        for check_name, budget_name, _metric_name, is_authoritative in mapping
        if is_authoritative and budgets[budget_name] is not None
    ]
    if any(value is False for value in authoritative):
        expected: Optional[bool] = False
    elif any(value is None for value in authoritative):
        expected = None
    elif authoritative:
        expected = True
    else:
        expected = None
    return result.get("within_budget") is expected
