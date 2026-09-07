#!/usr/bin/env python3
"""CLI utility to summarize paired-cohort statistics and effect sizes for NeuroTopology-Sim.

Guarantees:
- Deterministic subject pair matching.
- Explicit non-silent exclusion recording.
- Paired Cohen's d_z effect sizes and Wilcoxon signed-rank tests.
- Multiplicity corrections with explicit 'multiplicity_unavailable' state.
- Explicit non-evidence guardrails: formal_bayes_factor=null, scientific_pass=false.
- JSON output with strict finite/null guarantee and SHA-256 checksum.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add repo root to sys.path
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analysis.cohort_statistics import (
    calculate_paired_cohort_report,
    load_cohort_input,
    load_cohort_report,
    save_cohort_report,
    verify_report_checksum,
)
from analysis.cohort_statistics.models import (
    HypothesisAlternative,
    MultiplicityMethod,
    ProvenanceStatus,
)


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute and summarize paired-cohort statistics and effect sizes."
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to input cohort metrics JSON file.",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Path to output statistics report JSON file.",
    )
    parser.add_argument(
        "--condition-a", "-a",
        default="condition_a",
        help="Identifier/label for experimental condition A (preserved exactly as supplied).",
    )
    parser.add_argument(
        "--condition-b", "-b",
        default="condition_b",
        help="Identifier/label for reference condition B (preserved exactly as supplied).",
    )
    parser.add_argument(
        "--metrics", "-m",
        default=None,
        help="Comma-separated list of metrics to evaluate (default: all discovered).",
    )
    parser.add_argument(
        "--cohort-id", "--dataset-id", "-d",
        dest="cohort_id",
        default=None,
        help="Cohort or dataset identifier (e.g. ds005917, ds005620).",
    )
    parser.add_argument(
        "--pairing-key",
        default="subject_id",
        help="Key identifier used for subject pairing (default: subject_id).",
    )
    parser.add_argument(
        "--correction", "-c",
        choices=[m.value for m in MultiplicityMethod] + ["absent", "unavailable"],
        default=MultiplicityMethod.HOLM.value,
        help="Multiple testing correction method.",
    )
    parser.add_argument(
        "--alternative",
        choices=[a.value for a in HypothesisAlternative],
        default=HypothesisAlternative.TWO_SIDED.value,
        help="Alternative hypothesis directionality.",
    )
    parser.add_argument(
        "--min-pairs",
        type=int,
        default=3,
        help="Minimum required valid pairs for inferential testing.",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Explicitly mark dataset provenance as synthetic demo.",
    )
    parser.add_argument(
        "--provenance",
        choices=[p.value for p in ProvenanceStatus],
        default=ProvenanceStatus.EMPIRICAL.value,
        help="Explicit provenance status flag.",
    )
    parser.add_argument(
        "--verify-checksum",
        action="store_true",
        help="Verify the integrity checksum of an existing report JSON.",
    )
    return parser.parse_args(args)


def main(args: list[str] | None = None) -> int:
    ns = parse_args(args)

    if ns.verify_checksum:
        input_path = Path(ns.input)
        if not input_path.exists():
            print(f"Error: input file {input_path} not found.", file=sys.stderr)
            return 1
        import json
        data = json.loads(input_path.read_text(encoding="utf-8"))
        valid = verify_report_checksum(data)
        if valid:
            print(f"Checksum verified successfully: {data.get('checksum')}")
            return 0
        else:
            print(f"Checksum mismatch or missing in {input_path}.", file=sys.stderr)
            return 1

    input_data = load_cohort_input(ns.input)

    metrics_list = [m.strip() for m in ns.metrics.split(",")] if ns.metrics else None
    prov_status = (
        ProvenanceStatus.SYNTHETIC_DEMO.value
        if ns.synthetic
        else ns.provenance
    )

    report = calculate_paired_cohort_report(
        cohort_data=input_data,
        condition_a_name=ns.condition_a,
        condition_b_name=ns.condition_b,
        metrics=metrics_list,
        cohort_identifier=ns.cohort_id,
        pairing_key=ns.pairing_key,
        alternative=ns.alternative,
        multiplicity_method=ns.correction,
        min_pairs=ns.min_pairs,
        is_synthetic=ns.synthetic or prov_status == ProvenanceStatus.SYNTHETIC_DEMO.value,
        provenance_status=prov_status,
    )

    print("=" * 84)
    print(f"PAIRED COHORT STATISTICS REPORT (v2): {report.cohort_identifier or 'Unnamed Cohort'}")
    print(f"Contrast: {report.condition_a_label} - {report.condition_b_label}")
    print(f"Evaluated Subjects: {report.total_subjects_evaluated} | Included: {len(report.subjects_included)} | Excluded: {len(report.subjects_excluded)}")
    print(f"Effective Paired Sample Size: {report.effective_paired_sample_size}")
    print(f"Multiplicity Method: {report.multiplicity_method}")
    print(f"Evidence Class: {report.evidence_class} | Scientific Pass: {report.scientific_pass}")
    print(f"Formal Bayes Factor: {report.formal_bayes_factor} | Finite Status: {report.finite_value_status}")
    print(f"Report Checksum (SHA-256): {report.checksum}")
    print("=" * 84)
    print(f"{'Metric':<24} | {'N':<4} | {'Diff Mean':<10} | {'d_z':<8} | {'r':<8} | {'Ties':<5} | {'p (raw)':<9} | {'p (adj)':<9}")
    print("-" * 84)

    for m_name, m_stats in sorted(report.metrics.items()):
        d_mean = f"{m_stats.paired_differences.mean:.4f}" if m_stats.paired_differences.mean is not None else "N/A"
        dz = f"{m_stats.effect_size_estimates.cohens_dz:.3f}" if m_stats.effect_size_estimates.cohens_dz is not None else "N/A"
        rb = f"{m_stats.effect_size_estimates.rank_biserial_r:.3f}" if m_stats.effect_size_estimates.rank_biserial_r is not None else "N/A"
        ties = f"{m_stats.tie_count}"
        p_val = f"{m_stats.wilcoxon_p_value:.4f}" if m_stats.wilcoxon_p_value is not None else "N/A"
        p_adj = f"{m_stats.p_adjusted:.4f}" if m_stats.p_adjusted is not None else "N/A"

        print(f"{m_name:<24} | {m_stats.valid_pairs_count:<4} | {d_mean:<10} | {dz:<8} | {rb:<8} | {ties:<5} | {p_val:<9} | {p_adj:<9}")

        if m_stats.excluded_pairs_count > 0:
            print(f"  └─ Excluded {m_stats.excluded_pairs_count} pairs:")
            for excl in m_stats.exclusion_records[:5]:
                print(f"     • {excl.subject}: {excl.reason}")
            if len(m_stats.exclusion_records) > 5:
                print(f"     • ... and {len(m_stats.exclusion_records) - 5} more")

    print("-" * 84)
    for note in report.scientific_notes:
        print(f"[NOTE] {note}")
    print("=" * 84)

    if ns.output:
        out_p = save_cohort_report(report, ns.output)
        print(f"\nWrote full report artifact to: {out_p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
