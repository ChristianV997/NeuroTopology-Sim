"""Render a compiled report dict (see compiler.compile_report) to Markdown."""
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
    lines.append("# Unified Research-State Report")
    lines.append("")
    lines.append(f"- Report schema version: `{report['report_schema_version']}`")
    lines.append(f"- Compiler version: `{report['compiler_version']}`")
    lines.append(f"- Generated at: `{report['generated_at']}`")
    lines.append(f"- Status: **{report['status']}**")
    lines.append(f"- Final release recommendation: **{report['final_release_recommendation']}**")
    lines.append("")

    baseline = report["repository_and_baseline"]
    lines.append("## Repository and Baseline")
    lines.append("")
    lines.append(f"- Repository: {_fmt(baseline['repo'])}")
    lines.append(f"- Base ref: {_fmt(baseline['base_ref'])}")
    lines.append(f"- Base commit: {_fmt(baseline['base_commit'])}")
    lines.append("")

    prs = report["pull_requests"]["pull_requests"]
    lines.append("## Open / Merged / Draft / Blocked PRs")
    lines.append("")
    by_state = report["pull_requests"]["by_state"]
    for state in ("open", "merged", "draft", "closed", "unknown"):
        lines.append(f"- {state}: {by_state.get(state, [])}")
    lines.append("")
    lines.append(
        _table(
            ["PR", "Branch", "Base", "State", "Mergeable", "CI status", "Superseded by"],
            [
                [p["pr_number"], _fmt(p["branch"]), _fmt(p["base_branch"]), p["state"], _fmt(p["mergeable"]), p["ci_status"], _fmt(p["superseded_by_pr"])]
                for p in prs
            ],
        )
    )
    lines.append("")

    graph = report["dependency_and_stacking_graph"]
    lines.append("## Dependency and Stacking Graph")
    lines.append("")
    lines.append(f"- Layers (merge-safe order, ignoring eligibility): {graph['layers']}")
    lines.append(f"- Cycles detected: {graph['cycles'] if graph['cycles'] else 'none'}")
    lines.append("")

    ownership = report["changed_file_ownership"]
    lines.append("## Changed-File Ownership")
    lines.append("")
    lines.append(f"- Files tracked: {len(ownership['by_file'])}")
    lines.append(f"- Overlapping files (owned by multiple PRs): {ownership['overlapping_files'] if ownership['overlapping_files'] else 'none'}")
    lines.append("")

    ci = report["ci_and_infrastructure_status"]
    lines.append("## CI and Infrastructure Status")
    lines.append("")
    lines.append(f"- PR CI status counts: {ci['pr_ci_status_counts']}")
    lines.append(f"- Test-runner job status counts: {ci['test_runner'].get('counts_by_status', {})}")
    lines.append(
        "- Guardrail: jobs with status `not_started` are never counted as passing."
    )
    lines.append("")

    lines.append("## Performance Evidence")
    lines.append("")
    lines.append(
        _table(
            ["Name", "Metric", "Value", "Unit", "Baseline", "Regression %", "Status"],
            [
                [b["name"], _fmt(b["metric"]), _fmt(b["value"]), _fmt(b["unit"]), _fmt(b["baseline_value"]), _fmt(b["regression_pct"]), b["status"]]
                for b in report["performance_evidence"]["benchmarks"]
            ],
        )
    )
    lines.append("")

    lines.append("## Memory Evidence")
    lines.append("")
    lines.append(
        _table(
            ["Name", "Metric", "Value", "Unit", "Baseline", "Regression %", "Status"],
            [
                [b["name"], _fmt(b["metric"]), _fmt(b["value"]), _fmt(b["unit"]), _fmt(b["baseline_value"]), _fmt(b["regression_pct"]), b["status"]]
                for b in report["memory_evidence"]["benchmarks"]
            ],
        )
    )
    lines.append("")

    lines.append("## Interoperability Status")
    lines.append("")
    lines.append(
        _table(
            ["Adapter", "Status", "Contract version"],
            [[a["name"], a["status"], _fmt(a["contract_version"])] for a in report["interoperability_status"]["adapters"]],
        )
    )
    lines.append("")

    lines.append("## Dataset Provenance")
    lines.append("")
    lines.append(
        _table(
            ["Dataset", "Data mode", "Source", "License", "N subjects"],
            [
                [d["dataset_id"], d["data_mode"], _fmt(d["source"]), _fmt(d["license"]), _fmt(d["n_subjects"])]
                for d in report["dataset_provenance"]["datasets"]
            ],
        )
    )
    lines.append("")

    lines.append("## Topology Validation Status")
    lines.append("")
    lines.append(
        _table(
            ["Check", "Data mode", "Qabs", "I_mean", "Verdict"],
            [
                [c["name"], c["data_mode"], _fmt(c["Qabs"]), _fmt(c["I_mean"]), c["verdict"]]
                for c in report["topology_validation_status"]["checks"]
            ],
        )
    )
    lines.append("")

    lines.append("## Falsification Status")
    lines.append("")
    lines.append(
        _table(
            ["Hypothesis", "Data mode", "Metric", "Value", "Unit", "Verdict"],
            [
                [f["hypothesis_id"], f["data_mode"], f["display_label"], _fmt(f["metric_value"]), _fmt(f["unit"]), f["verdict"]]
                for f in report["falsification_status"]["results"]
            ],
        )
    )
    lines.append("")

    sve = report["synthetic_versus_empirical_distinction"]
    lines.append("## Synthetic Versus Empirical Distinction")
    lines.append("")
    lines.append(f"- Datasets — synthetic: {sve['datasets']['synthetic']}, empirical: {sve['datasets']['empirical']}, unknown: {sve['datasets']['unknown']}")
    lines.append(f"- Falsification results — synthetic: {sve['falsification_results']['synthetic']}, empirical: {sve['falsification_results']['empirical']}, unknown: {sve['falsification_results']['unknown']}")
    lines.append(f"- Topology checks — synthetic: {sve['topology_checks']['synthetic']}, empirical: {sve['topology_checks']['empirical']}, unknown: {sve['topology_checks']['unknown']}")
    lines.append(f"- {sve['guardrail']}")
    lines.append("")

    lines.append("## Scientific Limitations")
    lines.append("")
    for item in report["scientific_limitations"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Unresolved Conflicts")
    lines.append("")
    if report["unresolved_conflicts"]:
        for conflict in report["unresolved_conflicts"]:
            lines.append(f"- **{conflict['kind']}**: {conflict['detail']}")
    else:
        lines.append("_none_")
    lines.append("")

    merge_order = report["recommended_merge_order"]
    lines.append("## Recommended Merge Order")
    lines.append("")
    lines.append(f"- Order: {merge_order['order']}")
    if merge_order["excluded"]:
        lines.append("- Excluded:")
        for pr, reason in merge_order["excluded"].items():
            lines.append(f"  - PR #{pr}: {reason}")
    lines.append("")

    lines.append("## Final Release Recommendation")
    lines.append("")
    lines.append(f"**{report['final_release_recommendation']}**")
    lines.append("")

    return "\n".join(lines) + "\n"
