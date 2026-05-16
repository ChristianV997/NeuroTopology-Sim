"""
Local autonomous research loop (P23).

Runs only allowlisted safe commands, mirrors outputs to Obsidian, optionally
queries Ollama if available, and preserves all real-data and human-review
boundaries.

Usage:
    python -m tools.local_agents.research_loop --dry-run
    python -m tools.local_agents.research_loop --once
    python -m tools.local_agents.research_loop --max-commands 5

stdlib only (except optional Ollama via urllib).
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from tools.local_agents.command_guard import CommandPolicy
from tools.local_agents.event_log import append_event, event_hash
from tools.local_agents.obsidian_sync import ObsidianSyncConfig, sync_obsidian
from tools.local_agents.reporting import build_loop_report, write_loop_report
from tools.local_agents.safe_runner import SafeCommandResult, run_safe_command
from tools.local_agents.state_reader import read_sciencer_state


_LOOP_VERSION = "p24.0"
_SOURCE = "p24_research_loop"

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

_DEFAULT_SAFE_COMMANDS = [
    "make ds005620-autonomous-iteration",
    "make real-data-source-matrix",
    "make multi-dataset-autonomous-iteration",
    "make ds005620-generated-artifact-check",
    "make ontology-language-check",
    "make github-governance-check",
    "make sync-obsidian",
]


@dataclass
class ResearchLoopConfig:
    dry_run: bool = True
    once: bool = False
    max_commands: int = 20
    out_dir: str = "outputs/local_agents"
    vault_root: Optional[str] = None
    policy_path: Optional[str] = None
    timeout_s: int = 120
    continue_on_error: bool = False
    use_ollama: bool = False
    ollama_model: str = "llama3"
    safe_commands: list = field(default_factory=lambda: list(_DEFAULT_SAFE_COMMANDS))


@dataclass
class ResearchLoopResult:
    loop_version: str
    dry_run: bool
    steps_run: int
    steps_passed: int
    steps_failed: int
    steps_blocked: int
    next_action: str
    next_command: str
    output_files: list = field(default_factory=list)
    guardrails: dict = field(default_factory=lambda: dict(_GUARDRAILS))
    warnings: list = field(default_factory=list)
    error: str = ""


def _timestamp() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _try_ollama_summary(config: ResearchLoopConfig, state_summary: str) -> str:
    """Optionally query Ollama for a brief status summary. Returns "" on any failure."""
    if not config.use_ollama:
        return ""
    try:
        from tools.local_agents.ollama_client import OllamaClient
        client = OllamaClient(default_model=config.ollama_model)
        if not client.is_available():
            return ""
        prompt = (
            "Summarize the following ScienceR-Dsim pipeline state in one sentence. "
            "Do not make any empirical claims. Do not suggest running real data.\n\n"
            f"State:\n{state_summary}"
        )
        resp = client.chat(prompt)
        return resp.get("response", "")
    except Exception:
        return ""


def run_research_loop(
    config: Optional[ResearchLoopConfig] = None,
    _command_runner: Optional[Callable] = None,
) -> ResearchLoopResult:
    """
    Run the local autonomous research loop.

    All commands are evaluated by the command guard before execution.
    Blocked commands are never passed to subprocess.
    Real-data boundaries and human-review gates are always preserved.
    """
    if config is None:
        config = ResearchLoopConfig()

    out = Path(config.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    events_path = out / "loop_events.jsonl"
    events_path_p24 = out / "events.jsonl"

    policy = CommandPolicy()
    if config.policy_path:
        try:
            policy = CommandPolicy.load(config.policy_path)
        except FileNotFoundError:
            pass
    if config.dry_run:
        policy.dry_run_always = True

    start_ev = {
        "event": "loop_start",
        "loop_version": _LOOP_VERSION,
        "dry_run": config.dry_run,
        "ts": _timestamp(),
        "source": _SOURCE,
    }
    append_event(events_path, start_ev)
    append_event(events_path_p24, start_ev)

    commands = config.safe_commands[: config.max_commands]
    results: list[SafeCommandResult] = []
    warnings: list[str] = []

    for cmd in commands:
        result = run_safe_command(
            cmd,
            policy=policy,
            cwd=None,
            timeout_s=config.timeout_s,
            dry_run=config.dry_run,
            _runner=_command_runner,
        )
        results.append(result)
        ev = {
            "event": "step",
            "command": cmd,
            "allowed": result.allowed,
            "exit_code": result.exit_code,
            "blocked_reason": result.blocked_reason,
            "elapsed_s": result.elapsed_s,
            "ts": _timestamp(),
            "source": _SOURCE,
        }
        ev["event_id"] = event_hash(ev)
        append_event(events_path, ev)
        append_event(events_path_p24, ev)

        if not result.allowed:
            warnings.append(f"Blocked command: {cmd} — {result.blocked_reason}")

        if not config.dry_run and result.allowed and result.exit_code not in (0, None):
            if not config.continue_on_error:
                warnings.append(f"Stopping after failure: {cmd}")
                break

        if config.once:
            break

    # Read current system state
    try:
        system_state = read_sciencer_state()
        next_action = system_state.global_next_action
        next_command = _next_command_for_action(next_action)
    except Exception as exc:
        next_action = "read_state_error"
        next_command = ""
        warnings.append(f"State read error: {exc}")

    # Optional Ollama summary
    state_summary = f"next_action={next_action}, dry_run={config.dry_run}"
    ollama_summary = _try_ollama_summary(config, state_summary)
    if ollama_summary:
        append_event(events_path, {
            "event": "ollama_summary",
            "summary": ollama_summary,
            "ts": _timestamp(),
            "source": _SOURCE,
        })

    # Build report
    report = build_loop_report(
        loop_version=_LOOP_VERSION,
        dry_run=config.dry_run,
        step_results=results,
        next_action=next_action,
        next_command=next_command,
        warnings=warnings,
    )
    output_files = write_loop_report(report, out)

    # P24: also write named output files
    _write_p24_outputs(out, report, results, next_action, next_command, warnings)
    for fname in ["research_loop_plan.json", "research_loop_results.json",
                  "research_loop_next_action.json", "research_loop_report.md"]:
        fpath = out / fname
        if fpath.exists():
            output_files.append(str(fpath))

    # Optional Obsidian sync
    if config.vault_root:
        try:
            sync_result = sync_obsidian(
                outputs_root="outputs/btc_icft",
                vault_root=config.vault_root,
                config=ObsidianSyncConfig(vault_root=config.vault_root),
            )
            output_files.extend(sync_result.notes_written)
        except Exception as exc:
            warnings.append(f"Obsidian sync error: {exc}")

    end_ev = {
        "event": "loop_end",
        "next_action": next_action,
        "steps_run": len(results),
        "ts": _timestamp(),
        "source": _SOURCE,
        "guardrails": dict(_GUARDRAILS),
    }
    append_event(events_path, end_ev)
    append_event(events_path_p24, end_ev)

    passed = sum(1 for r in results if r.allowed and r.exit_code in (0, None))
    failed = sum(1 for r in results if r.allowed and r.exit_code not in (0, None))
    blocked = sum(1 for r in results if not r.allowed)

    return ResearchLoopResult(
        loop_version=_LOOP_VERSION,
        dry_run=config.dry_run,
        steps_run=len(results),
        steps_passed=passed,
        steps_failed=failed,
        steps_blocked=blocked,
        next_action=next_action,
        next_command=next_command,
        output_files=output_files,
        guardrails=dict(_GUARDRAILS),
        warnings=warnings,
    )


def _write_p24_outputs(
    out: Path,
    report,
    results: list,
    next_action: str,
    next_command: str,
    warnings: list,
) -> None:
    """Write P24 standardized output filenames alongside legacy ones."""
    import json as _json

    plan = {
        "loop_version": report.loop_version,
        "dry_run": report.dry_run,
        "status": "complete" if report.steps_failed == 0 else "failed",
        "steps_total": report.steps_total,
        "steps_completed": report.steps_completed,
        "steps_failed": report.steps_failed,
        "steps_blocked": report.steps_blocked,
        "guardrails": report.guardrails,
    }
    (out / "research_loop_plan.json").write_text(_json.dumps(plan, indent=2), encoding="utf-8")

    step_results = [
        {
            "command": getattr(r, "command", ""),
            "allowed": getattr(r, "allowed", True),
            "exit_code": getattr(r, "exit_code", None),
            "blocked_reason": getattr(r, "blocked_reason", ""),
            "elapsed_s": getattr(r, "elapsed_s", 0.0),
        }
        for r in results
    ]
    (out / "research_loop_results.json").write_text(_json.dumps(step_results, indent=2), encoding="utf-8")

    next_action_doc = {
        "next_action": next_action,
        "next_command": next_command,
        "warnings": warnings,
    }
    (out / "research_loop_next_action.json").write_text(_json.dumps(next_action_doc, indent=2), encoding="utf-8")

    md_lines = [
        "# Research Loop Report (P24)",
        "",
        f"- loop_version: `{report.loop_version}`",
        f"- dry_run: `{report.dry_run}`",
        f"- steps_total: `{report.steps_total}`",
        f"- steps_failed: `{report.steps_failed}`",
        f"- next_action: `{next_action}`",
        "",
        "## Guardrails",
        "",
        "All hardcoded `false`.",
        "",
        "---",
        "#local-agent #sciencer-dsim",
    ]
    (out / "research_loop_report.md").write_text("\n".join(md_lines), encoding="utf-8")


def _next_command_for_action(action: str) -> str:
    """Map a next_action to the suggested next command."""
    _map = {
        "run_mock_e2e": "make ds005620-e2e-mock",
        "fix_contract_validation": "make validate-ds005620-contracts",
        "fix_language_violations": "make ds005620-generated-language-check",
        "build_multi_dataset_matrix": "make real-data-source-matrix",
        "human_peer_review_required": "Review outputs/btc_icft/ds005620_real_execution_gate/human_peer_review_checklist.md",
    }
    if action in _map:
        return _map[action]
    if action.startswith("dataset_operator:"):
        parts = action.split(":")
        if len(parts) >= 2:
            return f"make ds005620-real-artifact-plan  # dataset={parts[1] if len(parts) > 1 else ''}"
    if action.startswith("dataset_gate:"):
        parts = action.split(":")
        if len(parts) >= 2:
            return f"make ds005620-real-execution-gate  # dataset={parts[1] if len(parts) > 1 else ''}"
    return ""


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local autonomous research loop (P23)")
    p.add_argument("--dry-run", action="store_true", default=False, help="Plan only; do not execute commands")
    p.add_argument("--once", action="store_true", default=False, help="Run only the first command")
    p.add_argument("--max-commands", type=int, default=20, help="Maximum commands to run per invocation")
    p.add_argument("--out", default="outputs/local_agents", help="Output directory for loop reports")
    p.add_argument("--vault", default=None, help="Obsidian vault root (optional)")
    p.add_argument("--policy", default=None, help="Path to command_policy.json override")
    p.add_argument("--timeout-s", type=int, default=120, help="Per-command timeout in seconds")
    p.add_argument("--continue-on-error", action="store_true", default=False)
    p.add_argument("--use-ollama", action="store_true", default=False, help="Query Ollama for status summaries")
    p.add_argument("--ollama-model", default="llama3")
    p.add_argument("--json", action="store_true", default=False, help="Print JSON summary to stdout")
    p.add_argument("--strict", action="store_true", default=False, help="Exit nonzero on any failure")
    return p.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(argv)
    config = ResearchLoopConfig(
        dry_run=args.dry_run,
        once=args.once,
        max_commands=args.max_commands,
        out_dir=args.out,
        vault_root=args.vault,
        policy_path=args.policy,
        timeout_s=args.timeout_s,
        continue_on_error=args.continue_on_error,
        use_ollama=args.use_ollama,
        ollama_model=args.ollama_model,
    )
    result = run_research_loop(config)

    if args.json:
        print(json.dumps({
            "loop_version": result.loop_version,
            "dry_run": result.dry_run,
            "steps_run": result.steps_run,
            "steps_passed": result.steps_passed,
            "steps_failed": result.steps_failed,
            "steps_blocked": result.steps_blocked,
            "next_action": result.next_action,
            "next_command": result.next_command,
            "warnings": result.warnings,
            "guardrails": result.guardrails,
            "output_files": result.output_files,
        }, indent=2))

    if result.error:
        print(f"ERROR: {result.error}", file=sys.stderr)
        return 1

    if args.strict and result.steps_failed > 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
