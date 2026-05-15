"""
Report generation for the local agent research loop (P23).

Writes loop state, next-action summary, and human-readable report.
stdlib only.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ResearchLoopReport:
    loop_version: str
    dry_run: bool
    steps_total: int
    steps_completed: int
    steps_failed: int
    steps_blocked: int
    next_action: str
    next_command: str
    warnings: list = field(default_factory=list)
    guardrails: dict = field(default_factory=dict)
    step_summaries: list = field(default_factory=list)


_GUARDRAILS = {
    "executes_real_data": False,
    "downloads_data": False,
    "auto_confirms_peer_review": False,
    "auto_runs_mne_extraction": False,
    "auto_runs_level_m_extraction": False,
    "auto_runs_level_t_extraction": False,
    "auto_runs_real_benchmark": False,
    "auto_declares_label_mapping": False,
    "infers_labels": False,
    "fabricates_targets": False,
    "weakens_p18_3_gate": False,
    "weakens_p20_operator": False,
    "weakens_p21_iteration": False,
    "weakens_ontology_quarantine": False,
    "weakens_language_firewall": False,
    "auto_pushes_git": False,
    "auto_merges_pr": False,
    "auto_closes_pr": False,
}


def build_loop_report(
    loop_version: str,
    dry_run: bool,
    step_results: list,
    next_action: str,
    next_command: str,
    warnings: Optional[list] = None,
) -> ResearchLoopReport:
    """Build a ResearchLoopReport from step results."""
    completed = sum(1 for r in step_results if getattr(r, "exit_code", None) == 0 or getattr(r, "allowed", False))
    failed = sum(1 for r in step_results if getattr(r, "exit_code", None) not in (None, 0) and getattr(r, "allowed", True))
    blocked = sum(1 for r in step_results if not getattr(r, "allowed", True))
    summaries = [
        {
            "command": getattr(r, "command", ""),
            "allowed": getattr(r, "allowed", True),
            "exit_code": getattr(r, "exit_code", None),
            "blocked_reason": getattr(r, "blocked_reason", ""),
            "elapsed_s": getattr(r, "elapsed_s", 0.0),
        }
        for r in step_results
    ]
    return ResearchLoopReport(
        loop_version=loop_version,
        dry_run=dry_run,
        steps_total=len(step_results),
        steps_completed=completed,
        steps_failed=failed,
        steps_blocked=blocked,
        next_action=next_action,
        next_command=next_command,
        warnings=list(warnings or []),
        guardrails=dict(_GUARDRAILS),
        step_summaries=summaries,
    )


def write_loop_report(report: ResearchLoopReport, out_dir: str | Path) -> list[str]:
    """Write loop report files to out_dir. Returns list of written paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    state = {
        "loop_version": report.loop_version,
        "dry_run": report.dry_run,
        "status": "complete" if report.steps_failed == 0 else "failed",
        "steps_total": report.steps_total,
        "steps_completed": report.steps_completed,
        "steps_failed": report.steps_failed,
        "steps_blocked": report.steps_blocked,
    }
    _write(out / "loop_state.json", state, written)

    next_action_doc = {
        "next_action": report.next_action,
        "next_command": report.next_command,
        "warnings": report.warnings,
    }
    _write(out / "loop_next_action.json", next_action_doc, written)

    guardrails_doc = dict(report.guardrails)
    _write(out / "loop_guardrails.json", guardrails_doc, written)

    results_doc = report.step_summaries
    _write(out / "loop_step_results.json", results_doc, written)

    md = _build_markdown(report)
    md_path = out / "loop_report.md"
    md_path.write_text(md, encoding="utf-8")
    written.append(str(md_path))

    return written


def _write(path: Path, data: Any, written: list) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    written.append(str(path))


def _build_markdown(report: ResearchLoopReport) -> str:
    lines = [
        "# Local Agent Research Loop Report",
        "",
        f"- loop_version: `{report.loop_version}`",
        f"- dry_run: `{report.dry_run}`",
        f"- steps_total: `{report.steps_total}`",
        f"- steps_completed: `{report.steps_completed}`",
        f"- steps_failed: `{report.steps_failed}`",
        f"- steps_blocked: `{report.steps_blocked}`",
        "",
        "## Next Action",
        "",
        f"- next_action: `{report.next_action}`",
        f"- next_command: `{report.next_command}`",
        "",
    ]
    if report.warnings:
        lines += ["## Warnings", ""]
        for w in report.warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines += [
        "## Guardrails",
        "",
        "All hardcoded `false`:",
        "",
    ]
    for k, v in report.guardrails.items():
        lines.append(f"- `{k}`: `{v}`")
    lines += ["", "---", "", "#local-agent #sciencer-dsim"]
    return "\n".join(lines)
