"""P22 CLI — Multi-dataset autonomous iteration runtime.

Executes safe per-dataset planning/inspection steps across all registered
datasets. Never executes real data, downloads, or auto-confirms peer review.

Usage
-----
# Dry-run (plan only):
python -m sciencer_d.btc_icft.pipelines.run_multi_dataset_autonomous_iteration --dry-run

# Safe iteration:
python -m sciencer_d.btc_icft.pipelines.run_multi_dataset_autonomous_iteration

# Specific datasets only:
python -m sciencer_d.btc_icft.pipelines.run_multi_dataset_autonomous_iteration \\
    --dataset-id DS005620
"""
from __future__ import annotations

import argparse
import json
import sys

from sciencer_d.btc_icft.runtime.multi_dataset_autonomous_iteration import (
    run_multi_dataset_autonomous_iteration,
)


_DEFAULT_SOURCES = "configs/btc_icft/multi_dataset_real_sources.json"
_DEFAULT_OUT = "outputs/btc_icft/multi_dataset_autonomous_iteration"
_DEFAULT_MATRIX_OUT = "outputs/btc_icft/multi_dataset_real_execution"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "P22: Multi-dataset autonomous iteration runtime. "
            "Runs safe per-dataset planning/inspection steps. "
            "Does NOT execute real data or confirm peer review."
        )
    )
    ap.add_argument(
        "--sources",
        default=_DEFAULT_SOURCES,
        help="Path to multi-dataset source manifest JSON",
    )
    ap.add_argument(
        "--out",
        default=_DEFAULT_OUT,
        help="Output directory for iteration artifacts",
    )
    ap.add_argument(
        "--matrix-out",
        default=_DEFAULT_MATRIX_OUT,
        dest="matrix_out",
        help="Output directory for matrix artifacts",
    )
    ap.add_argument(
        "--cwd",
        default=".",
        help="Working directory (default: current dir)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="Plan iteration without executing planning/inspection steps",
    )
    ap.add_argument(
        "--dataset-id",
        action="append",
        default=None,
        dest="dataset_ids",
        help="Limit iteration to specific dataset IDs (repeatable)",
    )
    ap.add_argument(
        "--max-files",
        type=int,
        default=5000,
        dest="max_files",
        help="Cap on filesystem scan per dataset (default 5000)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json_out",
        help="Print JSON summary to stdout",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit nonzero on internal error (default: also exit 0 on missing data)",
    )
    args = ap.parse_args(argv)

    try:
        result = run_multi_dataset_autonomous_iteration(
            sources_manifest=args.sources,
            out_dir=args.out,
            matrix_out_dir=args.matrix_out,
            cwd=args.cwd,
            dry_run=args.dry_run,
            dataset_ids=args.dataset_ids,
            max_files=args.max_files,
        )
    except Exception as exc:
        print(f"ERROR running multi-dataset iteration: {exc}", file=sys.stderr)
        return 1

    for name, path in result.output_paths.items():
        print(f"{name}: {path}")

    if args.json_out:
        summary = {
            "iteration_id": result.state.iteration_id,
            "iteration_version": result.state.iteration_version,
            "dry_run": result.state.dry_run,
            "last_iteration_status": result.state.last_iteration_status,
            "last_global_next_action": result.state.last_global_next_action,
            "n_datasets": result.state.n_datasets,
            "total_steps": result.state.total_steps,
            "succeeded_steps": result.state.succeeded_steps,
            "failed_steps": result.state.failed_steps,
            "manual_steps": result.state.manual_steps,
            "guardrails": result.state.guardrails,
        }
        print(json.dumps(summary, indent=2))

    if args.strict and result.state.last_iteration_status == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
