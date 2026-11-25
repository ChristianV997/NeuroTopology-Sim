"""Strict finite-JSON serialization and a readable Markdown report for
a :class:`~models.PlanAuditResult`."""
from __future__ import annotations

import json
import math
from typing import Any

from .models import PlanAuditResult


class NonFiniteValueError(ValueError):
    """Raised when an audit result contains a NaN/Infinity value that
    would otherwise silently leak into JSON output."""


def _check_finite(obj: Any, path: str = "$") -> None:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise NonFiniteValueError(f"non-finite float at {path}: {obj!r}")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            _check_finite(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            _check_finite(value, f"{path}[{index}]")


def to_finite_json(result: PlanAuditResult, *, indent: int = 2) -> str:
    payload = result.to_dict()
    _check_finite(payload)
    return json.dumps(payload, indent=indent, allow_nan=False, sort_keys=False)


_STATUS_ICON = {"pass": "PASS", "warning": "WARNING", "blocker": "BLOCKER", "missing": "MISSING"}


def to_markdown(result: PlanAuditResult) -> str:
    d = result.to_dict()
    lines: list[str] = []
    lines.append(f"# Research Plan Quality Audit — {d['plan_id'] or '(unlabeled plan)'}")
    lines.append("")
    lines.append(f"**evidence_class:** `{d['evidence_class']}` — a rubric score is never scientific confirmation.")
    lines.append("")
    lines.append(f"## Overall status: `{d['overall_status']}`  (score: {d['overall_score']})")
    lines.append("")
    lines.append("## Criteria")
    lines.append("")
    lines.append("| Dimension | Status | Detail |")
    lines.append("|---|---|---|")
    for c in d["criteria"]:
        lines.append(f"| {c['dimension']} | {_STATUS_ICON[c['status']]} | {c['detail']} |")
    lines.append("")
    if d["missing_fields"]:
        lines.append("## Missing fields")
        for field_name in d["missing_fields"]:
            lines.append(f"- {field_name}")
        lines.append("")
    if d["hard_blockers"]:
        lines.append("## Hard blockers")
        for blocker in d["hard_blockers"]:
            lines.append(f"- {blocker}")
        lines.append("")
    if d["warnings"]:
        lines.append("## Warnings")
        for warning in d["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")
    if d["recommended_revisions"]:
        lines.append("## Recommended revisions")
        for revision in d["recommended_revisions"]:
            lines.append(f"- {revision}")
        lines.append("")
    if d["generated_at"] is not None:
        lines.append(f"_Generated at: {d['generated_at']}_")
        lines.append("")
    return "\n".join(lines)
