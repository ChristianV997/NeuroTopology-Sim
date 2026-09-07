"""Paired-cohort statistics and effect-size validation for NeuroTopology-Sim.

This package provides typed, verifiable within-subject paired statistics:
- Exact pair matching and deterministic subject sorting.
- Explicit non-silent exclusion records for unparseable/missing data.
- Paired Cohen's d_z = mean(diff) / std(diff, ddof=1).
- Non-parametric rank-biserial correlation r and Wilcoxon signed-rank test.
- Multiple hypothesis correction (Holm, Bonferroni, FDR-BH).
- Strict finite/null JSON serialization (never NaN/Inf).
- Cryptographic SHA-256 report checksumming.
"""
from __future__ import annotations

from .calculator import (
    calculate_paired_cohort_report,
    compute_descriptive_stats,
    compute_inferential_stats,
    compute_paired_difference_stats,
    compute_paired_effect_size_dz,
    compute_rank_biserial_r,
    compute_report_checksum,
)
from .models import (
    CohortStatisticsReport,
    DescriptiveStats,
    ExclusionRecord,
    HypothesisAlternative,
    InferentialStats,
    MetricCohortStats,
    MultiplicityMethod,
    PairedDifferenceStats,
    ProvenanceStatus,
)
from .multiplicity import adjust_p_values
from .serialization import (
    export_cohort_report_dict,
    load_cohort_input,
    load_cohort_report,
    save_cohort_report,
    verify_report_checksum,
)

__all__ = [
    "CohortStatisticsReport",
    "DescriptiveStats",
    "ExclusionRecord",
    "HypothesisAlternative",
    "InferentialStats",
    "MetricCohortStats",
    "MultiplicityMethod",
    "PairedDifferenceStats",
    "ProvenanceStatus",
    "adjust_p_values",
    "calculate_paired_cohort_report",
    "compute_descriptive_stats",
    "compute_inferential_stats",
    "compute_paired_difference_stats",
    "compute_paired_effect_size_dz",
    "compute_rank_biserial_r",
    "compute_report_checksum",
    "export_cohort_report_dict",
    "load_cohort_input",
    "load_cohort_report",
    "save_cohort_report",
    "verify_report_checksum",
]
