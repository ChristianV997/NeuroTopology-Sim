#!/usr/bin/env python3
"""CLI utility to compile and validate a Simulation Release Bundle.

Connects local simulation execution artifacts to the research-cycle release review layer:
1. Validates the 8-stage chain:
   input provenance → configuration → code revision → seed → execution outcome → artifact manifest → validation → evidence review.
2. Promotes only validated PASS execution records.
3. Preserves PARTIAL, FAILED, TIMEOUT, BLOCKED, and NOT_IMPLEMENTED states.
4. Keeps non-PASS checksums strictly null.
5. Rejects fabricated provenance, path escapes, incomplete manifests, and non-finite values.
6. Emits strictly RFC 8259 finite JSON (no NaN or Inf).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.simulation_release_bridge import (
    SimulationReleaseBuilder,
    compile_simulation_release_bundle,
    render_bundle_markdown,
)
from tools.simulation_release_bridge.contracts import (
    ReleasePromotionStatus,
    dumps_finite_json,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile and validate a Simulation Release Bundle."
    )
    parser.add_argument(
        "--run-dir",
        "-r",
        type=str,
        required=True,
        help="Path to the simulation run directory containing artifacts.",
    )
    parser.add_argument(
        "--cycle-id",
        "-c",
        type=str,
        default="rc-sim-release-001",
        help="Research cycle identifier (default: rc-sim-release-001).",
    )
    parser.add_argument(
        "--bundle-id",
        type=str,
        default=None,
        help="Custom bundle identifier.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Destination path to write compiled bundle JSON.",
    )
    parser.add_argument(
        "--markdown-output",
        "-m",
        type=str,
        default=None,
        help="Destination path to write bundle Markdown audit report.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print compiled bundle JSON to standard output.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Perform strict chain verification and display diagnostics.",
    )
    parser.add_argument(
        "--fail-closed",
        action="store_true",
        help="Exit with non-zero code if bundle is not PROMOTED or validation fails.",
    )
    parser.add_argument(
        "--no-require-canonical-runner",
        action="store_true",
        help="Do not fail closed if the canonical bounded runner is absent.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = Path(args.run_dir).resolve()

    if not run_dir.is_dir():
        sys.stderr.write(f"Error: run directory does not exist: {run_dir}\n")
        return 1

    try:
        bundle = compile_simulation_release_bundle(
            run_dir=run_dir,
            cycle_id=args.cycle_id,
            output_path=args.output,
            markdown_path=args.markdown_output,
            require_canonical_runner=not args.no_require_canonical_runner,
        )
    except Exception as exc:
        sys.stderr.write(f"Error compiling bundle: {exc}\n")
        return 2

    if args.json:
        sys.stdout.write(bundle.to_json())
    elif not args.output:
        # Default summary output
        sys.stdout.write(f"Compiled Bundle: {bundle.bundle_id}\n")
        sys.stdout.write(f"Cycle ID:        {bundle.cycle_id}\n")
        sys.stdout.write(f"Promotion:       {bundle.promotion_status}\n")
        sys.stdout.write(f"Checksum:        {bundle.promotion_checksum or 'null'}\n")
        sys.stdout.write(f"Chain Complete:  {bundle.chain_complete}\n")
        sys.stdout.write(f"Data Mode:       {bundle.data_mode}\n")
        sys.stdout.write(f"Scientific Verdict: {bundle.scientific_verdict}\n")

    if args.verify:
        errors = bundle.diagnostics.get("errors", [])
        rejected = bundle.diagnostics.get("rejected", [])
        missing = bundle.diagnostics.get("missing", [])
        if errors or rejected or missing:
            sys.stderr.write("\nVerification Findings:\n")
            for m in missing:
                sys.stderr.write(f"  [MISSING STAGE] {m}\n")
            for r in rejected:
                sys.stderr.write(f"  [REJECTION]     {r}\n")
            for e in errors:
                sys.stderr.write(f"  [ERROR]         {e}\n")

    if args.fail_closed and bundle.promotion_status != ReleasePromotionStatus.PROMOTED.value:
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
