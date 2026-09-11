"""Deterministic terminal summary rendering."""
from __future__ import annotations

from typing import Any

_EXIT_LABELS = {0: "CLEAN", 1: "INCOMPLETE", 2: "INVALID", 3: "BLOCKED"}


def render_summary_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"research-cycle inspection -- {_EXIT_LABELS.get(report['exit_code'], 'UNKNOWN')} (exit {report['exit_code']})")
    lines.append(f"generated_at={report['generated_at']}")
    lines.append("")

    sources = report["sources"]
    lines.append("sources:")
    lines.append(f"  ledger_db: available={sources['ledger_db']['available']} path={sources['ledger_db']['path']} error={sources['ledger_db']['error']}")
    lines.append(f"  claim_gate_report: available={sources['claim_gate_report']['available']} path={sources['claim_gate_report']['path']} error={sources['claim_gate_report']['error']}")
    lines.append(f"  artifact_reports: available={sources['artifact_reports']['available']} read={len(sources['artifact_reports']['read'])} failed={len(sources['artifact_reports']['failed'])}")
    lines.append("")

    groups = report["cycles"]["groups"]
    lines.append("cycles:")
    for key in ("frozen", "active", "blocked", "failed", "incomplete", "other"):
        lines.append(f"  {key}: {groups.get(key, [])}")
    lines.append("")

    lines.append(f"claims missing provenance: {len(report['claims']['missing_provenance'])}")
    lines.append(f"hypotheses without an experiment: {len(report['hypotheses']['without_experiment'])}")
    lines.append(f"runs without artifacts: {len(report['artifacts']['runs_without_artifacts'])}")
    lines.append(f"orphan artifact reports: {len(report['artifacts']['orphan_artifact_reports'])}")
    lines.append(f"artifacts without validation: {len(report['artifacts']['missing_validation'])}")
    lines.append(f"stale outputs: {len(report['stale_outputs'])}")
    lines.append(f"duplicate ledger records: {len(report['duplicates_and_superseded']['duplicate_ledger_records'])}")
    lines.append(f"superseded ledger records: {len(report['duplicates_and_superseded']['superseded_ledger_records'])}")
    lines.append("")

    lines.append("evidence class breakdown (ledger records):")
    for label, count in sorted(report["evidence_class_breakdown"]["ledger_records"].items()):
        if count:
            lines.append(f"  {label}: {count}")
    lines.append("")

    lines.append(f"blockers: {len(report['blockers'])}")
    for blocker in report["blockers"][:20]:
        lines.append(f"  - [{blocker['kind']}] {blocker['id']}: {blocker['detail']}")
    if len(report["blockers"]) > 20:
        lines.append(f"  ... and {len(report['blockers']) - 20} more (see --format json or --format markdown for the full list)")
    lines.append("")
    lines.append(f"report_sha256={report['report_sha256']}")

    return "\n".join(lines) + "\n"
