"""Runs every criterion check over a :class:`~models.ResearchPlan` and
assembles the overall :class:`~models.PlanAuditResult`.

Deterministic and side-effect-free: the same ``ResearchPlan`` always
produces byte-identical output (modulo ``generated_at``, which is only
populated when explicitly requested). A high overall score/status here
is never a stand-in for scientific confirmation -- see
``evidence_class = "research_plan_audit"`` on every result.
"""
from __future__ import annotations

from typing import Optional

from .checks import CHECKS_BY_DIMENSION
from .models import PlanAuditResult, ResearchPlan, RUBRIC_DIMENSIONS

assert set(CHECKS_BY_DIMENSION) == set(RUBRIC_DIMENSIONS)

_HARD_STATUSES = frozenset({"blocker", "missing"})


def evaluate_plan(
    plan: ResearchPlan, *, include_generated_at: bool = False, generated_at_value: Optional[str] = None
) -> PlanAuditResult:
    criteria = tuple(CHECKS_BY_DIMENSION[dimension](plan) for dimension in RUBRIC_DIMENSIONS)

    missing_fields = tuple(c.dimension for c in criteria if c.status == "missing")
    hard_blockers = tuple(f"{c.dimension}: {c.detail}" for c in criteria if c.status in _HARD_STATUSES)
    warnings = tuple(f"{c.dimension}: {c.detail}" for c in criteria if c.status == "warning")
    recommended_revisions = hard_blockers + warnings

    if hard_blockers:
        overall_status = "BLOCKED"
    elif warnings:
        overall_status = "NEEDS_REVISION"
    else:
        overall_status = "READY_FOR_EXECUTION"

    overall_score = round(sum(c.score for c in criteria) / len(criteria), 4)

    return PlanAuditResult(
        plan_id=plan.plan_id,
        criteria=criteria,
        missing_fields=missing_fields,
        hard_blockers=hard_blockers,
        warnings=warnings,
        recommended_revisions=recommended_revisions,
        overall_status=overall_status,
        overall_score=overall_score,
        generated_at=generated_at_value if include_generated_at else None,
    )
