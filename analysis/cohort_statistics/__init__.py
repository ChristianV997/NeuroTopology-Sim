"""Paired-cohort statistics and effect-size validation for NeuroTopology-Sim.

This package provides typed, verifiable within-subject paired statistics:
- Exact pair matching and deterministic subject sorting.
- Explicit non-silent exclusion records for unparseable/missing data.
- Paired Cohen's d_z = mean(diff) / std(diff, ddof=1) labeled as effect estimate.
- Non-parametric rank-biserial correlation r and Wilcoxon signed-rank test.
- Multiple hypothesis correction (Holm, Bonferroni, FDR-BH) and explicit 'multiplicity_unavailable' state.
- Strict finite/null JSON serialization (never NaN/Inf).
- Explicit non-evidence guardrails (formal_bayes_factor=null, scientific_pass=false).
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
    compute_ties_and_zeros,
)
from .models import (
    CohortStatisticsReport,
    ConfidenceInterval,
    DescriptiveStats,
    EffectSizeEstimates,
    ExclusionRecord,
    HypothesisAlternative,
    InferentialStats,
    MetricCohortStats,
    MultiplicityMethod,
    PairedDifferenceStats,
    ProvenanceStatus,
)
from .multiplicity import adjust_p_values, resolve_multiplicity
from .serialization import (
    export_cohort_report_dict,
    load_cohort_input,
    load_cohort_report,
    save_cohort_report,
    verify_report_checksum,
)

__all__ = [
    "CohortStatisticsReport",
    "ConfidenceInterval",
    "DescriptiveStats",
    "EffectSizeEstimates",
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
    "compute_ties_and_zeros",
    "export_cohort_report_dict",
    "load_cohort_input",
    "load_cohort_report",
    "resolve_multiplicity",
    "save_cohort_report",
    "verify_report_checksum",
]
