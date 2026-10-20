"""Findings carry rule, severity, and safe context without raw subject labels or paths."""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .schema import SEVERITY_ORDER


def make_finding(
    code: str,
    severity: str,
    detail: str,
    *,
    line: Optional[int] = None,
    task: Optional[str] = None,
    entry_index: Optional[int] = None,
    affected_count: Optional[int] = None,
) -> dict[str, Any]:
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"unknown severity: {severity!r}")
    finding: dict[str, Any] = {"code": code, "severity": severity, "detail": detail}
    # Subject labels and caller paths are deliberately not supported finding fields.
    for key, value in (("line", line), ("task", task), ("entry_index", entry_index),
                       ("affected_count", affected_count)):
        if value is not None:
            finding[key] = value
    return finding


def sort_findings(findings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic order: severity, then code, then location."""
    return sorted(
        findings,
        key=lambda f: (
            SEVERITY_ORDER[f["severity"]],
            f["code"],
            str(f.get("task", "")),
            int(f.get("line", 0) or 0),
            int(f.get("entry_index", 0) or 0),
            int(f.get("affected_count", 0) or 0),
            f["detail"],
        ),
    )
