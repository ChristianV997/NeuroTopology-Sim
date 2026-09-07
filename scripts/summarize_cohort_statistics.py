#!/usr/bin/env python3
"""CLI for computing paired-cohort descriptive and non-parametric statistics.

Usage:
    python scripts/summarize_cohort_statistics.py \
      --input cohort_metrics.json \
      --output cohort_statistics.json \
      --correction holm
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

# Ensure repository root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.cohort_statistics import (
    CohortStatisticsReport,
    HypothesisAlternative,
    MultiplicityMethod,
    ProvenanceStatus,
    build_cohort_statistics_report,
    export_report_csv,
    export_report_json,
)


def load_input_data(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Loads metrics records and metadata from JSON or CSV file."""
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    meta: dict[str, Any] = {}
    records: list[dict[str, Any]] = []

    if suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            records = raw
        elif isinstance(raw, dict):
            meta = {k: v for k, v in raw.items() if k != "records"}
            if "records" in raw and isinstance(raw["records"], list):
                records = raw["records"]
            elif "per_subject" in raw and isinstance(raw["per_subject"], list):
                # Compatible with run_cohort_eeg_topology output structure
                records = raw["per_subject"]
            elif "paired_records" in raw and isinstance(raw["paired_records"], list):
                # Compatible with paired_cohort_manifest output structure
                for p in raw["paired_records"]:
                    subj = p.get("pairing_key", {}).get("subject", "unknown")
                    rec_a = p.get("condition_a_record", {})
                    rec_b = p.get("condition_b_record", {})
                    # If metrics embedded or summary metrics
                    records.append({
                        "subject": subj,
                        "condition_a_metrics": rec_a.get("metrics", {}),
                        "condition_b_metrics": rec_b.get("metrics", {}),
                    })
            else:
                # Dict of subject -> {condition_a: ..., condition_b: ...}
                for subj, data in raw.items():
                    if isinstance(data, dict):
                        records.append({"subject": subj, **data})
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(dict(row))
    else:
        raise ValueError(f"Unsupported input file format: {suffix}. Expected .json or .csv.")

    return records, meta


def run_summary(args: argparse.Namespace) -> CohortStatisticsReport:
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records, meta = load_input_data(input_path)

    cond_a = args.condition_a or meta.get("condition_a", meta.get("condition_a_label", "awake"))
    cond_b = args.condition_b or meta.get("condition_b", meta.get("condition_b_label", "sed2"))
    is_synth = args.is_synthetic or meta.get("is_synthetic", False)
    prov = args.provenance_status or meta.get("provenance_status", ProvenanceStatus.EMPIRICAL.value)
    dataset_id = args.dataset_id or meta.get("dataset_id")

    metrics_filter = [m.strip() for m in args.metrics.split(",") if m.strip()] if args.metrics else None

    report = build_cohort_statistics_report(
        records,
        condition_a_label=cond_a,
        condition_b_label=cond_b,
        metrics=metrics_filter,
        multiplicity_method=args.correction,
        alternative=args.alternative,
        min_pairs=args.min_pairs,
        is_synthetic=is_synth,
        provenance_status=prov,
        dataset_id=dataset_id,
    )

    export_report_json(report, output_path)

    if args.csv_output:
        csv_path = Path(args.csv_output)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        export_report_csv(report, csv_path)

    return report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compute paired-cohort descriptive moments, Wilcoxon tests, and multiplicity corrections."
    )
    p.add_argument("--input", "-i", type=Path, required=True, help="Input metrics JSON or CSV file.")
    p.add_argument("--output", "-o", type=Path, required=True, help="Output statistics JSON file.")
    p.add_argument(
        "--correction", "-c",
        type=str,
        default="holm",
        choices=["holm", "bonferroni", "fdr_bh", "none"],
        help="Multiplicity correction method across evaluated metrics (default: holm).",
    )
    p.add_argument(
        "--alternative", "-a",
        type=str,
        default="two-sided",
        choices=["two-sided", "greater", "less"],
        help="Alternative hypothesis direction for Wilcoxon signed-rank test (default: two-sided).",
    )
    p.add_argument("--min-pairs", type=int, default=2, help="Minimum valid pairs for inferential testing (default: 2).")
    p.add_argument("--metrics", type=str, default=None, help="Comma-separated subset of metrics to evaluate.")
    p.add_argument("--condition-a", type=str, default=None, help="Label for condition A (e.g. awake).")
    p.add_argument("--condition-b", type=str, default=None, help="Label for condition B (e.g. sed2).")
    p.add_argument("--csv-output", type=Path, default=None, help="Optional output path for tabular summary CSV.")
    p.add_argument("--is-synthetic", action="store_true", help="Explicitly mark inputs as synthetic fixtures.")
    p.add_argument("--provenance-status", type=str, default=None, choices=["empirical", "synthetic_fixture", "incomplete_provenance"])
    p.add_argument("--dataset-id", type=str, default=None, help="Dataset identifier (e.g. ds005620).")
    p.add_argument("--strict", action="store_true", help="Exit non-zero if any test errors occur or if no valid pairs exist.")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    report = run_summary(args)

    print(json.dumps({
        "status": "completed",
        "dataset_id": report.dataset_id,
        "total_subjects": report.total_subjects_evaluated,
        "metrics_evaluated": list(report.metrics.keys()),
        "multiplicity_method": report.multiplicity_method,
        "checksum": report.checksum,
    }, indent=2))

    if args.strict:
        for m_name, m in report.metrics.items():
            if m.inferential_stats.status == "execution_error":
                sys.stderr.write(f"Strict failure: metric '{m_name}' execution error: {m.inferential_stats.notes}\n")
                return 2
        if not report.metrics:
            sys.stderr.write("Strict failure: no metrics evaluated.\n")
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
