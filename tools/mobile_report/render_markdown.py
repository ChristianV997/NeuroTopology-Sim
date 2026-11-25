"""Render a compiled report dict (see compiler.compile_report) to Markdown
optimized for reading on a phone: the actionable summary comes first, in a
short block with no wide tables, and every table below is kept to a handful
of narrow columns so it doesn't require horizontal scrolling in a mobile
Markdown viewer.
"""
from __future__ import annotations

from typing import Any


def _fmt(value: Any) -> str:
    if value is None:
        return "_null_"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_none_\n"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(v) for v in row) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Mobile Research-State Report")
    lines.append("")

    # --- Mobile summary: everything a reviewer needs before scrolling. ---
    baseline = report["repository_and_integration_commit"]
    lines.append(f"**Recommendation: {report['final_release_recommendation']}**")
    lines.append("")
    lines.append(f"- Repo: {_fmt(baseline['repo'])}")
    lines.append(f"- Integration ref: {_fmt(baseline['integration_ref'])}")
    lines.append(f"- Integration commit: `{_fmt(baseline['integration_commit'])}`")
    lines.append(f"- Status: **{report['status']}**")
    lines.append(f"- Unresolved blockers: **{len(report['unresolved_blockers'])}**")
    lines.append(f"- Generated: `{report['generated_at']}`")
    lines.append("")
    if report["exact_next_actions"]:
        lines.append("**Next actions:**")
        for action in report["exact_next_actions"][:5]:
            lines.append(f"1. {action}")
        if len(report["exact_next_actions"]) > 5:
            lines.append(f"   (+{len(report['exact_next_actions']) - 5} more below)")
    else:
        lines.append("**Next actions:** none.")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append(f"_Report schema `{report['report_schema_version']}` · Compiler `{report['compiler_version']}`_")
    lines.append("")

    lines.append("## Agent Contribution Table")
    lines.append("")
    lines.append(
        _table(
            ["ID", "Agent", "PR", "Merge status", "Claim class"],
            [
                [c["id"], _fmt(c["agent"]), _fmt(c["pr_number"]), c["merge_status"], c["research_classification"]["claim_class"]]
                for c in report["agent_contribution_table"]["contributions"]
            ],
        )
    )
    lines.append("")

    lines.append("## PR State / Merge Status")
    lines.append("")
    for status, prs in report["merge_status_by_category"].items():
        if prs:
            lines.append(f"- {status}: {prs}")
    lines.append("")
    lines.append(
        _table(
            ["PR", "Merge status", "Category", "CI"],
            [[p["pr_number"], p["merge_status"], p["status_category"], p["ci_status"]] for p in report["pr_state"]["pull_requests"]],
        )
    )
    lines.append("")

    lines.append("## Stacked Relationships")
    lines.append("")
    lines.append(f"- Layers: {report['stacked_relationships']['layers']}")
    for edge in report["stacked_relationships"]["edges"]:
        lines.append(f"- PR #{edge['pr_number']} depends on: {edge['depends_on']}")
    lines.append("")

    lines.append("## Superseded Work")
    lines.append("")
    if report["superseded_work"]:
        for item in report["superseded_work"]:
            lines.append(f"- PR #{item['pr_number']} superseded by PR #{item['superseded_by_pr']}")
    else:
        lines.append("_none_")
    lines.append("")

    lines.append("## Conflicts")
    lines.append("")
    if report["conflicts"]:
        for c in report["conflicts"]:
            lines.append(f"- **{c['kind']}**: {c['detail']}")
    else:
        lines.append("_none_")
    lines.append("")

    ci = report["ci_status"]
    lines.append("## CI Status")
    lines.append("")
    lines.append(f"- PR CI counts: {ci['pr_ci_status_counts']}")
    lines.append(f"- Job status counts: {ci['test_runner'].get('counts_by_status', {})}")
    lines.append("")

    lines.append("## Billing / Infrastructure Status")
    lines.append("")
    bi = report["billing_infrastructure_status"]
    lines.append(f"- CI-blocked PRs: {bi['ci_blocked_prs']}")
    lines.append(f"- Billing-blocked PRs: {bi['billing_blocked_prs']}")
    lines.append(f"- Billing-blocked jobs: {bi['billing_blocked_jobs']}")
    lines.append(f"- Infrastructure-blocked jobs: {bi['infrastructure_blocked_jobs']}")
    lines.append(f"- Dashboard isolation ok: {_fmt(bi['dashboard_isolation_ok'])}")
    lines.append("")

    lines.append("## Test Totals")
    lines.append("")
    tt = report["test_totals"]
    lines.append(f"- Passed: {tt['passed']}, Failed: {tt['failed']}, Skipped: {tt['skipped']}")
    lines.append("")

    lines.append("## Timeouts")
    lines.append("")
    lines.append(f"- Timed-out test jobs: {report['timeouts']['test_jobs'] or '_none_'}")
    lines.append("")

    lines.append("## Performance Evidence")
    lines.append("")
    lines.append(
        _table(
            ["Name", "Value", "Unit", "Status"],
            [[b["name"], _fmt(b["value"]), _fmt(b["unit"]), b["status"]] for b in report["performance_evidence"]["benchmarks"]],
        )
    )
    lines.append("")

    lines.append("## Memory Evidence")
    lines.append("")
    lines.append(
        _table(
            ["Name", "Value", "Kind", "Verified"],
            [
                [b["name"], _fmt(b["value"]), b.get("kind", "unavailable"), _fmt(b.get("independently_verified"))]
                for b in report["memory_evidence"]["benchmarks"]
            ],
        )
    )
    lines.append("")

    lines.append("## Provenance Status")
    lines.append("")
    lines.append(
        _table(
            ["Dataset", "Data mode", "Checksum source"],
            [[d["dataset_id"], d["data_mode"], d["checksum_source"]] for d in report["provenance_status"]["datasets"]],
        )
    )
    lines.append("")

    lines.append("## Topology Validation Status")
    lines.append("")
    lines.append(
        _table(
            ["Check", "Family", "Data mode", "Verdict"],
            [[c["name"], c["metric_family"], c["data_mode"], c["verdict"]] for c in report["topology_validation_status"]["checks"]],
        )
    )
    lines.append("")

    lines.append("## Falsification Status")
    lines.append("")
    lines.append(
        _table(
            ["Hypothesis", "Claim class", "Metric", "Verdict"],
            [
                [f["hypothesis_id"], f["claim_class"], f["metric_display_label"], f["verdict"]]
                for f in report["falsification_status"]["results"]
            ],
        )
    )
    lines.append("")

    lines.append("## Scientific Limitations")
    lines.append("")
    for item in report["scientific_limitations"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Dashboard Isolation")
    lines.append("")
    dash = report["dashboard_isolation"]
    lines.append(f"- ok: {_fmt(dash['ok'])}")
    lines.append(f"- scanned files: {_fmt(dash['scanned_files'])}")
    lines.append(f"- violations: {dash['violations'] or '_none_'}")
    lines.append("")

    lines.append("## Unresolved Blockers")
    lines.append("")
    if report["unresolved_blockers"]:
        for b in report["unresolved_blockers"]:
            lines.append(f"- **{b['kind']}**: {b['detail']}")
    else:
        lines.append("_none_")
    lines.append("")

    lines.append("## Exact Next Actions")
    lines.append("")
    if report["exact_next_actions"]:
        for i, action in enumerate(report["exact_next_actions"], start=1):
            lines.append(f"{i}. {action}")
    else:
        lines.append("_none_")
    lines.append("")

    lines.append("## Final Release Recommendation")
    lines.append("")
    lines.append(f"**{report['final_release_recommendation']}**")
    lines.append("")

    return "\n".join(lines) + "\n"
