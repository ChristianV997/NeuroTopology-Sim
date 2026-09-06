"""Detect a CI check that fails identically across many unrelated work
orders sharing the same base commit -- evidence the failure is
environmental (a broken/misconfigured check, or a base-branch condition
inherited by every PR-triggered workflow) rather than caused by any one
branch's own diff.

This does not prove causation; it only surfaces the pattern with its
supporting counts so a human reviewer does not mistakenly blame an
individual branch for a check that was already failing everywhere.
"""
from __future__ import annotations

from typing import Optional


def detect_common_check_failures(
    checks_by_work_order: dict[str, Optional[dict[str, str]]],
    min_fraction: float = 0.6,
    min_work_orders: int = 3,
) -> list[dict]:
    """``checks_by_work_order``: {work_order_id: {check_name: conclusion}}.
    Returns a list of {"check_name", "failing_in", "total_reporting",
    "fraction"} entries for every check name that fails in at least
    ``min_fraction`` of the work orders that reported any result for that
    check name, provided at least ``min_work_orders`` work orders reported
    it at all (so two coincidentally-matching failures don't get flagged
    as a pattern)."""
    per_check_total: dict[str, int] = {}
    per_check_failing: dict[str, list[str]] = {}

    for work_order_id, checks in checks_by_work_order.items():
        if not checks:
            continue
        for check_name, conclusion in checks.items():
            per_check_total[check_name] = per_check_total.get(check_name, 0) + 1
            if conclusion != "success":
                per_check_failing.setdefault(check_name, []).append(work_order_id)

    findings: list[dict] = []
    for check_name, total in sorted(per_check_total.items()):
        failing = per_check_failing.get(check_name, [])
        if total < min_work_orders:
            continue
        fraction = len(failing) / total
        if fraction >= min_fraction:
            findings.append({
                "check_name": check_name,
                "failing_in": sorted(failing),
                "total_reporting": total,
                "fraction": round(fraction, 3),
            })
    return findings
