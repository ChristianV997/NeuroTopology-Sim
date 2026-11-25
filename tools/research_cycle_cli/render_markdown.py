"""Deterministic Markdown report rendering."""
from __future__ import annotations

from typing import Any

_EXIT_LABELS = {0: "CLEAN", 1: "INCOMPLETE", 2: "INVALID", 3: "BLOCKED"}


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
    lines.append("# Research Cycle Inspection Report")
    lines.append("")
    lines.append(f"**{_EXIT_LABELS.get(report['exit_code'], 'UNKNOWN')} (exit {report['exit_code']})**")
    lines.append("")
    lines.append(f"- Generated: `{report['generated_at']}`")
    lines.append(f"- Report checksum: `{report['report_sha256']}`")
    lines.append(f"- Blockers: **{len(report['blockers'])}**")
    lines.append("")
    lines.append("> This report describes ledger/artifact/claim-gate state as read from the supplied sources. It never re-runs, validates, or certifies any scientific claim itself.")
    lines.append("")

    lines.append("## Sources")
    lines.append("")
    s = report["sources"]
    lines.append(f"- ledger_db: available={_fmt(s['ledger_db']['available'])}, path=`{_fmt(s['ledger_db']['path'])}`, error={_fmt(s['ledger_db']['error'])}")
    lines.append(f"- claim_gate_report: available={_fmt(s['claim_gate_report']['available'])}, path=`{_fmt(s['claim_gate_report']['path'])}`, error={_fmt(s['claim_gate_report']['error'])}")
    lines.append(f"- artifact_reports: available={_fmt(s['artifact_reports']['available'])}, read={len(s['artifact_reports']['read'])}, failed={len(s['artifact_reports']['failed'])}")
    lines.append("")

    lines.append("## Cycles")
    lines.append("")
    for key, ids in report["cycles"]["groups"].items():
        lines.append(f"- {key}: {ids}")
    lines.append("")
    lines.append(_table(["cycle_id", "status", "finalized", "parent_cycle_id"], [[c["cycle_id"], c["status"], c["finalized"], c["parent_cycle_id"]] for c in report["cycles"]["records"]]))
    lines.append("")

    lines.append("## Claims")
    lines.append("")
    lines.append(f"Missing provenance: **{len(report['claims']['missing_provenance'])}**")
    lines.append("")
    lines.append(_table(["claim_id", "cycle_id", "reasons"], [[c["claim_id"], c["cycle_id"], "; ".join(c["reasons"])] for c in report["claims"]["missing_provenance"]]))
    lines.append("")

    lines.append("## Hypotheses")
    lines.append("")
    lines.append(f"Without an experiment: **{len(report['hypotheses']['without_experiment'])}**")
    lines.append("")
    lines.append(_table(["hypothesis_id", "cycle_id"], [[h["hypothesis_id"], h["cycle_id"]] for h in report["hypotheses"]["without_experiment"]]))
    lines.append("")

    lines.append("## Artifacts")
    lines.append("")
    lines.append(f"- Runs without artifacts: **{len(report['artifacts']['runs_without_artifacts'])}**")
    lines.append(f"- Orphan artifact reports: **{len(report['artifacts']['orphan_artifact_reports'])}**")
    lines.append(f"- Artifacts without validation: **{len(report['artifacts']['missing_validation'])}**")
    lines.append("")
    lines.append(_table(["run_record_id", "cycle_id"], [[r["run_record_id"], r["cycle_id"]] for r in report["artifacts"]["runs_without_artifacts"]]))
    lines.append("")

    lines.append("## Evidence Class Breakdown")
    lines.append("")
    lines.append("_Synthetic, proxy, descriptive, and formal evidence are always counted separately and never merged into one total._")
    lines.append("")
    lines.append(_table(["evidence_class", "ledger_records", "claim_gate_results"], [[label, report["evidence_class_breakdown"]["ledger_records"].get(label, 0), report["evidence_class_breakdown"]["claim_gate_results"].get(label, 0)] for label in sorted(report["evidence_class_breakdown"]["ledger_records"])]))
    lines.append("")

    lines.append("## Duplicated / Superseded Records")
    lines.append("")
    lines.append(_table(["record_hash", "record_ids"], [[d["record_hash"], d["record_ids"]] for d in report["duplicates_and_superseded"]["duplicate_ledger_records"]]))
    lines.append("")
    lines.append(_table(["superseded_record_id", "superseded_by_record_id", "record_type"], [[s["superseded_record_id"], s["superseded_by_record_id"], s["record_type"]] for s in report["duplicates_and_superseded"]["superseded_ledger_records"]]))
    lines.append("")

    lines.append("## Stale Outputs")
    lines.append("")
    lines.append(_table(["source_path", "run_directory", "stale_paths"], [[s["source_path"], s["run_directory"], s["stale_paths"]] for s in report["stale_outputs"]]))
    lines.append("")

    lines.append("## Blockers")
    lines.append("")
    if report["blockers"]:
        for b in report["blockers"]:
            lines.append(f"- **{b['kind']}** ({b['id']}): {b['detail']}")
    else:
        lines.append("_none_")
    lines.append("")

    lines.append("## Diagnostics")
    lines.append("")
    if report["diagnostics"]:
        lines.append(_table(["kind", "source", "detail"], [[d["kind"], d["source"], d["detail"]] for d in report["diagnostics"]]))
    else:
        lines.append("_none_")
    lines.append("")

    return "\n".join(lines) + "\n"
