"""P22 CLI — Plan multi-dataset real execution matrix.

Builds the full per-dataset readiness matrix without executing real data,
downloading data, or auto-confirming peer review.

Usage
-----
python -m sciencer_d.btc_icft.pipelines.plan_multi_dataset_real_execution

# Only specific datasets:
python -m sciencer_d.btc_icft.pipelines.plan_multi_dataset_real_execution \\
    --dataset-id DS005620 --dataset-id DS002094

# Strict mode:
python -m sciencer_d.btc_icft.pipelines.plan_multi_dataset_real_execution --strict
"""
from __future__ import annotations

import argparse
import json
import sys

from sciencer_d.btc_icft.runtime.multi_dataset_paths import (
    load_multi_dataset_source_manifest,
)
from sciencer_d.btc_icft.runtime.multi_dataset_real_execution_matrix import (
    build_multi_dataset_matrix,
    write_matrix_outputs,
)


_DEFAULT_SOURCES = "configs/btc_icft/multi_dataset_real_sources.json"
_DEFAULT_OUT = "outputs/btc_icft/multi_dataset_real_execution"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "P22: Build multi-dataset real-execution readiness matrix. "
            "Does NOT execute real data, download data, or confirm peer review."
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
        help="Output directory for matrix artifacts",
    )
    ap.add_argument(
        "--dataset-id",
        action="append",
        default=None,
        dest="dataset_ids",
        help="Limit to specific dataset IDs (repeatable)",
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
        help="Exit nonzero on internal/config error (default: also exit 0 on missing data)",
    )
    args = ap.parse_args(argv)

    try:
        profiles = load_multi_dataset_source_manifest(args.sources)
    except Exception as exc:
        print(f"ERROR loading source manifest: {exc}", file=sys.stderr)
        return 1

    try:
        matrix = build_multi_dataset_matrix(profiles, dataset_ids=args.dataset_ids)
    except Exception as exc:
        print(f"ERROR building matrix: {exc}", file=sys.stderr)
        return 1

    try:
        paths = write_matrix_outputs(matrix, args.out)
    except Exception as exc:
        print(f"ERROR writing matrix outputs: {exc}", file=sys.stderr)
        return 1

    for name, path in paths.items():
        print(f"{name}: {path}")

    if args.json_out:
        summary = {
            "matrix_version": matrix.matrix_version,
            "generated_at": matrix.generated_at,
            "n_datasets": matrix.n_datasets,
            "n_with_local_data": matrix.n_with_local_data,
            "n_ready_for_real_execution": matrix.n_ready_for_real_execution,
            "global_next_action": matrix.global_next_action,
            "global_next_command": matrix.global_next_command,
        }
        print(json.dumps(summary, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
