"""P21 CLI — DS005620 autonomous iteration runtime.

Runs safe mock/validation/planning/gate steps in order and records decisions.
Does NOT execute real data, download data, infer labels, or confirm peer review.

Usage
-----
# Dry-run (plan only, no commands executed):
python -m sciencer_d.btc_icft.pipelines.run_ds005620_autonomous_iteration --dry-run

# Safe full iteration:
python -m sciencer_d.btc_icft.pipelines.run_ds005620_autonomous_iteration

# Custom output directory:
python -m sciencer_d.btc_icft.pipelines.run_ds005620_autonomous_iteration \\
  --out outputs/btc_icft/ds005620_autonomous_iteration

# Continue even if a step fails:
python -m sciencer_d.btc_icft.pipelines.run_ds005620_autonomous_iteration --continue-on-error
"""
from __future__ import annotations

import argparse
import json
import sys

from sciencer_d.btc_icft.runtime.ds005620_autonomous_iteration import (
    run_ds005620_autonomous_iteration,
)

_DEFAULT_OUT = "outputs/btc_icft/ds005620_autonomous_iteration"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "P21: DS005620 autonomous iteration runtime. "
            "Runs safe mock/validation/planning/gate steps in order. "
            "Does NOT execute real data or confirm peer review."
        )
    )
    ap.add_argument(
        "--out",
        default=_DEFAULT_OUT,
        help="Output directory for iteration artifacts",
    )
    ap.add_argument(
        "--cwd",
        default=".",
        help="Working directory for running commands (default: current dir)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="Plan iteration without executing any commands",
    )
    ap.add_argument(
        "--continue-on-error",
        action="store_true",
        default=False,
        dest="continue_on_error",
        help="Continue to remaining steps even if a safe step fails",
    )
    ap.add_argument(
        "--timeout-s",
        type=int,
        default=300,
        dest="timeout_s",
        help="Per-step command timeout in seconds (default: 300)",
    )
    ap.add_argument(
        "--max-steps",
        type=int,
        default=None,
        dest="max_steps",
        help="Stop after this many steps",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json_out",
        help="Print JSON summary to stdout",
    )
    ap.add_argument(
        "--skip-mock",
        action="store_true",
        default=False,
        dest="skip_mock",
        help="Skip all mock E2E steps (run planning/gate steps only)",
    )
    ap.add_argument(
        "--skip-real-planning",
        action="store_true",
        default=False,
        dest="skip_real_planning",
        help="Skip real/local preflight, artifact plan, and execution gate steps",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit nonzero if any required safe step fails (default behavior, explicit flag)",
    )
    args = ap.parse_args(argv)

    try:
        result = run_ds005620_autonomous_iteration(
            out_dir=args.out,
            cwd=args.cwd,
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error,
            timeout_s=args.timeout_s,
            max_steps=args.max_steps,
            skip_mock=args.skip_mock,
            skip_real_planning=args.skip_real_planning,
        )
    except Exception as exc:
        print(f"ERROR running autonomous iteration: {exc}", file=sys.stderr)
        return 1

    for name, path in result.output_paths.items():
        print(f"{name}: {path}")

    if args.json_out:
        summary = {
            "iteration_id": result.state.iteration_id,
            "iteration_version": result.state.iteration_version,
            "dataset_id": result.state.dataset_id,
            "dry_run": result.state.dry_run,
            "last_iteration_status": result.state.last_iteration_status,
            "last_next_action": result.state.last_next_action,
            "total_steps": result.state.total_steps,
            "succeeded_steps": result.state.succeeded_steps,
            "failed_steps": result.state.failed_steps,
            "skipped_steps": result.state.skipped_steps,
            "manual_steps": result.state.manual_steps,
            "final_next_action": result.decision.final_next_action,
            "final_next_command": result.decision.final_next_command,
            "blocked_by": result.decision.blocked_by,
            "guardrails": result.state.guardrails,
        }
        print(json.dumps(summary, indent=2))

    # Exit nonzero if iteration failed (unless --continue-on-error was passed)
    if result.state.last_iteration_status == "failed" and not args.continue_on_error:
        print(
            f"Iteration failed: next_action={result.state.last_next_action}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
