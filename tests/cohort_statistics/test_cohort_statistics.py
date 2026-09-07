"""Comprehensive unit and integration test suite for paired-cohort statistics.

Validates:
1. Exact Cohen's d_z and rank-biserial effect sizes.
2. Non-parametric Wilcoxon signed-rank and zero-difference edge cases.
3. SciPy absence graceful fallback (status='unavailable', null values).
4. Insufficient pair threshold enforcement.
5. Non-silent exclusion tracking for missing/corrupted arms or non-finite inputs.
6. Multiplicity corrections (Holm, Bonferroni, FDR-BH) with None preservation.
7. Deterministic pair sorting and cryptographic SHA-256 checksum integrity.
8. Strict RFC-8259 JSON serialization (no NaN/Inf).
9. Provenance status tagging and scientific guardrails.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from analysis.cohort_statistics import (
    CohortStatisticsReport,
    DescriptiveStats,
    ExclusionRecord,
    HypothesisAlternative,
    InferentialStats,
    MetricCohortStats,
    MultiplicityMethod,
    PairedDifferenceStats,
    ProvenanceStatus,
    adjust_p_values,
    calculate_paired_cohort_report,
    compute_descriptive_stats,
    compute_inferential_stats,
    compute_paired_difference_stats,
    compute_paired_effect_size_dz,
    compute_rank_biserial_r,
    compute_report_checksum,
    export_cohort_report_dict,
    load_cohort_input,
    load_cohort_report,
    save_cohort_report,
    verify_report_checksum,
)
from scripts.summarize_cohort_statistics import main as cli_main


def test_compute_descriptive_stats():
    # Empty
    d0 = compute_descriptive_stats([])
    assert d0.n == 0
    assert d0.mean is None
    assert d0.median is None
    assert d0.variance is None
    assert d0.standard_error is None

    # Single element
    d1 = compute_descriptive_stats([42.0])
    assert d1.n == 1
    assert d1.mean == 42.0
    assert d1.median == 42.0
    assert d1.variance is None
    assert d1.standard_error is None

    # Multiple elements
    vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    dm = compute_descriptive_stats(vals)
    assert dm.n == 8
    assert dm.mean == 5.0
    assert dm.median == 4.5
    assert dm.variance == pytest.approx(4.571428, rel=1e-4)
    assert dm.standard_error == pytest.approx(math.sqrt(4.571428 / 8), rel=1e-4)


def test_paired_cohens_dz_calculations():
    # Zero difference
    diff_zero = [1.0, -1.0, 2.0, -2.0]
    dz_zero = compute_paired_effect_size_dz(diff_zero)
    assert dz_zero is not None
    assert abs(dz_zero) < 1e-9

    # Consistently positive
    diff_pos = [1.0, 1.2, 0.9, 1.1]
    dz_pos = compute_paired_effect_size_dz(diff_pos)
    assert dz_pos is not None
    assert dz_pos > 3.0  # Large d_z

    # Consistently negative
    diff_neg = [-2.0, -2.5, -2.2, -2.1]
    dz_neg = compute_paired_effect_size_dz(diff_neg)
    assert dz_neg is not None
    assert dz_neg < -3.0

    # Insufficient elements
    assert compute_paired_effect_size_dz([]) is None
    assert compute_paired_effect_size_dz([5.0]) is None

    # All identical non-zero differences (variance = 0)
    assert compute_paired_effect_size_dz([5.0, 5.0, 5.0]) is None
    # All zero differences (variance = 0, mean = 0)
    assert compute_paired_effect_size_dz([0.0, 0.0, 0.0]) == 0.0


def test_rank_biserial_r():
    # All positive differences -> r = +1.0
    diff_pos = [2.0, 5.0, 1.2, 0.8]
    assert compute_rank_biserial_r(diff_pos) == 1.0

    # All negative differences -> r = -1.0
    diff_neg = [-1.0, -3.0, -0.5]
    assert compute_rank_biserial_r(diff_neg) == -1.0

    # Symmetric around zero -> r = 0.0
    diff_sym = [-2.0, -1.0, 1.0, 2.0]
    assert compute_rank_biserial_r(diff_sym) == 0.0

    # All zero differences -> r = 0.0
    diff_zero = [0.0, 0.0, 0.0]
    assert compute_rank_biserial_r(diff_zero) == 0.0


def test_wilcoxon_signed_rank_and_zero_handling():
    # When all differences are zero
    zeros = [0.0, 0.0, 0.0, 0.0]
    inf_zero = compute_inferential_stats(zeros, min_pairs=3)
    assert inf_zero.status == "available"
    assert inf_zero.statistic == 0.0
    assert inf_zero.p_value == 1.0
    assert inf_zero.zero_count == 4

    # When differences are distinct
    diffs = [1.2, 2.3, 3.1, 0.8, 1.9]
    inf_valid = compute_inferential_stats(diffs, min_pairs=3)
    assert inf_valid.status == "available"
    assert inf_valid.statistic is not None
    assert inf_valid.p_value is not None
    assert 0.0 <= inf_valid.p_value <= 1.0


def test_scipy_unavailable_fallback(monkeypatch):
    import analysis.cohort_statistics.calculator as calc_mod

    # Simulate environment where scipy is missing
    monkeypatch.setattr(calc_mod, "sp_stats", None)

    diffs = [1.0, 2.0, 3.0, 4.0]
    inf = calc_mod.compute_inferential_stats(diffs, min_pairs=3)
    assert inf.status == "unavailable"
    assert inf.statistic is None
    assert inf.p_value is None
    assert "SciPy unavailable" in inf.notes


def test_insufficient_pairs():
    # Only 2 pairs when min_pairs=3
    diffs = [1.0, 2.0]
    inf = compute_inferential_stats(diffs, min_pairs=3)
    assert inf.status == "insufficient_pairs"
    assert inf.statistic is None
    assert inf.p_value is None
    assert "below minimum threshold" in inf.notes


def test_non_silent_exclusion_tracking():
    cohort = {
        "sub-01": {
            "drug": {"betti1": 10.0, "error": ""},
            "placebo": {"betti1": 5.0, "error": ""},
        },
        "sub-02": {  # Missing placebo condition
            "drug": {"betti1": 12.0, "error": ""},
        },
        "sub-03": {  # Error in drug condition
            "drug": {"betti1": 0.0, "error": "scanner_artifact"},
            "placebo": {"betti1": 4.0, "error": ""},
        },
        "sub-04": {  # Non-finite value in drug
            "drug": {"betti1": float("nan"), "error": ""},
            "placebo": {"betti1": 6.0, "error": ""},
        },
        "sub-05": {  # Unparseable value
            "drug": {"betti1": "corrupt_data", "error": ""},
            "placebo": {"betti1": 3.0, "error": ""},
        },
        "sub-06": {  # Clean pair
            "drug": {"betti1": 11.0, "error": ""},
            "placebo": {"betti1": 7.0, "error": ""},
        },
        "sub-07": {  # Clean pair
            "drug": {"betti1": 9.0, "error": ""},
            "placebo": {"betti1": 4.0, "error": ""},
        },
    }

    report = calculate_paired_cohort_report(
        cohort_data=cohort,
        condition_a_name="drug",
        condition_b_name="placebo",
        metrics=["betti1"],
    )

    betti1 = report.metrics["betti1"]
    assert betti1.valid_pairs_count == 3  # sub-01, sub-06, sub-07
    assert betti1.excluded_pairs_count == 4  # sub-02, sub-03, sub-04, sub-05

    excluded_subjects = {e.subject: e.reason for e in betti1.exclusion_records}
    assert "sub-02" in excluded_subjects
    assert "missing_placebo" in excluded_subjects["sub-02"]
    assert "sub-03" in excluded_subjects
    assert "drug_error" in excluded_subjects["sub-03"]
    assert "sub-04" in excluded_subjects
    assert "non_finite" in excluded_subjects["sub-04"]
    assert "sub-05" in excluded_subjects
    assert "unparseable" in excluded_subjects["sub-05"]


def test_multiplicity_corrections():
    # Test Holm, Bonferroni, FDR-BH
    p_raw = [0.01, None, 0.04, 0.02, 0.05]

    # Holm
    adj_holm = adjust_p_values(p_raw, method=MultiplicityMethod.HOLM)
    assert len(adj_holm) == 5
    assert adj_holm[1] is None  # Preserves None at original index

    # Valid values adjusted: 4 tests (0.01, 0.02, 0.04, 0.05)
    # Sorted: p(1)=0.01 * 4 = 0.04
    #         p(2)=0.02 * 3 = 0.06
    #         p(3)=0.04 * 2 = 0.08
    #         p(4)=0.05 * 1 = 0.05 -> maxed to 0.08
    assert adj_holm[0] == pytest.approx(0.04)
    assert adj_holm[3] == pytest.approx(0.06)
    assert adj_holm[2] == pytest.approx(0.08)
    assert adj_holm[4] == pytest.approx(0.08)

    # Bonferroni
    adj_bonf = adjust_p_values(p_raw, method=MultiplicityMethod.BONFERRONI)
    assert adj_bonf[1] is None
    assert adj_bonf[0] == pytest.approx(0.04)  # 0.01 * 4
    assert adj_bonf[3] == pytest.approx(0.08)  # 0.02 * 4

    # FDR-BH
    adj_bh = adjust_p_values(p_raw, method=MultiplicityMethod.FDR_BH)
    assert adj_bh[1] is None
    for p in adj_bh:
        if p is not None:
            assert 0.0 <= p <= 1.0


def test_deterministic_ordering_and_checksum():
    cohort_order_1 = {
        "sub-B": {"drug": {"m1": 10.0}, "placebo": {"m1": 5.0}},
        "sub-A": {"drug": {"m1": 12.0}, "placebo": {"m1": 6.0}},
        "sub-C": {"drug": {"m1": 8.0}, "placebo": {"m1": 4.0}},
    }
    cohort_order_2 = {
        "sub-A": {"drug": {"m1": 12.0}, "placebo": {"m1": 6.0}},
        "sub-C": {"drug": {"m1": 8.0}, "placebo": {"m1": 4.0}},
        "sub-B": {"drug": {"m1": 10.0}, "placebo": {"m1": 5.0}},
    }

    report1 = calculate_paired_cohort_report(cohort_order_1, condition_a_name="drug", condition_b_name="placebo")
    report2 = calculate_paired_cohort_report(cohort_order_2, condition_a_name="drug", condition_b_name="placebo")

    # Hashes and structure must be strictly identical regardless of dictionary insertion order
    assert report1.checksum == report2.checksum
    assert len(report1.checksum) == 64

    # Verify checksum validator
    dict1 = export_cohort_report_dict(report1)
    assert verify_report_checksum(dict1) is True

    # Tamper test
    dict1["dataset_id"] = "tampered_dataset_id"
    assert verify_report_checksum(dict1) is False


def test_rfc8259_strict_json_finite_null_compliance(tmp_path):
    cohort = {
        "sub-01": {"cond_a": {"m1": 10.0}, "cond_b": {"m1": 5.0}},
        "sub-02": {"cond_a": {"m1": 12.0}, "cond_b": {"m1": 6.0}},
        "sub-03": {"cond_a": {"m1": 8.0}, "cond_b": {"m1": 4.0}},
    }
    report = calculate_paired_cohort_report(cohort, condition_a_name="cond_a", condition_b_name="cond_b")

    out_file = tmp_path / "report.json"
    save_cohort_report(report, out_file)

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")

    # Strict check: standard JSON parser must not have NaN or Infinity
    # json.loads rejects NaN when parse_constant fails or we inspect tokens
    assert "NaN" not in content
    assert "Infinity" not in content

    # Re-hydrate report
    loaded_report = load_cohort_report(out_file)
    assert loaded_report.checksum == report.checksum
    assert len(loaded_report.metrics) == 1


def test_synthetic_provenance_marking():
    cohort = {
        "sub-01": {"cond_a": {"m1": 10.0}, "cond_b": {"m1": 5.0}},
        "sub-02": {"cond_a": {"m1": 12.0}, "cond_b": {"m1": 6.0}},
        "sub-03": {"cond_a": {"m1": 8.0}, "cond_b": {"m1": 4.0}},
    }
    report = calculate_paired_cohort_report(
        cohort,
        condition_a_name="cond_a",
        condition_b_name="cond_b",
        is_synthetic=True,
        provenance_status=ProvenanceStatus.SYNTHETIC_DEMO,
    )
    assert report.is_synthetic is True
    assert report.provenance_status == "synthetic_demo"

    # Verify guardrail note
    assert any("GUARDRAIL" in note for note in report.scientific_notes)


def test_cli_smoke(tmp_path, capsys):
    cohort_data = {
        "sub-01": {"drug": {"betti1": 10.0, "total_persistence": 2.5}, "placebo": {"betti1": 5.0, "total_persistence": 1.5}},
        "sub-02": {"drug": {"betti1": 12.0, "total_persistence": 2.8}, "placebo": {"betti1": 6.0, "total_persistence": 1.7}},
        "sub-03": {"drug": {"betti1": 8.0, "total_persistence": 2.1}, "placebo": {"betti1": 4.0, "total_persistence": 1.2}},
    }
    in_file = tmp_path / "cohort_input.json"
    in_file.write_text(json.dumps(cohort_data), encoding="utf-8")

    out_file = tmp_path / "cohort_report.json"

    # Test CLI execution
    exit_code = cli_main([
        "--input", str(in_file),
        "--output", str(out_file),
        "--condition-a", "drug",
        "--condition-b", "placebo",
        "--dataset-id", "ds-test",
        "--correction", "holm",
    ])
    assert exit_code == 0
    assert out_file.exists()

    captured = capsys.readouterr()
    assert "PAIRED COHORT STATISTICS REPORT" in captured.out
    assert "betti1" in captured.out
    assert "total_persistence" in captured.out

    # Test checksum verification via CLI
    verify_exit_code = cli_main([
        "--input", str(out_file),
        "--verify-checksum",
    ])
    assert verify_exit_code == 0
