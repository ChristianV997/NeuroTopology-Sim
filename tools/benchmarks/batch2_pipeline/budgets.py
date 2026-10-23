"""Configurable resource budgets. Missing metrics compare to None, never zero."""
from __future__ import annotations

import math
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


_BUDGET_FIELDS = frozenset(
    {"memory_bytes", "disk_bytes", "runtime_s", "rss_bytes", "max_workers"}
)


def telemetry_metrics_are_valid(metrics: Any) -> bool:
    """Reject malformed resource telemetry, even when its budget is disabled."""
    if not isinstance(metrics, dict):
        return False

    integer_metrics = {
        "tracemalloc_peak_bytes": 1,
        "rss_after_bytes": 1,
        "disk_bytes": 0,
        "worker_count": 1,
    }
    for name, minimum in integer_metrics.items():
        if name not in metrics or metrics[name] is None:
            continue
        value = metrics[name]
        if type(value) is not int or value < minimum:
            return False

    for name in (
        "runtime_best_s",
        "runtime_mean_s",
        "process_work_s",
        "checkpoint_s",
    ):
        if name not in metrics or metrics[name] is None:
            continue
        value = metrics[name]
        if not _finite_nonnegative_number(value):
            return False
    return True


def _finite_nonnegative_number(value: Any) -> bool:
    if type(value) is int:
        return value >= 0
    return type(value) is float and math.isfinite(value) and value >= 0


def _valid_budget_value(name: str, value: Any) -> bool:
    if value is None:
        return True
    if name == "runtime_s":
        return _finite_nonnegative_number(value)
    minimum = 1 if name == "max_workers" else 0
    return type(value) is int and value >= minimum


def budget_result_is_consistent(
    result: Any,
    metrics: Any = None,
    declared_budgets: Any = None,
    execution_worker_cap: Any = None,
) -> bool:
    """Check checks against declared limits, telemetry, and their aggregate.

    A missing measurement under an enabled limit is unknown, not a pass. Runtime
    and RSS remain advisory and are deliberately excluded from this aggregate.
    """
    if not isinstance(result, dict):
        return False
    checks = result.get("checks")
    budgets = result.get("budgets")
    if not isinstance(checks, dict) or not isinstance(budgets, dict):
        return False
    if (
        not isinstance(declared_budgets, dict)
        or set(budgets) != _BUDGET_FIELDS
        or set(declared_budgets) != _BUDGET_FIELDS
        or not telemetry_metrics_are_valid(metrics)
    ):
        return False
    if execution_worker_cap is not None and (
        type(execution_worker_cap) is not int or execution_worker_cap < 1
    ):
        return False

    observed_workers = metrics.get("worker_count")
    if (
        execution_worker_cap is not None
        and observed_workers is not None
        and observed_workers > execution_worker_cap
    ):
        return False

    mapping = (
        ("memory_within_budget", "memory_bytes", "tracemalloc_peak_bytes", True),
        ("disk_within_budget", "disk_bytes", "disk_bytes", True),
        ("workers_within_budget", "max_workers", "worker_count", True),
        ("runtime_within_budget", "runtime_s", "runtime_best_s", False),
        ("rss_within_budget", "rss_bytes", "rss_after_bytes", False),
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
        if not _valid_budget_value(budget_name, row_limit):
            return False
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
        limit = row_limit
        metric = metrics.get(metric_name)
        if limit is None or metric is None:
            expected_check: Optional[bool] = None
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
