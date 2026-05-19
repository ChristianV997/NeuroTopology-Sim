"""
Local continuous operations runner (P25).

Executes only allowlisted safe commands in a finite, lock-protected loop.
Writes structured outputs to outputs/local_ops/.

CLI:
    python -m tools.local_ops.runner --mode once
    python -m tools.local_ops.runner --mode dry-run
    python -m tools.local_ops.runner --mode loop --max-iterations 3

stdlib only.
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

from tools.local_agents.command_guard import CommandPolicy, evaluate_command
from tools.local_agents.event_log import append_event, event_hash
from tools.local_agents.safe_runner import SafeCommandResult, run_safe_command, run_command_sequence
from tools.local_ops.lockfile import acquire_lock, release_lock, read_lock
from tools.local_ops.retention import archive_current_run, rotate_run_outputs
from tools.local_ops.reporting import build_ops_report
from tools.local_ops.status import build_ops_status


_RUNNER_VERSION = "p25.0"
_SOURCE = "p25_local_ops_runner"

_GUARDRAILS = {
    "executes_real_data": False,
    "downloads_data": False,
    "auto_confirms_peer_review": False,
    "auto_pushes_git": False,
    "auto_merges_pr": False,
    "auto_closes_pr": False,
    "auto_runs_real_benchmark": False,
    "infers_labels": False,
    "fabricates_targets": False,
}

_DEFAULT_SAFE_SEQUENCE = [
    "make local-agent-healthcheck",
    "make local-agent-loop-once",
    "make local-agent-status",
    "make sync-obsidian",
]

_DEFAULT_OPTIONAL_COMMANDS = [
    "make real-data-source-matrix",
    "make multi-dataset-autonomous-iteration",
    "make validate-real-data-source-matrix",
]

_FORBIDDEN_SUBSTRINGS = [
    "--execute --peer-reviewed-contract-confirmed",
    "dandi download",
    "openneuro download",
    "wget",
    "curl",
    "aws s3 cp",
    "rm -rf",
    "git push",
    "gh pr merge",
    "gh pr close",
    ".env",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
]


def _ts() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _load_policy_config(policy_path: str) -> dict:
    p = Path(policy_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_command_forbidden(cmd: str) -> bool:
    for substr in _FORBIDDEN_SUBSTRINGS:
        if substr in cmd:
            return True
    return False


@dataclass
class LocalOpsRunnerConfig:
    mode: str = "dry-run"
    out_dir: str = "outputs/local_ops"
    local_agent_root: str = "outputs/local_agents"
    vault: str = "obsidian"
    policy_path: str = "configs/local_ops/local_ops_policy.json"
    interval_seconds: int = 1800
    max_iterations: int = 1
    max_consecutive_failures: int = 3
    continue_on_error: bool = False
    no_lock: bool = False
    lock_ttl_seconds: int = 7200
    retention_keep_last: int = 25
    safe_commands: list = field(default_factory=lambda: list(_DEFAULT_SAFE_SEQUENCE))
    optional_commands: list = field(default_factory=lambda: list(_DEFAULT_OPTIONAL_COMMANDS))
    timeout_s: int = 300


@dataclass
class LocalOpsRunResult:
    runner_version: str
    mode: str
    status: str
    iterations_completed: int
    safe_commands_succeeded: int
    safe_commands_failed: int
    commands_blocked: int
    next_action: str
    manual_required: bool
    human_review_required: bool
    real_data_boundary_hit: bool
    generated_at: str
    warnings: list = field(default_factory=list)
    guardrails: dict = field(default_factory=lambda: dict(_GUARDRAILS))


def _determine_next_action(
    all_results: list[SafeCommandResult],
    warnings: list[str],
    consecutive_failures: int,
    max_consecutive_failures: int,
) -> tuple[str, bool, bool]:
    """Returns (next_action, manual_required, human_review_required)."""
    if consecutive_failures >= max_consecutive_failures:
        return "back_off_repeated_failures", False, False
    for r in all_results:
        if not r.allowed:
            return "policy_blocked_command", False, False
    failed = [r for r in all_results if r.allowed and r.exit_code not in (0, None)]
    if failed:
        return "fix_failed_step", False, False
    return "run_local_ops_once", False, False


def _write_state(out: Path, result: LocalOpsRunResult) -> None:
    state = {
        "status": result.status,
        "mode": result.mode,
        "runner_version": result.runner_version,
        "iterations_completed": result.iterations_completed,
        "safe_commands_succeeded": result.safe_commands_succeeded,
        "safe_commands_failed": result.safe_commands_failed,
        "commands_blocked": result.commands_blocked,
        "next_action": result.next_action,
        "manual_required": result.manual_required,
        "human_review_required": result.human_review_required,
        "real_data_boundary_hit": result.real_data_boundary_hit,
        "generated_at": result.generated_at,
        "warnings": result.warnings,
        "guardrails": result.guardrails,
    }
    (out / "local_ops_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def _write_plan(out: Path, config: LocalOpsRunnerConfig, commands: list[str]) -> None:
    plan = {
        "runner_version": _RUNNER_VERSION,
        "mode": config.mode,
        "max_iterations": config.max_iterations,
        "interval_seconds": config.interval_seconds,
        "safe_commands": commands,
        "guardrails": dict(_GUARDRAILS),
        "generated_at": _ts(),
    }
    (out / "local_ops_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")


def _write_results(out: Path, all_results: list[SafeCommandResult]) -> None:
    rows = []
    for r in all_results:
        rows.append({
            "command": r.command,
            "allowed": r.allowed,
            "exit_code": r.exit_code,
            "blocked_reason": r.blocked_reason,
            "elapsed_s": r.elapsed_s,
            "dry_run": r.dry_run,
        })
    (out / "local_ops_results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _write_next_action(out: Path, next_action: str, warnings: list[str]) -> None:
    doc = {"next_action": next_action, "warnings": warnings, "generated_at": _ts()}
    (out / "local_ops_next_action.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")


def run_one_cycle(
    config: LocalOpsRunnerConfig,
    out: Path,
    events_path: Path,
    policy: CommandPolicy,
    _command_runner: Optional[Callable] = None,
) -> tuple[list[SafeCommandResult], list[str]]:
    """Execute one cycle of safe commands. Returns (results, warnings)."""
    warnings: list[str] = []
    all_results: list[SafeCommandResult] = []
    dry_run = config.mode == "dry-run"

    commands = list(config.safe_commands)

    for cmd in commands:
        if _is_command_forbidden(cmd):
            ev = {
                "event": "command_forbidden",
                "command": cmd,
                "ts": _ts(),
                "source": _SOURCE,
            }
            append_event(events_path, ev)
            warnings.append(f"Forbidden command skipped: {cmd}")
            blocked_result = SafeCommandResult(
                command=cmd,
                allowed=False,
                blocked_reason="matches local_ops forbidden substring",
                exit_code=None,
                stdout="",
                stderr="",
                elapsed_s=0.0,
                dry_run=dry_run,
            )
            all_results.append(blocked_result)
            if not config.continue_on_error:
                break
            continue

        result = run_safe_command(
            cmd,
            policy=policy,
            cwd=None,
            timeout_s=config.timeout_s,
            dry_run=dry_run,
            _runner=_command_runner,
        )
        all_results.append(result)

        ev = {
            "event": "step",
            "command": cmd,
            "allowed": result.allowed,
            "exit_code": result.exit_code,
            "blocked_reason": result.blocked_reason,
            "elapsed_s": result.elapsed_s,
            "ts": _ts(),
            "source": _SOURCE,
        }
        ev["event_id"] = event_hash(ev)
        append_event(events_path, ev)

        if not result.allowed:
            warnings.append(f"Blocked: {cmd} — {result.blocked_reason}")

        if not dry_run and result.allowed and result.exit_code not in (0, None):
            warnings.append(f"Command failed (exit={result.exit_code}): {cmd}")
            if not config.continue_on_error:
                break

    return all_results, warnings


def run_local_ops(
    config: Optional[LocalOpsRunnerConfig] = None,
    _command_runner: Optional[Callable] = None,
) -> LocalOpsRunResult:
    """
    Main entry point for the local continuous operations runner.

    Modes:
    - dry-run: write plan/results, do not execute commands
    - once: execute one safe cycle
    - loop: repeat until max_iterations or interrupted

    All commands are evaluated by command_guard before execution.
    Real-data boundaries and human-review gates are always preserved.
    """
    if config is None:
        config = LocalOpsRunnerConfig()

    out = Path(config.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    events_path = out / "local_ops_events.jsonl"
    lock_path = out / "local_ops_lock.json"

    # Load command policy: try config.policy_path, then fall back to local_agents default
    policy = CommandPolicy()
    policy_candidates = [
        config.policy_path,
        "configs/local_agents/command_policy.json",
    ]
    for candidate in policy_candidates:
        if candidate and Path(candidate).exists():
            try:
                policy = CommandPolicy.load(candidate)
                break
            except Exception:
                pass
    if config.mode == "dry-run":
        policy.dry_run_always = True

    # Archive previous run outputs before writing new ones
    if config.mode != "dry-run":
        try:
            archive_current_run(out)
            rotate_run_outputs(out, config.retention_keep_last)
        except Exception:
            pass

    # Write the run plan
    _write_plan(out, config, config.safe_commands)

    # Dry-run: write plan only
    if config.mode == "dry-run":
        append_event(events_path, {
            "event": "dry_run_start",
            "runner_version": _RUNNER_VERSION,
            "mode": "dry-run",
            "ts": _ts(),
            "source": _SOURCE,
        })
        results, warnings = run_one_cycle(config, out, events_path, policy, _command_runner)
        _write_results(out, results)
        next_action = "run_local_ops_once"
        _write_next_action(out, next_action, warnings)

        succeeded = sum(1 for r in results if r.allowed and r.exit_code in (0, None))
        failed = sum(1 for r in results if r.allowed and r.exit_code not in (0, None))
        blocked = sum(1 for r in results if not r.allowed)

        run_result = LocalOpsRunResult(
            runner_version=_RUNNER_VERSION,
            mode="dry-run",
            status="dry_run_complete",
            iterations_completed=1,
            safe_commands_succeeded=succeeded,
            safe_commands_failed=failed,
            commands_blocked=blocked,
            next_action=next_action,
            manual_required=False,
            human_review_required=False,
            real_data_boundary_hit=False,
            generated_at=_ts(),
            warnings=warnings,
        )
        _write_state(out, run_result)

        report_md = build_ops_report(
            runner_version=_RUNNER_VERSION,
            mode="dry-run",
            iterations_completed=1,
            safe_commands_succeeded=succeeded,
            safe_commands_failed=failed,
            commands_blocked=blocked,
            status="dry_run_complete",
            next_action=next_action,
            warnings=warnings,
            guardrails=_GUARDRAILS,
        )
        (out / "local_ops_report.md").write_text(report_md, encoding="utf-8")

        # Build ops status
        _write_ops_status(out, config, run_result)

        append_event(events_path, {
            "event": "dry_run_end",
            "runner_version": _RUNNER_VERSION,
            "ts": _ts(),
            "source": _SOURCE,
        })
        return run_result

    # Acquire lock (once and loop modes)
    lock_owner = f"{_SOURCE}_pid{__import__('os').getpid()}"
    if not config.no_lock:
        acquired = acquire_lock(lock_path, ttl_seconds=config.lock_ttl_seconds, owner=lock_owner)
        if not acquired:
            existing = read_lock(lock_path)
            owner_info = existing.owner if existing else "unknown"
            run_result = LocalOpsRunResult(
                runner_version=_RUNNER_VERSION,
                mode=config.mode,
                status="locked",
                iterations_completed=0,
                safe_commands_succeeded=0,
                safe_commands_failed=0,
                commands_blocked=0,
                next_action="wait_for_lock_release",
                manual_required=False,
                human_review_required=False,
                real_data_boundary_hit=False,
                generated_at=_ts(),
                warnings=[f"Lock held by {owner_info}"],
            )
            _write_state(out, run_result)
            _write_next_action(out, "wait_for_lock_release", [f"Lock held by {owner_info}"])
            append_event(events_path, {
                "event": "lock_blocked",
                "owner": owner_info,
                "ts": _ts(),
                "source": _SOURCE,
            })
            return run_result

    append_event(events_path, {
        "event": "run_start",
        "runner_version": _RUNNER_VERSION,
        "mode": config.mode,
        "max_iterations": config.max_iterations,
        "ts": _ts(),
        "source": _SOURCE,
    })

    all_results: list[SafeCommandResult] = []
    all_warnings: list[str] = []
    iterations_completed = 0
    consecutive_failures = 0
    overall_status = "succeeded"

    try:
        iterations = config.max_iterations if config.mode == "loop" else 1

        for iteration in range(iterations):
            append_event(events_path, {
                "event": "iteration_start",
                "iteration": iteration + 1,
                "ts": _ts(),
                "source": _SOURCE,
            })

            results, warnings = run_one_cycle(config, out, events_path, policy, _command_runner)
            all_results.extend(results)
            all_warnings.extend(warnings)
            iterations_completed += 1

            # Track consecutive failures
            iter_failed = sum(
                1 for r in results if r.allowed and r.exit_code not in (0, None)
            )
            if iter_failed > 0:
                consecutive_failures += 1
            else:
                consecutive_failures = 0

            append_event(events_path, {
                "event": "iteration_end",
                "iteration": iteration + 1,
                "failed_commands": iter_failed,
                "ts": _ts(),
                "source": _SOURCE,
            })

            if consecutive_failures >= config.max_consecutive_failures:
                all_warnings.append(
                    f"Stopping after {consecutive_failures} consecutive failures"
                )
                overall_status = "failed"
                break

            # Sleep between iterations (loop mode only)
            if config.mode == "loop" and iteration < iterations - 1:
                time.sleep(config.interval_seconds)

    finally:
        if not config.no_lock:
            release_lock(lock_path, owner=lock_owner)

    succeeded = sum(1 for r in all_results if r.allowed and r.exit_code in (0, None))
    failed = sum(1 for r in all_results if r.allowed and r.exit_code not in (0, None))
    blocked = sum(1 for r in all_results if not r.allowed)

    if overall_status != "failed":
        overall_status = "succeeded" if failed == 0 else "failed"

    next_action, manual_required, human_review_required = _determine_next_action(
        all_results, all_warnings, consecutive_failures, config.max_consecutive_failures
    )

    run_result = LocalOpsRunResult(
        runner_version=_RUNNER_VERSION,
        mode=config.mode,
        status=overall_status,
        iterations_completed=iterations_completed,
        safe_commands_succeeded=succeeded,
        safe_commands_failed=failed,
        commands_blocked=blocked,
        next_action=next_action,
        manual_required=manual_required,
        human_review_required=human_review_required,
        real_data_boundary_hit=False,
        generated_at=_ts(),
        warnings=all_warnings,
    )

    _write_state(out, run_result)
    _write_results(out, all_results)
    _write_next_action(out, next_action, all_warnings)

    report_md = build_ops_report(
        runner_version=_RUNNER_VERSION,
        mode=config.mode,
        iterations_completed=iterations_completed,
        safe_commands_succeeded=succeeded,
        safe_commands_failed=failed,
        commands_blocked=blocked,
        status=overall_status,
        next_action=next_action,
        warnings=all_warnings,
        guardrails=_GUARDRAILS,
    )
    (out / "local_ops_report.md").write_text(report_md, encoding="utf-8")

    _write_ops_status(out, config, run_result)

    append_event(events_path, {
        "event": "run_end",
        "status": overall_status,
        "iterations_completed": iterations_completed,
        "ts": _ts(),
        "source": _SOURCE,
        "guardrails": dict(_GUARDRAILS),
    })

    return run_result


def _write_ops_status(
    out: Path,
    config: LocalOpsRunnerConfig,
    run_result: LocalOpsRunResult,
) -> None:
    """Write local_ops_status.json from current runner state."""
    try:
        status = build_ops_status(
            output_root=str(out),
            local_agent_root=config.local_agent_root,
            btc_root="outputs/btc_icft",
        )
    except Exception as exc:
        status = {
            "ok": True,
            "generated_at": _ts(),
            "last_run_status": run_result.status,
            "next_action": run_result.next_action,
            "error": str(exc),
        }
    (out / "local_ops_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local continuous operations runner (P25)")
    p.add_argument(
        "--mode",
        choices=["once", "loop", "dry-run"],
        default="dry-run",
        help="Execution mode: once (one cycle), loop (repeat), dry-run (plan only)",
    )
    p.add_argument("--out", default="outputs/local_ops", help="Output directory")
    p.add_argument("--local-agent-root", default="outputs/local_agents")
    p.add_argument("--vault", default="obsidian", help="Obsidian vault root")
    p.add_argument("--policy", default="configs/local_ops/local_ops_policy.json")
    p.add_argument("--interval-seconds", type=int, default=1800, help="Seconds between loop iterations")
    p.add_argument("--max-iterations", type=int, default=1, help="Maximum loop iterations")
    p.add_argument("--max-commands", type=int, default=None, help="Maximum commands per iteration")
    p.add_argument("--continue-on-error", action="store_true", default=False)
    p.add_argument("--no-lock", action="store_true", default=False, help="Skip lockfile (unsafe)")
    p.add_argument("--json", dest="json_out", action="store_true", default=False)
    return p.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(argv)

    policy_cfg = _load_policy_config(args.policy)

    safe_commands = policy_cfg.get("safe_command_sequence", list(_DEFAULT_SAFE_SEQUENCE))
    if args.max_commands is not None:
        safe_commands = safe_commands[: args.max_commands]

    config = LocalOpsRunnerConfig(
        mode=args.mode,
        out_dir=args.out,
        local_agent_root=args.local_agent_root,
        vault=args.vault,
        policy_path=args.policy,
        interval_seconds=args.interval_seconds,
        max_iterations=args.max_iterations,
        continue_on_error=args.continue_on_error,
        no_lock=args.no_lock,
        safe_commands=safe_commands,
        optional_commands=policy_cfg.get("optional_safe_commands", list(_DEFAULT_OPTIONAL_COMMANDS)),
        lock_ttl_seconds=policy_cfg.get("lock_ttl_seconds", 7200),
        retention_keep_last=policy_cfg.get("retention_keep_last", 25),
    )

    result = run_local_ops(config)

    if args.json_out:
        print(json.dumps({
            "runner_version": result.runner_version,
            "mode": result.mode,
            "status": result.status,
            "iterations_completed": result.iterations_completed,
            "safe_commands_succeeded": result.safe_commands_succeeded,
            "safe_commands_failed": result.safe_commands_failed,
            "commands_blocked": result.commands_blocked,
            "next_action": result.next_action,
            "warnings": result.warnings,
            "guardrails": result.guardrails,
        }, indent=2))

    if result.status == "locked":
        print(f"[local_ops] Runner locked: {result.warnings}", file=sys.stderr)
        return 2

    if result.status == "failed":
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
