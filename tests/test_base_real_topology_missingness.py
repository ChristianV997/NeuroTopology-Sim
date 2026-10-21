"""Unit and integration tests for Level T missingness tracking and zero-imputation prevention.

Verifies:
1. Missing source files return explicit missing rows with is_valid=False and None metrics.
2. Missing companion files (e.g. BrainVision .vmrk/.eeg) are detected as missing_companion_file.
3. Failed signal reads return failed_read and do not manufacture zero-valued evidence.
4. Genuine zero observations (q_net = 0.0) are preserved as valid computed telemetry.
5. Missing metadata fields (session_id, run_id, task_label) remain None, not "0" or "none".
6. build_topology_quality_report excludes missing rows and reports skip rates.
7. build_artifact_alignment_report does not crash on None and does not impute zeros.
8. build_group_significance_report excludes missing rows and enforces skip rate thresholds.
9. write_level_t_topology_outputs serializes None as empty string in CSV (never 0.0).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import numpy as np
import pytest

from sciencer_d.btc_icft.level_t.base_real_topology import (
    LevelTRealTopologyResult,
    LevelTRealTopologyRow,
    audit_cohort_missingness,
    build_artifact_alignment_report,
    build_group_significance_report,
    build_level_t_omega_event,
    build_ml_decoding_report,
    build_topology_quality_report,
    compute_real_topology_for_window,
    write_level_t_topology_outputs,
)


def _valid_row(
    index: int,
    subject_id: str = "sub-01",
    task_label: str = "rest",
    q_net: float = 0.1,
    q_abs: float = 0.25,
    topology_quality: float = 0.9,
) -> LevelTRealTopologyRow:
    return LevelTRealTopologyRow(
        row_id=f"row-{index}",
        subject_id=subject_id,
        session_id="ses-01",
        run_id="run-01",
        window_id=f"win-{index}",
        task_label=task_label,
        q_net=q_net,
        q_abs=q_abs,
        f_dress=0.05,
        defect_density=0.02,
        n_triangles=12,
        n_valid_triangles=11,
        topology_quality=topology_quality,
        null_method="real_none",
        null_seed=index,
        source_file="/data/sub-01_task-rest.edf",
        window_start_s=float(index * 2),
        window_end_s=float((index + 1) * 2),
        warnings=[],
        topology_status="computed",
        missingness_state="computed",
        missingness_reason=None,
        is_valid=True,
        run_status="complete",
        replicate_count=1,
    )


def _missing_row(
    index: int,
    subject_id: str = "sub-01",
    task_label: str | None = None,
    state: str = "missing_source_file",
    reason: str = "source file not found",
) -> LevelTRealTopologyRow:
    return LevelTRealTopologyRow(
        row_id=f"row-{index}",
        subject_id=subject_id,
        session_id=None,
        run_id=None,
        window_id=f"win-{index}",
        task_label=task_label,
        q_net=None,
        q_abs=None,
        f_dress=None,
        defect_density=None,
        n_triangles=0,
        n_valid_triangles=0,
        topology_quality=None,
        null_method="real_none",
        null_seed=0,
        source_file="missing.edf",
        window_start_s=float(index * 2),
        window_end_s=float((index + 1) * 2),
        warnings=[reason],
        topology_status="skipped",
        missingness_state=state,
        missingness_reason=reason,
        is_valid=False,
        run_status="failed",
        replicate_count=0,
    )


# ---------------------------------------------------------------------------
# 1. Missing source file yields fail-closed missing row
# ---------------------------------------------------------------------------

def test_missing_source_file_yields_fail_closed_missing_row():
    m_row = {
        "row_id": "r100",
        "subject_id": "sub-01",
        "session_id": "",
        "run_id": "",
        "window_id": "w0",
        "task_label": "task_a",
        "source_file": "/nonexistent/path/signal.edf",
        "window_start_s": "0.0",
        "window_end_s": "2.0",
    }
    row = compute_real_topology_for_window(m_row)

    assert row.is_valid is False
    assert row.topology_status == "skipped"
    assert row.missingness_state == "missing_source_file"
    assert row.missingness_reason is not None
    assert "source file not found" in row.missingness_reason
    assert row.q_net is None
    assert row.q_abs is None
    assert row.f_dress is None
    assert row.defect_density is None
    assert row.topology_quality is None
    assert row.replicate_count == 0
    assert row.run_status == "failed"
    assert row.session_id is None
    assert row.run_id is None


# ---------------------------------------------------------------------------
# 2. Missing companion file detected and not imputed as zero
# ---------------------------------------------------------------------------

def test_missing_companion_file_detected_and_not_imputed_as_zero(tmp_path, monkeypatch):
    vhdr_file = tmp_path / "sub-02_task-rest.vhdr"
    vhdr_file.write_text("BrainVision header stub", encoding="utf-8")

    def _mock_read(*args, **kwargs):
        raise FileNotFoundError("BrainVision companion file missing: sub-02_task-rest.vmrk")

    monkeypatch.setattr("data.bids_ingest.read_window_signal", _mock_read)

    m_row = {
        "row_id": "r200",
        "subject_id": "sub-02",
        "window_id": "w0",
        "task_label": "rest",
        "source_file": str(vhdr_file),
        "window_start_s": "0.0",
        "window_end_s": "2.0",
    }
    row = compute_real_topology_for_window(m_row)

    assert row.is_valid is False
    assert row.topology_status == "skipped"
    assert row.missingness_state == "missing_companion_file"
    assert "companion file missing" in row.missingness_reason
    assert row.q_net is None
    assert row.q_abs is None
    assert row.topology_quality is None
    assert row.replicate_count == 0


# ---------------------------------------------------------------------------
# 3. Failed signal read does not manufacture zero-valued evidence
# ---------------------------------------------------------------------------

def test_failed_read_exception_does_not_impute_zeros(tmp_path, monkeypatch):
    edf_file = tmp_path / "corrupt.edf"
    edf_file.write_bytes(b"\x00\x01\x02")

    def _mock_read(*args, **kwargs):
        raise ValueError("Invalid header: sample rate must be positive, got 0")

    monkeypatch.setattr("data.bids_ingest.read_window_signal", _mock_read)

    m_row = {
        "row_id": "r300",
        "subject_id": "sub-03",
        "window_id": "w0",
        "task_label": "task_b",
        "source_file": str(edf_file),
        "window_start_s": "0.0",
        "window_end_s": "2.0",
    }
    row = compute_real_topology_for_window(m_row)

    assert row.is_valid is False
    assert row.topology_status == "skipped"
    assert row.missingness_state == "failed_read"
    assert row.q_net is None
    assert row.q_abs is None
    assert row.topology_quality is None


# ---------------------------------------------------------------------------
# 4. Empty channels array returns failed_read
# ---------------------------------------------------------------------------

def test_empty_channels_returns_failed_read(tmp_path, monkeypatch):
    sig_file = tmp_path / "empty.edf"
    sig_file.write_bytes(b"empty")

    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: np.array([]))

    m_row = {
        "row_id": "r400",
        "subject_id": "sub-04",
        "window_id": "w0",
        "task_label": "task_c",
        "source_file": str(sig_file),
        "window_start_s": "0.0",
        "window_end_s": "2.0",
    }
    row = compute_real_topology_for_window(m_row)

    assert row.is_valid is False
    assert row.missingness_state == "failed_read"
    assert row.q_net is None


# ---------------------------------------------------------------------------
# 5. Genuine zero observation (q_net = 0.0) is preserved as valid computed row
# ---------------------------------------------------------------------------

def test_real_zero_valued_observation_distinguished_from_missing():
    # A genuine physical measurement where topological charge cancels out
    row = _valid_row(1, q_net=0.0, q_abs=1.5, topology_quality=0.85)

    assert row.is_valid is True
    assert row.topology_status == "computed"
    assert row.missingness_state == "computed"
    assert row.q_net == 0.0  # genuine zero observation
    assert row.q_abs == 1.5
    assert row.replicate_count == 1
    assert row.missingness_reason is None

    # Compare with a missing row
    m_row = _missing_row(2, state="missing_source_file")
    assert m_row.is_valid is False
    assert m_row.topology_status == "skipped"
    assert m_row.q_net is None  # NOT 0.0!
    assert m_row.q_abs is None  # NOT 0.0!
    assert m_row.replicate_count == 0


# ---------------------------------------------------------------------------
# 6. Null metadata fields remain None, not string "0" or "none"
# ---------------------------------------------------------------------------

def test_missing_metadata_preserves_none():
    row = _missing_row(1, task_label=None)
    assert row.session_id is None
    assert row.run_id is None
    assert row.task_label is None
    assert row.session_id != "0"
    assert row.session_id != "none"
    assert row.run_id != "0"
    assert row.task_label != "0"


# ---------------------------------------------------------------------------
# 7. build_topology_quality_report excludes missing rows and computes skip rate
# ---------------------------------------------------------------------------

def test_build_topology_quality_report_excludes_missing_rows():
    # 3 valid rows (quality 0.8, 0.9, 1.0) and 2 missing rows (quality None)
    rows = [
        _valid_row(0, topology_quality=0.8),
        _valid_row(1, topology_quality=0.9),
        _valid_row(2, topology_quality=1.0),
        _missing_row(3),
        _missing_row(4),
    ]
    report = build_topology_quality_report(rows)

    assert report["n_rows"] == 5
    assert report["n_valid_rows"] == 3
    assert report["n_missing_rows"] == 2
    assert report["skip_rate"] == 0.4
    assert report["status"] == "blocked_high_skip_rate"  # 40% > 20%
    assert report["quality_passed"] is False

    # mean quality must be exactly 0.9, NOT diluted by 0.0!
    expected_mean = (0.8 + 0.9 + 1.0) / 3.0
    assert abs(report["mean_topology_quality"] - expected_mean) < 1e-6
    assert report["min_topology_quality"] == 0.8
    assert report["max_topology_quality"] == 1.0
    assert "row-3" in report["missing_row_ids"]
    assert "row-4" in report["missing_row_ids"]


def test_build_topology_quality_report_all_missing():
    rows = [_missing_row(0), _missing_row(1)]
    report = build_topology_quality_report(rows)

    assert report["n_valid_rows"] == 0
    assert report["n_missing_rows"] == 2
    assert report["mean_topology_quality"] is None
    assert report["quality_passed"] is False
    assert report["status"] == "blocked_high_skip_rate"


# ---------------------------------------------------------------------------
# 8. build_artifact_alignment_report handles None without crash or zero-fill
# ---------------------------------------------------------------------------

def test_build_artifact_alignment_report_handles_missing_values():
    rows = [
        _valid_row(0, topology_quality=0.9),
        _missing_row(1),
    ]
    m_rows = [
        {"row_id": "row-0", "artifact_score": "0.15"},
        {"row_id": "row-1", "artifact_score": ""},  # missing artifact score
    ]
    report = build_artifact_alignment_report(rows, m_rows)

    assert report["n_rows"] == 2
    assert report["n_missing_artifact_scores"] == 1
    assert abs(report["mean_artifact_score"] - 0.15) < 1e-6
    assert abs(report["topology_quality_mean"] - 0.9) < 1e-6
    assert "row-1" in report["missing_topology_rows"]
    assert report["artifact_alignment_warning"] == "artifact scores partially missing"


# ---------------------------------------------------------------------------
# 9. build_group_significance_report excludes missing rows and enforces skip rate
# ---------------------------------------------------------------------------

def test_build_group_significance_report_enforces_max_skip_rate():
    # 8 valid rows, 4 missing rows -> skip rate = 4/12 = 33.3% > 20%
    rows = [_valid_row(i, subject_id=f"sub-{i}", task_label="a" if i < 4 else "b") for i in range(8)]
    rows += [_missing_row(i, subject_id=f"sub-{i}", task_label="a") for i in range(8, 12)]

    m_rows = [{"row_id": r.row_id, "state_label": r.task_label or "a"} for r in rows]

    report = build_group_significance_report(
        rows, m_rows, max_skip_rate=0.20, n_permutations=100, seed=42
    )

    assert report["status"] == "blocked_high_skip_rate"
    assert report["skip_rate"] > 0.20
    assert report["n_rows_total"] == 12
    assert report["n_rows_eligible"] == 8


def test_build_group_significance_report_computes_precision_metrics():
    pytest.importorskip("pandas")
    # 10 rows in group a, 10 in group b, all valid
    rng = np.random.default_rng(0)
    rows = []
    m_rows = []
    for i in range(20):
        group = "expert" if i < 10 else "novice"
        q_val = float(rng.normal(0.2, 0.02) if group == "expert" else rng.normal(0.4, 0.02))
        r = _valid_row(i, subject_id=f"sub-{i}", task_label=group, q_abs=q_val)
        rows.append(r)
        m_rows.append({"row_id": r.row_id, "state_label": group})

    report = build_group_significance_report(rows, m_rows, n_permutations=200, seed=0)

    assert report["status"] == "computed"
    q_abs_m = report["metrics"]["q_abs"]
    assert "mean_a" in q_abs_m
    assert "mean_b" in q_abs_m
    assert "sem_a" in q_abs_m
    assert "sem_b" in q_abs_m
    assert "ci_95_a" in q_abs_m
    assert "ci_95_b" in q_abs_m
    assert q_abs_m["ci_95_a"][0] < q_abs_m["mean_a"] < q_abs_m["ci_95_a"][1]
    assert q_abs_m["ci_95_b"][0] < q_abs_m["mean_b"] < q_abs_m["ci_95_b"][1]


def test_build_group_significance_report_missing_dependency_fails_gracefully(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pandas":
            raise ImportError("No module named 'pandas'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    rows = [_valid_row(i, subject_id=f"sub-{i}", task_label="expert" if i < 5 else "novice") for i in range(10)]
    m_rows = [{"row_id": r.row_id, "state_label": r.task_label} for r in rows]
    report = build_group_significance_report(rows, m_rows, n_permutations=50, seed=0)
    assert report["status"] == "dependency_missing"
    assert "required for permutation testing" in report["reason"]


# ---------------------------------------------------------------------------
# 10. write_level_t_topology_outputs serializes empty strings for None
# ---------------------------------------------------------------------------

def test_write_level_t_topology_outputs_serializes_empty_string_for_none(tmp_path):
    out_dir = tmp_path / "topo_out"
    rows = [
        _valid_row(0, q_net=0.05, q_abs=0.25),
        _missing_row(1),
    ]
    q_rep = build_topology_quality_report(rows)
    null_rep = {"status": "placeholder_only", "real_nulls_performed": False}
    art_rep = {"n_rows": 2}
    omega = build_level_t_omega_event(rows, "ds005620")
    res = LevelTRealTopologyResult(
        dataset_id="ds005620",
        n_rows=2,
        n_subjects=1,
        n_windows=2,
        topology_quality_report=q_rep,
        null_placeholder_report=null_rep,
        artifact_alignment_report=art_rep,
        omega_event=omega,
        safe_claim="Safe telemetry claim.",
        forbidden_claims=[],
        warnings=[],
    )

    cohort_audit = {
        "verdict": "INCOMPLETE",
        "gate_passed": False,
        "skip_rate": 0.5,
        "n_valid_windows": 1,
        "n_missing_windows": 1,
        "n_paired_subjects": 0,
        "verdict_reason": "1 missing window",
    }

    out_paths = write_level_t_topology_outputs(
        res, str(out_dir), rows, "ds005620", cohort_missingness_report=cohort_audit
    )

    csv_path = Path(out_paths["features_t.csv"])
    assert csv_path.exists()

    with csv_path.open("r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    assert len(reader) == 2
    # Valid row has numerical strings
    assert reader[0]["q_net"] == "0.05"
    assert reader[0]["is_valid"] == "True"

    # Missing row MUST have empty string, NEVER "0.0" or "None"
    assert reader[1]["q_net"] == ""
    assert reader[1]["q_abs"] == ""
    assert reader[1]["topology_quality"] == ""
    assert reader[1]["session_id"] == ""
    assert reader[1]["run_id"] == ""
    assert reader[1]["is_valid"] == "False"
    assert reader[1]["topology_status"] == "skipped"

    # Verify cohort_missingness_report.json was written
    audit_json = Path(out_paths["cohort_missingness_report.json"])
    assert audit_json.exists()
    audit_data = json.loads(audit_json.read_text(encoding="utf-8"))
    assert audit_data["verdict"] == "INCOMPLETE"

    # Verify report.md has the cohort audit section
    report_md = Path(out_paths["report.md"]).read_text(encoding="utf-8")
    assert "Cohort missingness audit report" in report_md
    assert "verdict: INCOMPLETE" in report_md


# ---------------------------------------------------------------------------
# 11. Partial run (prematurely terminated window) yields partial_run state
# ---------------------------------------------------------------------------

def test_partial_run_out_of_range_window_classified_as_partial_run(tmp_path, monkeypatch):
    edf_file = tmp_path / "truncated_sub-01.edf"
    edf_file.write_bytes(b"header")

    def _mock_read(*args, **kwargs):
        raise ValueError(
            "window [4.0,6.0]s out of range for truncated_sub-01.edf (duration 4.85s)"
        )

    monkeypatch.setattr("data.bids_ingest.read_window_signal", _mock_read)

    m_row = {
        "row_id": "r_part_1",
        "subject_id": "sub-01",
        "window_id": "w2",
        "task_label": "rest",
        "source_file": str(edf_file),
        "window_start_s": "4.0",
        "window_end_s": "6.0",
    }
    row = compute_real_topology_for_window(m_row)

    assert row.is_valid is False
    assert row.topology_status == "skipped"
    assert row.missingness_state == "partial_run"
    assert row.run_status == "partial"
    assert row.q_net is None
    assert row.q_abs is None
    assert row.f_dress is None
    assert row.defect_density is None
    assert row.topology_quality is None
    assert row.replicate_count == 0


def test_nonfinite_channel_samples_yield_failed_read_not_zeros(tmp_path, monkeypatch):
    edf_file = tmp_path / "nan_signal.edf"
    edf_file.write_bytes(b"header")

    def _mock_read(*args, **kwargs):
        arr = np.ones((4, 100), dtype=float)
        arr[1, 10] = float("nan")
        return arr

    monkeypatch.setattr("data.bids_ingest.read_window_signal", _mock_read)

    m_row = {
        "row_id": "r_nan_1",
        "subject_id": "sub-01",
        "window_id": "w0",
        "task_label": "rest",
        "source_file": str(edf_file),
        "window_start_s": "0.0",
        "window_end_s": "2.0",
    }
    row = compute_real_topology_for_window(m_row)

    assert row.is_valid is False
    assert row.topology_status == "skipped"
    assert row.missingness_state == "failed_read"
    assert row.q_net is None
    assert row.q_abs is None
    assert row.topology_quality is None


# ---------------------------------------------------------------------------
# 12. Any None or non-finite metric demotes row to invalid/unobserved
# ---------------------------------------------------------------------------

def test_row_with_any_none_or_nonfinite_metric_demotes_to_unobserved():
    # q_net is None while q_abs and topology_quality are finite
    row_partial_none = LevelTRealTopologyRow(
        row_id="r_none_qnet",
        subject_id="sub-01",
        session_id="ses-01",
        run_id="run-01",
        window_id="w0",
        task_label="rest",
        q_net=None,
        q_abs=0.25,
        f_dress=0.05,
        defect_density=0.02,
        n_triangles=10,
        n_valid_triangles=9,
        topology_quality=0.9,
        null_method="real_none",
        null_seed=0,
        source_file="f.edf",
        window_start_s=0.0,
        window_end_s=2.0,
        warnings=[],
    )
    assert row_partial_none.is_valid is False
    assert row_partial_none.topology_status == "skipped"
    assert row_partial_none.missingness_state == "unobserved"
    assert row_partial_none.replicate_count == 0

    # q_abs is NaN
    row_nan = LevelTRealTopologyRow(
        row_id="r_nan_qabs",
        subject_id="sub-01",
        session_id="ses-01",
        run_id="run-01",
        window_id="w1",
        task_label="rest",
        q_net=0.1,
        q_abs=float("nan"),
        f_dress=0.05,
        defect_density=0.02,
        n_triangles=10,
        n_valid_triangles=9,
        topology_quality=0.9,
        null_method="real_none",
        null_seed=0,
        source_file="f.edf",
        window_start_s=0.0,
        window_end_s=2.0,
        warnings=[],
    )
    assert row_nan.is_valid is False
    assert row_nan.topology_status == "skipped"
    assert row_nan.missingness_state == "unobserved"
    assert row_nan.q_abs is None
    assert row_nan.replicate_count == 0


# ---------------------------------------------------------------------------
# 13. Artifact alignment report handles malformed / NaN artifact_score safely
# ---------------------------------------------------------------------------

def test_build_artifact_alignment_report_handles_malformed_and_nonfinite_scores():
    rows = [
        _valid_row(0, topology_quality=0.9),
        _valid_row(1, topology_quality=0.8),
        _valid_row(2, topology_quality=0.85),
    ]
    m_rows = [
        {"row_id": "row-0", "artifact_score": "0.60"},
        {"row_id": "row-1", "artifact_score": "not_a_float"},
        {"row_id": "row-2", "artifact_score": "NaN"},
    ]
    report = build_artifact_alignment_report(rows, m_rows)

    assert report["n_rows"] == 3
    assert report["n_missing_artifact_scores"] == 2
    assert abs(report["mean_artifact_score"] - 0.60) < 1e-6
    assert report["high_artifact_rows"] == ["row-0"]
    assert report["artifact_dominance_proxy"] is True


# ---------------------------------------------------------------------------
# 14. Group significance report: skip-rate boundary, paired-subject gate, and missing row exclusion
# ---------------------------------------------------------------------------

def test_build_group_significance_report_skip_rate_exact_boundary_and_paired_subject_gate():
    pytest.importorskip("pandas")
    # 10 rows total: 8 valid (4 subjects x 2 conditions), 2 missing -> skip_rate = 0.20 exactly
    rows = []
    m_rows = []
    idx = 0
    for s in range(4):
        for cond, q_val in (("awake", 0.2 + 0.01 * s), ("sedated", 0.5 + 0.01 * s)):
            r = _valid_row(idx, subject_id=f"sub-{s}", task_label=cond, q_abs=q_val)
            rows.append(r)
            m_rows.append({"row_id": r.row_id, "state_label": cond})
            idx += 1
    for s in range(4, 6):
        r = _missing_row(idx, subject_id=f"sub-{s}", task_label="awake")
        rows.append(r)
        m_rows.append({"row_id": r.row_id, "state_label": "awake"})
        idx += 1

    # At max_skip_rate=0.20, skip_rate == 0.20 is at boundary (not > 0.20),
    # but min_paired_subjects=5 should fail with insufficient_power because only 4 subjects are paired!
    rep_power = build_group_significance_report(
        rows, m_rows, max_skip_rate=0.20, min_paired_subjects=5, n_permutations=50, seed=0
    )
    assert rep_power["status"] == "insufficient_power"
    assert rep_power["n_paired_subjects"] == 4

    # With min_paired_subjects=4 and max_skip_rate=0.20, it computes using ONLY the 8 valid rows
    rep_ok = build_group_significance_report(
        rows, m_rows, max_skip_rate=0.20, min_paired_subjects=4, n_permutations=50, seed=0
    )
    assert rep_ok["status"] == "computed"
    assert rep_ok["n_rows_total"] == 10
    assert rep_ok["n_rows_eligible"] == 8
    assert rep_ok["n_rows_excluded"] == 2
    assert rep_ok["metrics"]["q_abs"]["n_obs_a"] == 4
    assert rep_ok["metrics"]["q_abs"]["n_obs_b"] == 4


def test_build_ml_decoding_report_excludes_invalid_or_missing_metric_rows():
    # Construct invalid rows that happen to have empty warnings and positive n_triangles
    bad_rows = [
        LevelTRealTopologyRow(
            row_id=f"r{i}",
            subject_id=f"sub-{i}",
            session_id="ses-01",
            run_id="run-01",
            window_id=f"w{i}",
            task_label="a" if i < 5 else "b",
            q_net=None,
            q_abs=None,
            f_dress=None,
            defect_density=None,
            n_triangles=10,
            n_valid_triangles=9,
            topology_quality=None,
            null_method="real_none",
            null_seed=0,
            source_file="f.edf",
            window_start_s=0.0,
            window_end_s=2.0,
            warnings=[],
        )
        for i in range(10)
    ]
    m_rows = [{"row_id": r.row_id, "state_label": r.task_label} for r in bad_rows]
    rep = build_ml_decoding_report(bad_rows, m_rows)
    assert rep["status"] == "not_applicable"
    assert rep["n_rows_excluded"] == 10
