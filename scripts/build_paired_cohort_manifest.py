#!/usr/bin/env python3
"""CLI for discovering, validating, and building paired cohort manifests.

Usage:
    python scripts/build_paired_cohort_manifest.py \
        --input-dir DATA_DIR \
        --condition-a awake \
        --condition-b sed2 \
        --output-dir OUTPUT_DIR \
        --min-pairs 2
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Ensure repository root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.data_loaders.cohort_manifest import (
    CohortManifest,
    CohortStatus,
    build_paired_cohort_manifest,
)


def _parse_aliases(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    aliases: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            k, v = item.split("=", 1)
            aliases[k.strip()] = v.strip()
        else:
            raise ValueError(f"Invalid alias format '{item}'. Expected KEY=VALUE.")
    return aliases


def run_build(args: argparse.Namespace) -> tuple[CohortManifest, dict[str, Any]]:
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pairing_keys = [k.strip() for k in args.pairing_keys.split(",") if k.strip()]
    aliases = _parse_aliases(args.condition_alias)
    formats = [f.strip() for f in args.formats.split(",") if f.strip()] if args.formats else None

    manifest = build_paired_cohort_manifest(
        input_dir=input_dir,
        condition_a=args.condition_a,
        condition_b=args.condition_b,
        pairing_keys=pairing_keys,
        min_pairs=args.min_pairs,
        condition_alias=aliases,
        allow_synthetic=args.allow_synthetic,
        recognized_formats=formats,
    )

    json_path = Path(args.json_out) if args.json_out else output_dir / "paired_cohort_manifest.json"
    csv_path = Path(args.csv_out) if args.csv_out else output_dir / "paired_cohort_manifest.csv"
    summary_path = Path(args.summary_out) if args.summary_out else output_dir / "paired_cohort_summary.json"

    manifest.to_json(json_path)
    manifest.to_csv(csv_path)

    paired_subjects = sorted(list({
        str(p.pairing_key.get("subject", p.pairing_key))
        for p in manifest.paired_records
    }))
    unpaired_subjects = sorted(list({
        str(u.get("pairing_key", {}).get("subject", u.get("pairing_key")))
        for u in manifest.unpaired_records
    }))

    summary = {
        "schema": "NeuroTopologySim.PairedCohortSummary.v1",
        "input_dir": str(input_dir),
        "condition_a": args.condition_a,
        "condition_b": args.condition_b,
        "pairing_keys": pairing_keys,
        "status": manifest.status.value,
        "status_reason": manifest.status_reason,
        "min_pairs": manifest.min_pairs,
        "empirical_paired_count": manifest.empirical_paired_count,
        "synthetic_paired_count": manifest.synthetic_paired_count,
        "total_recordings": manifest.total_recordings,
        "paired_subjects": paired_subjects,
        "unpaired_subjects": unpaired_subjects,
        "duplicate_candidates_count": len(manifest.duplicate_candidates),
        "ambiguous_matches_count": len(manifest.ambiguous_matches),
        "missing_files_count": len(manifest.missing_files),
        "invalid_files_count": len(manifest.invalid_files),
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")

    return manifest, summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Local-only BIDS/cohort manifest builder with provenance and paired-condition readiness gating."
    )
    p.add_argument("--input-dir", "-i", type=Path, required=True, help="Directory containing empirical or test recordings.")
    p.add_argument("--condition-a", "-a", type=str, required=True, help="Exact label of condition A (e.g. awake).")
    p.add_argument("--condition-b", "-b", type=str, required=True, help="Exact label of condition B (e.g. sed2).")
    p.add_argument("--output-dir", "-o", type=Path, required=True, help="Directory to save manifest artifacts.")
    p.add_argument("--min-pairs", type=int, default=2, help="Minimum paired subjects required for valid status (default: 2).")
    p.add_argument("--pairing-keys", type=str, default="subject", help="Comma-separated pairing keys (default: 'subject').")
    p.add_argument("--condition-alias", type=str, default=None, help="Comma-separated condition aliases, e.g. 'sedation=sed2,awake_ec=awake'.")
    p.add_argument("--allow-synthetic", action="store_true", help="Permit synthetic fixtures in cohort pairing (default: False).")
    p.add_argument("--formats", type=str, default=None, help="Optional comma-separated formats filter (e.g. 'vhdr,edf,bdf,fif').")
    p.add_argument("--strict", action="store_true", help="Exit non-zero if status is not valid_paired_cohort.")
    p.add_argument("--json-out", type=Path, default=None, help="Custom path for full manifest JSON.")
    p.add_argument("--csv-out", type=Path, default=None, help="Custom path for manifest CSV.")
    p.add_argument("--summary-out", type=Path, default=None, help="Custom path for summary JSON.")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    manifest, summary = run_build(args)

    print(json.dumps({
        "status": manifest.status.value,
        "empirical_pairs": manifest.empirical_paired_count,
        "min_pairs": manifest.min_pairs,
        "total_recordings": manifest.total_recordings,
    }, indent=2))

    if args.strict and manifest.status != CohortStatus.VALID_PAIRED_COHORT:
        sys.stderr.write(f"Strict check failed: {manifest.status_reason}\n")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
