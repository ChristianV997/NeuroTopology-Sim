"""Strict JSON and human Markdown rendering of a StateLockReport."""
from __future__ import annotations

import json

from .models import StateLockReport


def to_json(report: StateLockReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def to_markdown(report: StateLockReport) -> str:
    lines: list[str] = []
    lines.append("# Integration State Lock")
    lines.append("")
    lines.append(f"**Authoritative head:** `{report.authoritative_head.value or 'unknown'}` "
                 f"({report.authoritative_head.source})")
    lines.append(f"**Main tip:** `{report.main_tip.value or 'unknown'}`")
    lines.append(f"**Local worktree tip:** `{report.local_worktree_tip.value or 'unknown'}`")
    lines.append(f"**Merge base (head, main):** `{report.merge_base_head_and_main.value or 'unknown'}`")
    lines.append(f"**Head is ancestor of main:** {report.is_head_ancestor_of_main.value}")
    lines.append(f"**PR:** #{report.pr_number.value} state={report.pr_state.value} "
                 f"draft={report.pr_draft.value} lifecycle={report.pr_lifecycle.value}")
    lines.append(f"**Merged into main (authoritative):** {report.pr_merged.value} "
                 f"({report.pr_merged.source})")
    lines.append("")

    if report.handoff_verifications:
        lines.append("## Handoff commit verification")
        lines.append("| Label | Claimed commit | Classification | Resolved commit |")
        lines.append("|---|---|---|---|")
        for verification in report.handoff_verifications:
            d = verification.to_dict()
            lines.append(f"| {d['label']} | `{d['claimed_commit']}` | **{d['classification']}** | "
                         f"`{d['resolved_commit'] or '-'}` |")
        lines.append("")
        if report.contradictory_handoffs:
            lines.append(f"**Contradictory handoffs detected:** {report.contradiction_detail}")
        else:
            lines.append("No contradictory handoffs detected.")
        lines.append("")

    if report.integrated_pr_history_findings:
        lines.append("## Integrated-PR history verification")
        for finding in report.integrated_pr_history_findings:
            mark = "found" if finding["found_in_integration_branch_history"] else "NOT found"
            lines.append(f"- PR #{finding['pr_number']}: {mark} in integration branch history — {finding['note']}")
        lines.append("")

    if report.check_classifications:
        lines.append("## Check classifications")
        for name, state in sorted(report.check_classifications.items()):
            lines.append(f"- `{name}`: **{state}**")
        lines.append("")

    if report.notes:
        lines.append("## Notes")
        for note in report.notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines) + "\n"
