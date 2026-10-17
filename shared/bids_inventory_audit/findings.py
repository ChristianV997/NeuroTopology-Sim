"""Finding records. Every problem is reported with a code and a location, never dropped silently."""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .schema import SEVERITY_ORDER


def make_finding(
    code: str,
    severity: str,
    detail: str,
    *,
    line: Optional[int] = None,
    subject: Optional[str] = None,
    task: Optional[str] = None,
    path: Optional[str] = None,
) -> dict[str, Any]:
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"unknown severity: {severity!r}")
    finding: dict[str, Any] = {"code": code, "severity": severity, "detail": detail}
    for key, value in (("line", line), ("subject", subject), ("task", task), ("path", path)):
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
            str(f.get("subject", "")),
            str(f.get("task", "")),
            str(f.get("path", "")),
            int(f.get("line", 0) or 0),
            f["detail"],
        ),
    )
