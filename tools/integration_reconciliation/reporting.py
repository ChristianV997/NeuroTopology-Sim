"""Strict JSON and human Markdown rendering of a ReconciliationReport."""
from __future__ import annotations

import json

from .models import STAGES, ReconciliationReport

_STAGE_LABELS = {
    "reported": "reported",
    "branch_present": "branch present",
    "pr_present": "PR present",
    "checks_passing": "checks passing",
    "mergeable": "mergeable",
    "merged": "merged",
}


def to_json(report: ReconciliationReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def _mark(value) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def to_markdown(report: ReconciliationReport) -> str:
    lines: list[str] = []
    lines.append("# Integration Reconciliation Report")
    lines.append("")
    lines.append(f"Base ref: `{report.base_branch}` @ `{report.base_commit or 'unknown'}`")
    lines.append("")
    header = "| Work order | " + " | ".join(_STAGE_LABELS[s] for s in STAGES) + " | Notes |"
    sep = "|---" * (len(STAGES) + 2) + "|"
    lines.append(header)
    lines.append(sep)
    for entry in report.entries:
        row = [entry.work_order.description]
        for stage in STAGES:
            row.append(_mark(entry.stages.get(stage).value if entry.stages.get(stage) else None))
        row.append("; ".join(entry.notes) if entry.notes else "")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    if report.file_overlaps:
        lines.append("## File overlaps")
        for pair, files in sorted(report.file_overlaps.items()):
            lines.append(f"- `{pair}`: {', '.join(files)}")
        lines.append("")
    else:
        lines.append("## File overlaps")
        lines.append("None detected among work orders with known changed-file lists.")
        lines.append("")

    if report.common_check_failures:
        lines.append("## Checks failing across most work orders (likely environmental, not branch-caused)")
        for finding in report.common_check_failures:
            lines.append(
                f"- `{finding['check_name']}`: failing in {len(finding['failing_in'])}/"
                f"{finding['total_reporting']} reporting work orders "
                f"({finding['fraction']*100:.0f}%) — {', '.join(finding['failing_in'])}"
            )
        lines.append("")

    if report.dashboard_isolation is not None:
        lines.append("## Dashboard isolation")
        result = report.dashboard_isolation
        status = "PASS" if result["ok"] else ("UNKNOWN" if result["ok"] is None else "FAIL")
        lines.append(f"Status: **{status}** ({result['evidence']})")
        if result["violations"]:
            for violation in result["violations"]:
                lines.append(f"- {violation}")
        lines.append("")

    if report.artifact_commit_findings:
        lines.append("## Suspected generated artifacts committed")
        for work_order_id, files in sorted(report.artifact_commit_findings.items()):
            lines.append(f"- `{work_order_id}`: {', '.join(files)}")
        lines.append("")

    return "\n".join(lines) + "\n"
