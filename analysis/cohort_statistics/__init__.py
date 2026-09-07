"""Paired-cohort descriptive and non-parametric statistics layer for NeuroTopology-Sim."""
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
from .calculator import (
    calculate_descriptive_moments,
    calculate_paired_differences,
    calculate_wilcoxon_test,
    evaluate_metric_cohort,
)
from .multiplicity import adjust_p_values
from .serialization import (
    build_cohort_statistics_report,
    compute_report_checksum,
    export_report_csv,
    export_report_json,
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
    "calculate_descriptive_moments",
    "calculate_paired_differences",
    "calculate_wilcoxon_test",
    "evaluate_metric_cohort",
    "adjust_p_values",
    "build_cohort_statistics_report",
    "compute_report_checksum",
    "export_report_csv",
    "export_report_json",
]
