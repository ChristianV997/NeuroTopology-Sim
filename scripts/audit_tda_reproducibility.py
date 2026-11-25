#!/usr/bin/env python3
"""CLI runner for TDA backend reproducibility and equivalence audit.

Audits:
- 5 TDA backends: ripser, gudhi, gtda, ripser++, fallback
- Invariants: symmetry, zero diagonal, finite intervals, reordering invariance, bounded capacity
- Strict separation of graph beta_1 and spatial phase charge (Q_spatial)
- Cross-backend pairwise equivalence (bottleneck, Wasserstein, coordinate diffs)
- Emits strict null-safe JSON (allow_nan=False) and terminal summary tables
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add repository root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.tda_reproducibility.audit import run_tda_reproducibility_audit
from tools.tda_reproducibility.fixtures import get_standard_fixtures
from tools.tda_reproducibility.reporters import (
    format_markdown_report,
    format_obsidian_mirror,
    format_terminal_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit TDA backend availability, reproducibility, and equivalence."
    )
    parser.add_argument(
        "--fixtures",
        type=str,
        default=None,
        help="Comma-separated fixture IDs to filter (e.g. circle_s1_12,triangle_equilateral_3).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path for saving report.",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["summary", "json", "markdown"],
        default="summary",
        help="Display format for stdout (default: summary).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail with exit code 1 if any invariant fails or any backend disagreement occurs.",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=256,
        help="Max allowed point capacity bound (default: 256).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for deterministic perturbations and reordering (default: 42).",
    )
    parser.add_argument(
        "--export-obsidian",
        type=str,
        default=None,
        help="Optional path to write an Obsidian mirror markdown note.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    fixtures = get_standard_fixtures()
    if args.fixtures:
        selected_ids = {s.strip() for s in args.fixtures.split(",") if s.strip()}
        fixtures = [f for f in fixtures if f.fixture_id in selected_ids]
        if not fixtures:
            print(f"Error: No matching fixtures found for --fixtures '{args.fixtures}'", file=sys.stderr)
            return 1

    report = run_tda_reproducibility_audit(
        fixtures=fixtures,
        max_points_bound=args.max_points,
        seed=args.seed,
    )

    # Format output for stdout
    if args.format == "json":
        sys.stdout.write(report.to_json(indent=2) + "\n")
    elif args.format == "markdown":
        sys.stdout.write(format_markdown_report(report) + "\n")
    else:
        sys.stdout.write(format_terminal_summary(report) + "\n")

    # Write output file if requested
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".json":
            out_path.write_text(report.to_json(indent=2), encoding="utf-8")
        elif out_path.suffix.lower() in [".md", ".markdown"]:
            out_path.write_text(format_markdown_report(report), encoding="utf-8")
        else:
            out_path.write_text(report.to_json(indent=2), encoding="utf-8")

    # Export Obsidian mirror note if requested
    if args.export_obsidian:
        obs_path = Path(args.export_obsidian)
        obs_path.parent.mkdir(parents=True, exist_ok=True)
        obs_path.write_text(format_obsidian_mirror(report), encoding="utf-8")

    # Determine exit code
    if args.strict:
        if not report.all_invariants_passed:
            print("Strict mode error: One or more invariants failed.", file=sys.stderr)
            return 1
        if report.summary_counts.get("disagreements_count", 0) > 0:
            print("Strict mode error: Backend disagreements detected.", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
