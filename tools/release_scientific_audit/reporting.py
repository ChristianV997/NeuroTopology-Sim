"""Strict JSON and human Markdown rendering of an AuditReport."""
from __future__ import annotations

import json

from .models import AuditReport


def to_json(report: AuditReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def to_markdown(report: AuditReport) -> str:
    lines: list[str] = []
    lines.append("# Scientific Release Audit")
    lines.append("")
    lines.append(f"**Release decision:** `{report.release_decision}`")
    lines.append(f"**Reason codes:** {', '.join(report.decision_reason_codes) or '(none)'}")
    lines.append("")

    by_severity: dict[str, list] = {"blocking": [], "warning": [], "info": []}
    for finding in report.findings:
        by_severity.setdefault(finding.severity, []).append(finding)

    for severity in ("blocking", "warning", "info"):
        entries = by_severity.get(severity, [])
        if not entries:
            continue
        lines.append(f"## {severity.capitalize()} findings ({len(entries)})")
        for finding in entries:
            tag = " [insufficient data]" if finding.insufficient_data else ""
            lines.append(f"- **[{finding.check}]**{tag} {finding.summary} — _{finding.evidence_source}_")
            if finding.detail:
                lines.append(f"  - detail: {finding.detail}")
        lines.append("")

    return "\n".join(lines) + "\n"
