#!/usr/bin/env python3
"""CLI entrypoint for bounded streaming paired-cohort topology execution.

Refuses execution if cohort manifest does not meet strict readiness gates.
Emits strictly descriptive persistent homology and spatial charge metrics.
Never emits a scientific PASS or formal Bayes factor.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cohort_execution import (
    ExecutionStatus,
    execute_cohort_topology,
)


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream paired EEG/electrophysiology cohort recordings and compute descriptive topology.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to the paired cohort manifest JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/cohort_topology"),
        help="Directory to write execution summaries, CSVs, and logs.",
    )
    parser.add_argument(
        "--window-duration-s",
        type=float,
        default=None,
        help="Window duration in seconds (overrides window-samples if provided).",
    )
    parser.add_argument(
        "--window-samples",
        type=int,
        default=1024,
        help="Sliding window size in samples for persistence computation.",
    )
    parser.add_argument(
        "--step-duration-s",
        type=float,
        default=None,
        help="Step duration in seconds between sliding windows.",
    )
    parser.add_argument(
        "--step-samples",
        type=int,
        default=None,
        help="Step size in samples between sliding windows.",
    )
    parser.add_argument(
        "--channel-limit",
        type=int,
        default=None,
        help="Optional upper bound on channels processed per window.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=None,
        help="Optional upper bound on total samples read per recording.",
    )
    parser.add_argument(
        "--filtration-thresholds",
        type=float,
        nargs="+",
        default=None,
        help="Optional list of filtration thresholds in [0, 1].",
    )
    parser.add_argument(
        "--max-points-per-window",
        type=int,
        default=None,
        help="Maximum points permitted per TDA window.",
    )
    parser.add_argument(
        "--max-windows",
        type=int,
        default=None,
        help="Optional upper bound on windows processed per recording.",
    )
    parser.add_argument(
        "--no-memory-telemetry",
        action="store_true",
        help="Disable tracemalloc memory telemetry tracking.",
    )
    parser.add_argument(
        "--diagnostic-only",
        action="store_true",
        help="Validate manifest readiness and emit refusal reasons without reading data.",
    )
    parser.add_argument(
        "--allow-insufficient",
        action="store_true",
        help="Allow execution on manifests with insufficient pairs below min_pairs threshold.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic descriptive analysis.",
    )
    return parser.parse_args(args)


def main() -> int:
    args = parse_args()

    try:
        summary = execute_cohort_topology(
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            window_duration_s=args.window_duration_s,
            window_samples=args.window_samples,
            step_duration_s=args.step_duration_s,
            step_samples=args.step_samples,
            channel_limit=args.channel_limit,
            sample_limit=args.sample_limit,
            filtration_thresholds=args.filtration_thresholds,
            max_points_per_window=args.max_points_per_window,
            max_windows=args.max_windows,
            memory_telemetry=not args.no_memory_telemetry,
            diagnostic_only=args.diagnostic_only,
            allow_insufficient=args.allow_insufficient,
            seed=args.seed,
        )

        # Print summary JSON to stdout
        print(json.dumps(summary.to_dict(), indent=2))

        # Check refusal states
        refusal_states = {
            ExecutionStatus.NO_DATA.value,
            ExecutionStatus.INVALID_INPUT.value,
            ExecutionStatus.INSUFFICIENT_PAIRED_SUBJECTS.value,
            ExecutionStatus.INCOMPLETE_PROVENANCE.value,
            ExecutionStatus.MISSING_OPTIONAL_DEPENDENCY.value,
        }
        if summary.execution_status in refusal_states:
            return 2
        return 0

    except Exception as exc:
        err_payload = {
            "error": str(exc),
            "execution_status": ExecutionStatus.INVALID_INPUT.value,
            "manifest": str(args.manifest),
        }
        print(json.dumps(err_payload, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
