"""Unit and integration tests for paired-cohort descriptive and inferential statistics."""
from __future__ import annotations

import json
import math
from pathlib import Path
import pytest

from analysis.cohort_statistics import (
    CohortStatisticsReport,
    HypothesisAlternative,
    MultiplicityMethod,
    ProvenanceStatus,
    adjust_p_values,
    build_cohort_statistics_report,
    calculate_descriptive_moments,
    calculate_paired_differences,
    calculate_wilcoxon_test,
    evaluate_metric_cohort,
    export_report_csv,
    export_report_json,
)
from scripts.summarize_cohort_statistics import main


# 1. Valid paired data
def test_valid_paired_data() -> None:
    records = [
        {
            "subject": f"sub-0{i}",
            "condition_a_metrics": {"beta_1": 10.0 + i, "landscape_area": 5.0 + 0.5 * i, "winding": 1.0, "spatial_charge": 0.2},
            "condition_b_metrics": {"beta_1": 15.0 + 1.2 * i, "landscape_area": 8.0 + 0.8 * i, "winding": 2.0, "spatial_charge": 0.5},
        }
        for i in range(1, 6)
    ]

    report = build_cohort_statistics_report(
        records,
        condition_a_label="awake",
        condition_b_label="sed2",
        multiplicity_method=MultiplicityMethod.HOLM,
        min_pairs=2,
    )

    assert report.total_subjects_evaluated == 5
    assert set(report.metrics.keys()) == {"beta_1", "landscape_area", "winding", "spatial_charge"}

    b1 = report.metrics["beta_1"]
    assert b1.valid_pairs_count == 5
    assert b1.excluded_pairs_count == 0
    assert len(b1.exclusion_records) == 0

    # Moments
    assert b1.condition_a_stats.n == 5
    assert b1.condition_a_stats.mean == pytest.approx(13.0)
    assert b1.condition_b_stats.mean == pytest.approx(18.6)

    # Paired differences (cond_b - cond_a)
    assert b1.difference_stats.mean == pytest.approx(5.6)
    assert b1.difference_stats.cohens_d_z is not None
    assert b1.difference_stats.cohens_d_z > 0
    assert b1.difference_stats.ci_95 is not None
    assert b1.difference_stats.ci_95[0] < b1.difference_stats.ci_95[1]

    # Inferential stats
    assert b1.inferential_stats.status == "computed"
    assert b1.inferential_stats.statistic is not None
    assert b1.inferential_stats.p_value is not None
    assert b1.inferential_stats.p_adjusted is not None
    assert b1.inferential_stats.p_adjusted >= b1.inferential_stats.p_value


# 2. Insufficient pairs
def test_insufficient_pairs() -> None:
    records = [
        {
            "subject": "sub-01",
            "condition_a_metrics": {"beta_1": 12.0},
            "condition_b_metrics": {"beta_1": 15.0},
        }
    ]

    report = build_cohort_statistics_report(
        records,
        min_pairs=2,
    )

    b1 = report.metrics["beta_1"]
    assert b1.valid_pairs_count == 1
    assert b1.inferential_stats.status == "insufficient_pairs"
    assert b1.inferential_stats.statistic is None
    assert b1.inferential_stats.p_value is None
    assert b1.inferential_stats.p_adjusted is None
    assert "strictly below" in b1.inferential_stats.notes


# 3. Missing metrics are never silently dropped
def test_missing_metrics() -> None:
    records = [
        {"subject": "sub-01", "condition_a_metrics": {"beta_1": 10.0}, "condition_b_metrics": {"beta_1": 12.0}},
        {"subject": "sub-02", "condition_a_metrics": {"beta_1": 11.0}, "condition_b_metrics": {"beta_1": None}},
        {"subject": "sub-03", "condition_a_metrics": {"beta_1": None}, "condition_b_metrics": {"beta_1": 13.0}},
        {"subject": "sub-04", "condition_a_metrics": {}, "condition_b_metrics": {"beta_1": 14.0}},
    ]

    report = build_cohort_statistics_report(records, min_pairs=2)
    b1 = report.metrics["beta_1"]

    assert b1.valid_pairs_count == 1
    assert b1.excluded_pairs_count == 3
    excluded_subjects = {e.subject: e.reason for e in b1.exclusion_records}
    assert "sub-02" in excluded_subjects
    assert excluded_subjects["sub-02"] == "missing_condition_b_metric"
    assert "sub-03" in excluded_subjects
    assert excluded_subjects["sub-03"] == "missing_condition_a_metric"
    assert "sub-04" in excluded_subjects
    assert excluded_subjects["sub-04"] == "missing_condition_a_metric"


# 4. Non-finite values rejection
def test_non_finite_values_rejection() -> None:
    records = [
        {"subject": "sub-01", "condition_a_metrics": {"beta_1": 10.0}, "condition_b_metrics": {"beta_1": 12.0}},
        {"subject": "sub-02", "condition_a_metrics": {"beta_1": float("nan")}, "condition_b_metrics": {"beta_1": 14.0}},
        {"subject": "sub-03", "condition_a_metrics": {"beta_1": 11.0}, "condition_b_metrics": {"beta_1": float("inf")}},
        {"subject": "sub-04", "condition_a_metrics": {"beta_1": float("-inf")}, "condition_b_metrics": {"beta_1": 12.0}},
    ]

    report = build_cohort_statistics_report(records, min_pairs=2)
    b1 = report.metrics["beta_1"]

    assert b1.valid_pairs_count == 1
    assert b1.excluded_pairs_count == 3
    excluded_reasons = {e.subject: e.reason for e in b1.exclusion_records}
    assert "non_finite_metric_value" in excluded_reasons["sub-02"]
    assert "non_finite_metric_value" in excluded_reasons["sub-03"]
    assert "non_finite_metric_value" in excluded_reasons["sub-04"]


# 5. All-zero differences
def test_all_zero_differences() -> None:
    records = [
        {"subject": f"sub-0{i}", "condition_a_metrics": {"beta_1": 10.0}, "condition_b_metrics": {"beta_1": 10.0}}
        for i in range(1, 5)
    ]

    report = build_cohort_statistics_report(records, min_pairs=2)
    b1 = report.metrics["beta_1"]

    assert b1.valid_pairs_count == 4
    assert b1.difference_stats.mean == 0.0
    assert b1.difference_stats.median == 0.0
    assert b1.difference_stats.cohens_d_z == 0.0
    assert b1.inferential_stats.status == "all_paired_differences_zero"
    assert b1.inferential_stats.statistic == 0.0
    assert b1.inferential_stats.p_value == 1.0
    assert b1.inferential_stats.p_adjusted == 1.0
    assert b1.inferential_stats.zero_method == "wilcox"


# 6. Positive and negative paired effects
def test_positive_and_negative_paired_effects() -> None:
    # Positive effect: B > A systematically
    pos_pairs = [{"subject": f"s{i}", "condition_a": 10.0, "condition_b": 15.0 + i} for i in range(8)]
    pos_stats = evaluate_metric_cohort("pos_metric", pos_pairs, alternative="greater", min_pairs=2)
    assert pos_stats.difference_stats.mean > 0
    assert pos_stats.difference_stats.cohens_d_z > 1.0
    assert pos_stats.inferential_stats.status == "computed"
    assert pos_stats.inferential_stats.p_value < 0.01

    # Negative effect: B < A systematically
    neg_pairs = [{"subject": f"s{i}", "condition_a": 20.0 + i, "condition_b": 10.0} for i in range(8)]
    neg_stats = evaluate_metric_cohort("neg_metric", neg_pairs, alternative="less", min_pairs=2)
    assert neg_stats.difference_stats.mean < 0
    assert neg_stats.difference_stats.cohens_d_z < -1.0
    assert neg_stats.inferential_stats.status == "computed"
    assert neg_stats.inferential_stats.p_value < 0.01


# 7. Deterministic ordering
def test_deterministic_ordering() -> None:
    records_ordered = [
        {"subject": "sub-01", "condition_a_metrics": {"beta_1": 10.0}, "condition_b_metrics": {"beta_1": 12.0}},
        {"subject": "sub-02", "condition_a_metrics": {"beta_1": 11.0}, "condition_b_metrics": {"beta_1": 13.0}},
        {"subject": "sub-03", "condition_a_metrics": {"beta_1": 12.0}, "condition_b_metrics": {"beta_1": 14.0}},
    ]
    records_shuffled = [records_ordered[2], records_ordered[0], records_ordered[1]]

    rep1 = build_cohort_statistics_report(records_ordered)
    rep2 = build_cohort_statistics_report(records_shuffled)

    assert rep1.checksum == rep2.checksum
    assert export_report_json(rep1) == export_report_json(rep2)


# 8. Wilcoxon unavailable fallback
def test_wilcoxon_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    real_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if "scipy" in name:
            raise ImportError("Mock SciPy unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    res = calculate_wilcoxon_test([10.0, 11.0, 12.0], [12.0, 13.0, 14.0], min_pairs=2)
    assert res.status == "scipy_unavailable"
    assert res.statistic is None
    assert res.p_value is None
    assert "SciPy is unavailable" in res.notes


# 9. Multiplicity correction
def test_multiplicity_correction() -> None:
    p_vals = {"m1": 0.01, "m2": 0.04, "m3": 0.03}

    # Bonferroni: multiply by m=3
    bonf = adjust_p_values(p_vals, method="bonferroni")
    assert bonf["m1"] == pytest.approx(0.03)
    assert bonf["m2"] == pytest.approx(0.12)
    assert bonf["m3"] == pytest.approx(0.09)

    # Holm:
    # m1: 0.01 * 3 = 0.03
    # m3: max(0.03, 0.03 * 2) = 0.06
    # m2: max(0.06, 0.04 * 1) = 0.06
    holm = adjust_p_values(p_vals, method="holm")
    assert holm["m1"] == pytest.approx(0.03)
    assert holm["m3"] == pytest.approx(0.06)
    assert holm["m2"] == pytest.approx(0.06)

    # FDR_BH:
    # m1 (rank 1): 0.01 * 3 / 1 = 0.03
    # m3 (rank 2): 0.03 * 3 / 2 = 0.045
    # m2 (rank 3): 0.04 * 3 / 3 = 0.04
    # Step-up min: m2 = 0.04, m3 = min(0.04, 0.045) = 0.04, m1 = min(0.04, 0.03) = 0.03
    fdr = adjust_p_values(p_vals, method="fdr_bh")
    assert fdr["m1"] == pytest.approx(0.03)
    assert fdr["m3"] == pytest.approx(0.04)
    assert fdr["m2"] == pytest.approx(0.04)

    # None
    raw = adjust_p_values(p_vals, method="none")
    assert raw == p_vals


# 10. Synthetic-only input labeling
def test_synthetic_only_input_labeling() -> None:
    records = [
        {"subject": "sub-01", "condition_a_metrics": {"beta_1": 10.0}, "condition_b_metrics": {"beta_1": 12.0}},
        {"subject": "sub-02", "condition_a_metrics": {"beta_1": 11.0}, "condition_b_metrics": {"beta_1": 13.0}},
    ]
    report = build_cohort_statistics_report(
        records,
        is_synthetic=True,
        provenance_status=ProvenanceStatus.SYNTHETIC_FIXTURE,
    )
    assert report.is_synthetic is True
    assert report.provenance_status == "synthetic_fixture"


# 11. Empirical provenance incomplete
def test_empirical_provenance_incomplete() -> None:
    records = [
        {"subject": "sub-01", "condition_a_metrics": {"beta_1": 10.0}, "condition_b_metrics": {"beta_1": 12.0}},
    ]
    report = build_cohort_statistics_report(
        records,
        is_synthetic=False,
        provenance_status=ProvenanceStatus.INCOMPLETE,
    )
    assert report.is_synthetic is False
    assert report.provenance_status == "incomplete_provenance"


# 12. JSON finite and null compliance
def test_json_finite_null_compliance(tmp_path: Path) -> None:
    records = [
        {"subject": "sub-01", "condition_a_metrics": {"beta_1": 10.0}, "condition_b_metrics": {"beta_1": 12.0}},
    ]
    report = build_cohort_statistics_report(records, min_pairs=2)
    json_path = tmp_path / "out.json"
    json_str = export_report_json(report, json_path)

    parsed = json.loads(json_str)
    assert parsed["schema"] == "NeuroTopologySim.CohortStatisticsReport.v1"
    assert "NaN" not in json_str
    assert "Infinity" not in json_str
    # Inferential stats should be null
    assert parsed["metrics"]["beta_1"]["inferential_stats"]["statistic"] is None
    assert parsed["metrics"]["beta_1"]["inferential_stats"]["p_value"] is None


# 13. CLI execution
def test_cli_execution(tmp_path: Path) -> None:
    in_file = tmp_path / "cohort_metrics.json"
    out_file = tmp_path / "cohort_statistics.json"
    csv_file = tmp_path / "cohort_statistics.csv"

    sample_input = {
        "dataset_id": "ds005620",
        "condition_a": "awake",
        "condition_b": "sed2",
        "records": [
            {"subject": "sub-01", "condition_a_metrics": {"beta_1": 10.0, "winding": 1.0}, "condition_b_metrics": {"beta_1": 14.0, "winding": 2.0}},
            {"subject": "sub-02", "condition_a_metrics": {"beta_1": 12.0, "winding": 1.5}, "condition_b_metrics": {"beta_1": 16.0, "winding": 2.5}},
            {"subject": "sub-03", "condition_a_metrics": {"beta_1": 11.0, "winding": 1.2}, "condition_b_metrics": {"beta_1": 15.0, "winding": 2.2}},
        ],
    }
    in_file.write_text(json.dumps(sample_input), encoding="utf-8")

    cmd = [
        "--input", str(in_file),
        "--output", str(out_file),
        "--correction", "holm",
        "--csv-output", str(csv_file),
        "--strict",
    ]
    exit_code = main(cmd)
    assert exit_code == 0
    assert out_file.is_file()
    assert csv_file.is_file()

    out_data = json.loads(out_file.read_text(encoding="utf-8"))
    assert out_data["total_subjects_evaluated"] == 3
    assert "beta_1" in out_data["metrics"]
    assert "winding" in out_data["metrics"]
    assert out_data["metrics"]["beta_1"]["inferential_stats"]["status"] == "computed"
