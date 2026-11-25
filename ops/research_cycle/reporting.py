"""Finite JSON + Markdown + operator surfaces for one audit run."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ops.research_cycle import PACK_ID, PACK_VERSION, SCHEMA_VERSION
from ops.research_cycle.json_util import dumps, json_safe
from ops.research_cycle.safety import assert_write_path

DISCLAIMERS: tuple[str, ...] = (
    "Infrastructure PASS is not a scientific PASS.",
    "Synthetic fixtures are not an empirical PASS.",
    "Inventory is not evidence.",
    "This pack wraps existing CLIs; it does not validate scientific results.",
    "Q/Qabs/f_dress values are never treated as proof.",
    "No ontology promotion, no TOE validation, no consciousness-solved claim.",
)


def build_report(
    *,
    repo_root: Path,
    output_dir: Path,
    generated_at: str | None,
    git_state: Mapping[str, Any] | None,
    steps: list[dict[str, Any]],
    overall_status: str,
    allow_solver: bool,
    catalog_path: str,
    shell_family: str,
) -> dict[str, Any]:
    return json_safe(
        {
            "schema_version": SCHEMA_VERSION,
            "pack_id": PACK_ID,
            "pack_version": PACK_VERSION,
            "generated_at": generated_at,
            "repo_root": str(repo_root),
            "output_dir": str(output_dir),
            "catalog_path": catalog_path,
            "shell_family": shell_family,
            "allow_solver": bool(allow_solver),
            "read_only_default": True,
            "network_enabled": False,
            "downloads_enabled": False,
            "solver_executed": False,
            "scientific_pass": False,
            "empirical_pass": False,
            "infrastructure_pass_is_not_scientific_pass": True,
            "synthetic_is_not_empirical_pass": True,
            "overall_status": overall_status,
            "git": git_state,
            "steps": steps,
            "disclaimers": list(DISCLAIMERS),
            "exit_code_map": {
                "PASS": 0,
                "INCOMPLETE": 10,
                "BLOCKED": 20,
                "FAILURE": 30,
                "NOT_AVAILABLE": 40,
            },
        }
    )


def render_markdown(report: Mapping[str, Any]) -> str:
    steps = report.get("steps") or []
    lines = [
        "# Research-cycle operator pack report",
        "",
        f"- pack_id: `{report.get('pack_id')}`",
        f"- pack_version: `{report.get('pack_version')}`",
        f"- generated_at: `{report.get('generated_at')}`",
        f"- overall_status: `{report.get('overall_status')}`",
        f"- shell_family: `{report.get('shell_family')}`",
        f"- allow_solver: `{report.get('allow_solver')}`",
        f"- scientific_pass: `{report.get('scientific_pass')}`",
        f"- empirical_pass: `{report.get('empirical_pass')}`",
        "",
        "## Integrity disclaimers",
        "",
    ]
    for item in report.get("disclaimers") or DISCLAIMERS:
        lines.append(f"- {item}")
    git = report.get("git") or {}
    lines.extend(
        [
            "",
            "## Repository state (read-only)",
            "",
            f"- HEAD: `{git.get('head')}`",
            f"- branch: `{git.get('branch')}`",
            f"- dirty: `{git.get('dirty')}`",
            "",
            "## Steps",
            "",
            "| order | id | status | exit | timeout_s | wraps |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for step in steps:
        wraps = ", ".join(step.get("wraps") or []) or "null"
        lines.append(
            "| {order} | `{id}` | `{status}` | `{exit}` | `{timeout}` | {wraps} |".format(
                order=step.get("order"),
                id=step.get("id"),
                status=step.get("status"),
                exit=step.get("exit_code"),
                timeout=step.get("timeout_s"),
                wraps=wraps.replace("|", "/"),
            )
        )
    lines.extend(["", "## Step notes", ""])
    for step in steps:
        lines.append(f"### `{step.get('id')}` — {step.get('status')}")
        if step.get("reason"):
            lines.append(f"- reason: {step.get('reason')}")
        if step.get("argv"):
            lines.append(f"- argv: `{' '.join(str(part) for part in step.get('argv') or [])}`")
        if step.get("note"):
            lines.append(f"- {step.get('note')}")
        lines.append("")
    lines.extend(
        [
            "## Exit codes",
            "",
            "- `0` PASS",
            "- `10` INCOMPLETE",
            "- `20` BLOCKED",
            "- `30` FAILURE",
            "- `40` NOT_AVAILABLE",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    json_path = assert_write_path(output_dir / "research_cycle_audit.json", output_dir)
    md_path = assert_write_path(output_dir / "research_cycle_audit.md", output_dir)
    json_path.write_text(dumps(report) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
