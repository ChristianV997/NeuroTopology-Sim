"""Emit Obsidian notes, command-center payloads, and one RAG pack under --output-dir."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ops.research_cycle.json_util import dumps
from ops.research_cycle.reporting import DISCLAIMERS
from ops.research_cycle.safety import assert_write_path


def emit_surfaces(report: Mapping[str, Any], output_dir: Path) -> dict[str, list[str]]:
    written = {
        "obsidian": _write_obsidian(report, output_dir / "obsidian"),
        "command_center": _write_command_center(report, output_dir / "command_center"),
        "rag": _write_rag(report, output_dir / "rag"),
    }
    return written


def _write_obsidian(report: Mapping[str, Any], root: Path) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    steps = list(report.get("steps") or [])
    notes = {
        "00_index.md": _index_note(report),
        "01_safety.md": _safety_note(report),
        "02_exit_codes.md": _exit_note(),
        "03_steps.md": _steps_note(steps),
        "04_scientific_integrity.md": _integrity_note(),
        "05_windows_vs_posix.md": _shell_note(report),
        "06_wrapped_clis.md": _wraps_note(steps),
        "07_limitations.md": _limits_note(report),
    }
    paths: list[str] = []
    for name, body in notes.items():
        path = assert_write_path(root / name, root.parent)
        path.write_text(body, encoding="utf-8")
        paths.append(str(path))
    return paths


def _write_command_center(report: Mapping[str, Any], root: Path) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    payloads = {
        "health.json": {
            "ok": report.get("overall_status") in {"PASS", "INCOMPLETE"},
            "service": "research_cycle_operator_pack",
            "scientific_pass": False,
        },
        "status.json": {
            "ok": True,
            "overall_status": report.get("overall_status"),
            "scientific_pass": False,
            "empirical_pass": False,
        },
        "guardrails.json": {
            "read_only_default": True,
            "network_enabled": False,
            "solver_executed": False,
            "disclaimers": list(DISCLAIMERS),
        },
        "steps.json": {"steps": report.get("steps") or []},
        "action_queue.json": {
            "items": [],
            "note": "This pack does not enqueue live actions, downloads, or merges.",
        },
        "git_echo.json": report.get("git") or {},
    }
    paths: list[str] = []
    for name, payload in payloads.items():
        path = assert_write_path(root / name, root.parent)
        path.write_text(dumps(payload) + "\n", encoding="utf-8")
        paths.append(str(path))
    return paths


def _write_rag(report: Mapping[str, Any], root: Path) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    pack = {
        "pack_id": "research_cycle_operator_rag",
        "mode": "operator_documentation_only",
        "scientific_pass": False,
        "overall_status": report.get("overall_status"),
        "disclaimers": list(DISCLAIMERS),
        "sources": [
            "docs/ops/research_cycle_operator_pack.md",
            "ops/research_cycle/catalog.json",
            str(report.get("output_dir")),
        ],
    }
    json_path = assert_write_path(root / "pack.json", root.parent)
    md_path = assert_write_path(root / "pack.md", root.parent)
    json_path.write_text(dumps(pack) + "\n", encoding="utf-8")
    md_path.write_text(
        "# Research-cycle operator RAG pack\n\n"
        "Retrieval text for operator commands only. Not empirical evidence.\n\n"
        + "\n".join(f"- {item}" for item in DISCLAIMERS)
        + "\n",
        encoding="utf-8",
    )
    return [str(json_path), str(md_path)]


def _index_note(report: Mapping[str, Any]) -> str:
    return (
        "# Research-cycle operator pack\n\n"
        f"overall_status: `{report.get('overall_status')}`\n\n"
        "Read-only wrapper around existing NeuroTopology-Sim CLIs.\n"
        "Infrastructure PASS is not a scientific PASS.\n"
    )


def _safety_note(report: Mapping[str, Any]) -> str:
    return (
        "# Safety\n\n"
        f"- allow_solver: `{report.get('allow_solver')}`\n"
        f"- network_enabled: `{report.get('network_enabled')}`\n"
        "- Writes only under `--output-dir`.\n"
        "- No downloads, package installs, daemons, or git mutation.\n"
    )


def _exit_note() -> str:
    return (
        "# Exit codes\n\n"
        "- 0 PASS\n"
        "- 10 INCOMPLETE\n"
        "- 20 BLOCKED\n"
        "- 30 FAILURE\n"
        "- 40 NOT_AVAILABLE\n\n"
        "Missing commands are NOT_AVAILABLE. They are never silent skip-as-pass.\n"
    )


def _steps_note(steps: list[dict[str, Any]]) -> str:
    lines = ["# Steps\n"]
    for step in steps:
        lines.append(f"- `{step.get('id')}` → `{step.get('status')}`")
    return "\n".join(lines) + "\n"


def _integrity_note() -> str:
    return "# Scientific integrity\n\n" + "\n".join(f"- {item}" for item in DISCLAIMERS) + "\n"


def _shell_note(report: Mapping[str, Any]) -> str:
    return (
        "# Windows vs POSIX\n\n"
        f"This run's shell_family: `{report.get('shell_family')}`\n\n"
        "- POSIX: `scripts/run_research_cycle_audit.sh`\n"
        "- Windows PowerShell: `scripts/run_research_cycle_audit.ps1`\n"
        "- The two wrappers are not interchangeable.\n"
    )


def _wraps_note(steps: list[dict[str, Any]]) -> str:
    lines = ["# Wrapped CLIs\n"]
    for step in steps:
        wraps = step.get("wraps") or []
        lines.append(f"- `{step.get('id')}`: {', '.join(wraps) if wraps else 'builtin'}")
    return "\n".join(lines) + "\n"


def _limits_note(report: Mapping[str, Any]) -> str:
    return (
        "# Limitations\n\n"
        f"- overall_status `{report.get('overall_status')}` is an operator-pack status.\n"
        "- It does not authorize merge, release, or empirical claims.\n"
        "- Fixture dry-runs are synthetic. Synthetic ≠ empirical PASS.\n"
    )
