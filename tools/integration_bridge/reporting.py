"""Human-readable rendering of an assembled ecosystem run.

Pure formatting: takes already-computed structures (QualityReport, the
plan, provenance) and renders text. No computation, no I/O beyond the
return value.
"""
from __future__ import annotations

from typing import Any, Dict, List


def render_markdown_summary(
    *,
    run_id: str,
    status: str,
    provenance: Dict[str, Any],
    quality_report: Dict[str, Any],
    plan: Dict[str, Any],
    stage_durations_s: Dict[str, float],
) -> str:
    lines: List[str] = []
    lines.append(f"# Ecosystem run `{run_id}`")
    lines.append("")
    lines.append(f"**Status:** `{status}`")
    lines.append("")
    lines.append("## Provenance")
    for key in sorted(provenance):
        lines.append(f"- `{key}`: {provenance[key]}")
    lines.append("")
    lines.append("## Plan")
    steps = plan.get("steps", [])
    skipped = plan.get("skipped", [])
    lines.append(f"- executed steps: {', '.join(s['name'] for s in steps) or '(none)'}")
    if skipped:
        lines.append("- skipped steps:")
        for step in skipped:
            lines.append(f"  - `{step['name']}`: {step.get('reason_if_skipped', 'unknown reason')}")
    lines.append("")
    lines.append("## Quality gate")
    for key, value in sorted(quality_report.get("checks", {}).items()):
        mark = "PASS" if value else "FAIL"
        lines.append(f"- [{mark}] {key}")
    if quality_report.get("errors"):
        lines.append("")
        lines.append("### Errors")
        for error in quality_report["errors"]:
            lines.append(f"- {error}")
    if quality_report.get("warnings"):
        lines.append("")
        lines.append("### Warnings")
        for warning in quality_report["warnings"]:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append("## Stage durations (s)")
    for stage in sorted(stage_durations_s):
        lines.append(f"- {stage}: {stage_durations_s[stage]:.4f}")
    return "\n".join(lines) + "\n"
