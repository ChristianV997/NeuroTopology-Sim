"""Render a compiled record dict (see compiler.compile_record) to Markdown
optimized for reading on a phone: the actionable summary comes first, in a
short block with no wide tables, and every table below is kept to a
handful of narrow columns so it doesn't require horizontal scrolling in a
mobile Markdown viewer -- "the project needs a single readable report for
mobile review."
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


def render_markdown(record: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Research Record")
    lines.append("")

    head = record["integration_branch_and_verified_head"]
    lines.append(f"**Recommendation: {record['final_release_recommendation']}**")
    lines.append("")
    lines.append(f"- Repo: {_fmt(record['repository_identity']['repo'])}")
    lines.append(f"- origin/main commit: `{_fmt(record['origin_main_commit'])}`")
    lines.append(f"- Integration ref: {_fmt(head['integration_ref'])}, head `{_fmt(head['commit'])}` (verified: {_fmt(head['verified'])})")
    lines.append(f"- Status: **{record['status']}**")
    lines.append(f"- Engineering status: **{record['engineering_status']['label']}** / Scientific status: **{record['scientific_status']['label']}** / Scientific verdict: **{record['scientific_verdict']}**")
    lines.append(f"- Unresolved blockers: **{len(record['unresolved_blockers'])}**")
    lines.append(f"- Generated: `{record['generated_at']}`")
    lines.append("")
    lines.append(f"> {record['final_conclusions']['scientific_conclusion_caveat']}")
    lines.append("")
    if record["next_actions"]:
        lines.append("**Next actions:**")
        for action in record["next_actions"][:5]:
            lines.append(f"1. {action}")
        if len(record["next_actions"]) > 5:
            lines.append(f"   (+{len(record['next_actions']) - 5} more below)")
    else:
        lines.append("**Next actions:** none.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"_Report schema `{record['report_schema_version']}` · Input contract `{record['input_contract_version']}` · "
        f"Compiler `{record['compiler_version']}` · Checksum `{record['canonical_checksum'][:12]}…`_"
    )
    lines.append("")

    lines.append("## Execution Timestamp and Source Commits")
    lines.append("")
    lines.append(f"- Generated: `{record['generated_at']}`")
    lines.append(f"- Repo: {_fmt(record['repository_identity']['repo'])}")
    lines.append(f"- origin/main commit: `{_fmt(record['origin_main_commit'])}`")
    lines.append(f"- Integration ref: {_fmt(head['integration_ref'])}, head `{_fmt(head['commit'])}` (verified: {_fmt(head['verified'])})")
    lines.append(f"- Integration head verification reason: {head['reason']}")
    lines.append("")

    lines.append("## Repository and Branch State")
    lines.append("")
    lines.append(f"- Status: **{record['status']}**")
    for bucket, prs in record["pr_buckets"].items():
        lines.append(f"- {bucket}: {prs}")
    lines.append("")

    lines.append("## Merged-to-Main Work")
    lines.append("")
    merged = [p for p in record["pr_state"]["pull_requests"] if p["merge_status"] == "merged"]
    lines.append(_table(["PR", "Branch", "Ancestor of target"], [[p["pr_number"], _fmt(p["branch"]), _fmt(p["is_ancestor_of_target"])] for p in merged]))
    lines.append("")

    lines.append("## Integration-Only Work")
    lines.append("")
    integration_only = [p for p in record["pr_state"]["pull_requests"] if p["integration_status"] == "integrated_only"]
    lines.append(_table(["PR", "Branch", "Merge status"], [[p["pr_number"], _fmt(p["branch"]), p["merge_status"]] for p in integration_only]))
    lines.append("")

    lines.append("## Open PRs")
    lines.append("")
    open_prs = [p for p in record["pr_state"]["pull_requests"] if p["merge_status"] == "open" and p["is_draft"] is not True]
    lines.append(_table(["PR", "Branch", "CI"], [[p["pr_number"], _fmt(p["branch"]), p["ci_status"]] for p in open_prs]))
    lines.append("")

    lines.append("## Agent Contribution Table")
    lines.append("")
    lines.append(
        _table(
            ["ID", "Agent", "PR", "Merge status", "Claim class"],
            [
                [c["id"], _fmt(c["agent"]), _fmt(c["pr_number"]), c["merge_status"], c["research_classification"]["claim_class"]]
                for c in record["agent_contribution_table"]["contributions"]
            ],
        )
    )
    lines.append("")

    lines.append("## PR Buckets (open / draft / closed / merged / integrated-only)")
    lines.append("")
    for bucket, prs in record["pr_buckets"].items():
        lines.append(f"- {bucket}: {prs}")
    lines.append("")

    lines.append("## PR State")
    lines.append("")
    lines.append(
        _table(
            ["PR", "Merge status", "Category", "CI"],
            [[p["pr_number"], p["merge_status"], p["status_category"], p["ci_status"]] for p in record["pr_state"]["pull_requests"]],
        )
    )
    lines.append("")

    lines.append("## Branch Ancestry")
    lines.append("")
    lines.append(_table(["PR", "Branch", "Is ancestor of target"], [[b["pr_number"], _fmt(b["branch"]), _fmt(b["is_ancestor_of_target"])] for b in record["branch_ancestry"]]))
    lines.append("")

    lines.append("## Stacked Dependencies")
    lines.append("")
    lines.append(f"- Layers: {record['stacked_dependencies']['layers']}")
    for edge in record["stacked_dependencies"]["edges"]:
        lines.append(f"- PR #{edge['pr_number']} depends on: {edge['depends_on']}")
    lines.append("")

    lines.append("## Duplicate / Superseded Decisions")
    lines.append("")
    lines.append(
        _table(
            ["PR", "Superseded by", "Duplicate of", "Recommended action"],
            [[d["pr_number"], _fmt(d["superseded_by_pr"]), _fmt(d["duplicate_of_pr"]), d["recommended_action"]] for d in record["duplicate_superseded_decisions"]],
        )
    )
    lines.append("")

    lines.append("## Changed-File Ownership")
    lines.append("")
    shared = {path: prs for path, prs in record["changed_file_ownership"].items() if len(prs) > 1}
    if shared:
        for path, prs in shared.items():
            lines.append(f"- {path}: {prs}")
    else:
        lines.append("_no files touched by more than one PR_")
    lines.append("")

    lines.append("## Conflicts")
    lines.append("")
    if record["conflicts"]:
        for c in record["conflicts"]:
            lines.append(f"- **{c['kind']}**: {c['detail']}")
    else:
        lines.append("_none_")
    lines.append("")

    ci = record["ci_status"]
    lines.append("## CI Status")
    lines.append("")
    lines.append(f"- PR CI counts: {ci['pr_ci_status_counts']}")
    lines.append(f"- Job status counts: {ci['test_runner'].get('counts_by_status', {})}")
    lines.append("")

    lines.append("## Billing / Runner Status")
    lines.append("")
    br = record["billing_runner_status"]
    lines.append(f"- Billing-blocked jobs: {br['billing_blocked_jobs']}")
    lines.append(f"- Infrastructure-blocked jobs: {br['infrastructure_blocked_jobs']}")
    lines.append(f"- Billing-blocked PRs: {br['billing_blocked_prs']}")
    lines.append(f"- CI-blocked PRs: {br['ci_blocked_prs']}")
    lines.append("")

    lines.append("## Test Totals")
    lines.append("")
    tt = record["test_totals"]
    lines.append(f"- Passed: {tt['passed']}, Failed: {tt['failed']}, Skipped: {tt['skipped']}")
    lines.append("")

    lines.append("## Failures")
    lines.append("")
    lines.append(f"- Failed jobs: {record['failures']['failed_jobs'] or '_none_'}")
    lines.append(f"- PRs with failed CI: {record['failures']['failed_ci_prs'] or '_none_'}")
    lines.append("")

    lines.append("## Timeouts")
    lines.append("")
    lines.append(f"- Timed-out test jobs: {record['timeouts']['test_jobs'] or '_none_'}")
    lines.append(f"- Timed-out scientific checks: {record['timeouts']['scientific_checks'] or '_none_'}")
    lines.append("")

    lines.append("## Performance Evidence")
    lines.append("")
    lines.append(
        _table(
            ["Name", "Value", "Unit", "Status"],
            [[b["name"], _fmt(b["value"]), _fmt(b["unit"]), b["status"]] for b in record["performance_evidence"]["benchmarks"]],
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
                for b in record["memory_evidence"]["benchmarks"]
            ],
        )
    )
    lines.append("")

    lines.append("## Provenance")
    lines.append("")
    lines.append(
        _table(
            ["Dataset", "Data mode", "Checksum source"],
            [[d["dataset_id"], d["data_mode"], d["checksum_source"]] for d in record["provenance"]["datasets"]],
        )
    )
    lines.append("")

    lines.append("## Cohort Readiness")
    lines.append("")
    lines.append(
        _table(
            ["Cohort", "N subjects", "N required", "Ready"],
            [[c["cohort_id"], _fmt(c["n_subjects"]), _fmt(c["n_required"]), _fmt(c["ready"])] for c in record["cohort_readiness"]["cohorts"]],
        )
    )
    lines.append("")

    lines.append("## Topology Readiness")
    lines.append("")
    lines.append(
        _table(
            ["Check", "Family", "Data mode", "Verdict"],
            [[c["name"], c["metric_family"], c["data_mode"], c["verdict"]] for c in record["topology_readiness"]["checks"]],
        )
    )
    lines.append("")

    lines.append("## Falsification Semantics")
    lines.append("")
    lines.append(
        _table(
            ["Hypothesis", "Claim class", "Metric", "Verdict"],
            [
                [f["hypothesis_id"], f["claim_class"], f["metric_display_label"], f["verdict"]]
                for f in record["falsification_semantics"]["results"]
            ],
        )
    )
    lines.append("")

    lines.append("## Scientific Gate Reports")
    lines.append("")
    lines.append(
        _table(
            ["Gate", "Claim class", "Data mode", "Verdict"],
            [[g["gate_id"], g["claim_class"], g["data_mode"], g["verdict"]] for g in record["scientific_gate_reports"]["gates"]],
        )
    )
    lines.append("")

    lines.append("## Scientific Falsification Status")
    lines.append("")
    lines.append(f"**scientific_verdict: {record['scientific_verdict']}**")
    lines.append("")
    lines.append(
        "_Only items labeled \"formal statistical evidence\" or \"empirical observation\" ever contribute to this "
        "verdict; engineering facts and benchmark results never do._"
    )
    lines.append("")

    lines.append("## Scientific Limitations")
    lines.append("")
    for item in record["scientific_limitations"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Dashboard Isolation")
    lines.append("")
    dash = record["dashboard_isolation"]
    lines.append(f"- ok: {_fmt(dash['ok'])}")
    lines.append(f"- scanned files: {_fmt(dash['scanned_files'])}")
    lines.append(f"- violations: {dash['violations'] or '_none_'}")
    lines.append("")

    lines.append("## Engineering Status vs. Scientific Status")
    lines.append("")
    lines.append(f"- Engineering status: **{record['engineering_status']['label']}**")
    lines.append(f"- Scientific status: **{record['scientific_status']['label']}**")
    lines.append(f"- Scientific verdict: **{record['scientific_verdict']}**")
    lines.append("")

    epi = record["epistemic_classification"]

    lines.append("## Confirmed Engineering Facts")
    lines.append("")
    lines.append(_table(["Source", "ID", "Summary"], [[i["source"], i["id"], i["summary"]] for i in epi["confirmed_engineering_facts"]]))
    lines.append("")

    lines.append("## Benchmark Results")
    lines.append("")
    lines.append(_table(["Source", "ID", "Summary"], [[i["source"], i["id"], i["summary"]] for i in epi["benchmark_results"]]))
    lines.append("")

    lines.append("## Hypotheses")
    lines.append("")
    lines.append(_table(["Source", "ID", "Summary"], [[i["source"], i["id"], i["summary"]] for i in epi["hypotheses"]]))
    lines.append("")

    lines.append("## Speculation")
    lines.append("")
    lines.append(_table(["Source", "ID", "Summary"], [[i["source"], i["id"], i["summary"]] for i in epi["speculation"]]))
    lines.append("")

    lines.append("## Unsupported Claims")
    lines.append("")
    lines.append(_table(["Source", "ID", "Summary"], [[i["source"], i["id"], i["summary"]] for i in epi["unsupported_claims"]]))
    lines.append("")

    lines.append("## Release Manifest")
    lines.append("")
    rm = record["release_manifest"]
    lines.append(f"- schema_version: {_fmt(rm['schema_version'])}, repo: {_fmt(rm['repo'])}, commit: `{_fmt(rm['commit'])}`, branch: {_fmt(rm['branch'])}")
    lines.append("")

    lines.append("## Artifact References")
    lines.append("")
    lines.append(_table(["Label", "Path", "Kind"], [[a["label"], a["path"], _fmt(a["kind"])] for a in record["artifact_references"]["artifacts"]]))
    lines.append("")

    lines.append("## Operator Notes")
    lines.append("")
    lines.append(
        _table(
            ["Note", "Epistemic label"],
            [[n["note"], n["declared_epistemic_label"] or "(unlabeled -> unsupported claim)"] for n in record["operator_notes"]["notes"]],
        )
    )
    lines.append("")

    lines.append("## Unresolved Blockers")
    lines.append("")
    if record["unresolved_blockers"]:
        for b in record["unresolved_blockers"]:
            lines.append(f"- **{b['kind']}**: {b.get('detail', '')}")
    else:
        lines.append("_none_")
    lines.append("")

    lines.append("## Final Conclusions")
    lines.append("")
    lines.append(record["final_conclusions"]["engineering_conclusion"])
    lines.append("")
    lines.append(f"> {record['final_conclusions']['scientific_conclusion_caveat']}")
    lines.append("")

    lines.append("## Next Priorities")
    lines.append("")
    if record["next_priorities"]:
        for i, action in enumerate(record["next_priorities"], start=1):
            lines.append(f"{i}. {action}")
    else:
        lines.append("_none_")
    lines.append("")

    lines.append("## Final Release Recommendation")
    lines.append("")
    lines.append(f"**{record['final_release_recommendation']}**")
    lines.append("")
    lines.append(f"_Canonical checksum: `{record['canonical_checksum']}`_")
    lines.append("")

    return "\n".join(lines) + "\n"
