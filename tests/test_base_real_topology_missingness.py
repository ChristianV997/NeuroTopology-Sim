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
    build_phase_based_topology_report,
    build_connectivity_report,
    build_null_gate_report,
    compute_phase_based_topology_for_window,
    compute_connectivity_for_window,
    compute_surrogate_gate_for_window,
    compute_fixture_topology_for_window,
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


@pytest.mark.parametrize(
    "channels",
    [
        [[1.0, 2.0], [3.0]],
        [1.0, 2.0],
    ],
    ids=["ragged-channels", "one-dimensional-channels"],
)
def test_malformed_channel_layout_returns_failed_read(tmp_path, monkeypatch, channels):
    signal_file = tmp_path / "malformed.edf"
    signal_file.write_bytes(b"synthetic-only")
    monkeypatch.setattr(
        "data.bids_ingest.read_window_signal",
        lambda *args, **kwargs: channels,
    )

    row = compute_real_topology_for_window(
        {
            "row_id": "synthetic-malformed",
            "subject_id": "synthetic-subject",
            "window_id": "synthetic-window",
            "task_label": "synthetic-task",
            "source_file": str(signal_file),
            "window_start_s": 0.0,
            "window_end_s": 2.0,
        }
    )

    assert row.is_valid is False
    assert row.topology_status == "skipped"
    assert row.missingness_state == "failed_read"
    assert row.q_net is None
    assert row.q_abs is None
    assert row.f_dress is None
    assert row.defect_density is None
    assert row.topology_quality is None
    assert row.n_triangles == 0
    assert row.n_valid_triangles == 0
    assert row.missingness_reason is not None
    assert row.replicate_count == 0
    assert row.run_status == "failed"


# ---------------------------------------------------------------------------
# 5. Genuine zero observation (q_net = 0.0) is preserved as valid computed row
# ---------------------------------------------------------------------------

def test_real_zero_valued_observation_distinguished_from_missing():
    # A zero-valued computed output remains distinct from a missing metric.
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
        res, str(out_dir), rows, "ds005620", cohort_missingness_report=cohort_audit,
        spatial_topology_report={"status": "not_applicable"},
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
    assert "Local Signal-Reader Level T Topology Extraction" in report_md
    assert "genuine 2D phase field" not in report_md
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
    assert row_partial_none.run_status == "failed"
    assert row_partial_none.missingness_reason == "missing or non-finite topology metric"
    assert row_partial_none.warnings

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

    from dataclasses import replace

    row_inf = replace(_valid_row(2), f_dress=float("inf"))
    report = build_topology_quality_report([row_inf])
    assert row_inf.is_valid is False
    assert row_inf.run_status == "failed"
    assert report["n_valid_rows"] == 0
    assert report["n_missing_rows"] == 1
    assert report["quality_passed"] is False


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


def test_compute_real_topology_rejects_missing_or_invalid_window_bounds(tmp_path, monkeypatch):
    from data import bids_ingest

    source = tmp_path / "synthetic.edf"
    source.write_bytes(b"synthetic-only test marker")
    calls = []

    def fake_reader(*args, **kwargs):
        calls.append((args, kwargs))
        return [[0.1, 0.2, 0.3], [0.3, 0.2, 0.1]]

    monkeypatch.setattr(bids_ingest, "read_window_signal", fake_reader)
    invalid_bounds = [
        (None, "2"),
        ("", "2"),
        ("NaN", "2"),
        ("Infinity", "3"),
        ("not-a-number", "2"),
        ("0", None),
        ("0", "NaN"),
        ("0", "Infinity"),
        ("2", "1"),
        ("0", "0"),
    ]
    for index, (start, end) in enumerate(invalid_bounds):
        row = compute_real_topology_for_window({
            "row_id": f"synthetic-{index}",
            "subject_id": "synthetic-subject",
            "window_id": f"window-{index}",
            "source_file": str(source),
            "window_start_s": start,
            "window_end_s": end,
        })
        assert row.is_valid is False
        assert row.topology_status == "skipped"
        assert row.missingness_state == "unobserved"
        assert row.q_net is None and row.q_abs is None

    assert calls == []


def test_fixture_topology_does_not_promote_missing_window_metadata():
    row = compute_fixture_topology_for_window({
        "row_id": "synthetic-row",
        "subject_id": "synthetic-subject",
        "window_id": "synthetic-window",
        "source_file": "synthetic.edf",
        "window_end_s": "2",
    })

    assert row.is_valid is False
    assert row.missingness_state == "unobserved"
    assert row.q_net is None and row.q_abs is None


def test_fixture_rows_are_not_reported_as_valid_topology_or_artifact_alignment():
    row = compute_fixture_topology_for_window({
        "row_id": "synthetic-row",
        "subject_id": "synthetic-subject",
        "window_id": "synthetic-window",
        "source_file": "synthetic.edf",
        "window_start_s": "0",
        "window_end_s": "2",
    })

    quality = build_topology_quality_report([row])
    alignment = build_artifact_alignment_report([row], [{"row_id": row.row_id, "artifact_score": "0.2"}])

    assert quality["status"] == "incomplete"
    assert quality["quality_passed"] is False
    assert quality["n_valid_rows"] == 0
    assert quality["n_synthetic_fixture_rows"] == 1
    assert alignment["topology_quality_mean"] is None
    assert alignment["n_synthetic_fixture_topology_rows"] == 1


def test_fixture_rows_are_excluded_from_group_and_ml_reports():
    m_rows = [
        {
            "row_id": f"fixture-{index}",
            "subject_id": f"synthetic-sub-{index}",
            "window_id": f"window-{index}",
            "source_file": "synthetic.edf",
            "window_start_s": str(index * 2),
            "window_end_s": str(index * 2 + 2),
            "state_label": "awake" if index < 5 else "sedated",
        }
        for index in range(10)
    ]
    rows = [compute_fixture_topology_for_window(row) for row in m_rows]

    group = build_group_significance_report(rows, m_rows)
    decoding = build_ml_decoding_report(rows, m_rows)

    assert group["status"] == "not_applicable"
    assert group["n_rows_eligible"] == 0
    assert decoding["status"] == "not_applicable"
    assert decoding["n_rows_excluded"] == len(rows)


def test_signal_reports_reject_invalid_bounds_before_loading_signal_tools():
    m_row = {"row_id": "synthetic-row", "source_file": "synthetic.edf", "window_start_s": None, "window_end_s": "2"}

    results = [
        compute_phase_based_topology_for_window(m_row),
        compute_connectivity_for_window(m_row),
        compute_surrogate_gate_for_window(m_row),
    ]

    assert all(result["status"] == "skipped" for result in results)
    assert all("window bounds" in result["reason"] for result in results)


def test_signal_report_aggregators_keep_missing_joins_visible():
    row = _valid_row(0)

    phase = build_phase_based_topology_report([row], [])
    connectivity = build_connectivity_report([row], [])
    nulls = build_null_gate_report([row], [])

    for report in (phase, connectivity):
        assert report["status"] == "not_applicable"
        assert report["n_windows_total_candidates"] == 1
        assert report["n_windows_skipped"] == 1
        assert report["results"][0]["reason"] == "matching Level M row is missing"
        json.dumps(report, allow_nan=False)
    assert nulls["status"] == "not_applicable"
    assert nulls["real_nulls_performed"] is False
    assert nulls["n_windows_total_candidates"] == 1
    assert nulls["n_windows_skipped"] == 1
    assert nulls["gate_results"][0]["reason"] == "matching Level M row is missing"
    json.dumps(nulls, allow_nan=False)


def test_warning_rows_are_not_reused_as_valid_measurements_across_reports():
    from dataclasses import replace

    row = replace(_valid_row(0), warnings=["synthetic warning marker"])
    m_row = {
        "row_id": row.row_id,
        "source_file": "synthetic-missing.edf",
        "window_start_s": 0.0,
        "window_end_s": 2.0,
        "state_label": "awake",
    }

    quality = build_topology_quality_report([row])
    alignment = build_artifact_alignment_report([row], [{"row_id": row.row_id, "artifact_score": 0.2}])
    phase = build_phase_based_topology_report([row], [m_row])
    connectivity = build_connectivity_report([row], [m_row])
    nulls = build_null_gate_report([row], [m_row])
    group = build_group_significance_report([row], [m_row], max_skip_rate=0.0)
    decoding = build_ml_decoding_report([row], [m_row])
    cohort = audit_cohort_missingness([row], [m_row], max_skip_rate=0.0)

    assert quality["n_valid_rows"] == 0
    assert quality["n_missing_rows"] == 1
    assert quality["quality_passed"] is False
    assert alignment["topology_quality_mean"] is None
    assert group["status"] == "blocked_high_skip_rate"
    assert group["n_rows_eligible"] == 0
    assert decoding["status"] == "not_applicable"
    assert phase["results"][0]["reason"] == "Level T row is invalid or unobserved"
    assert connectivity["results"][0]["reason"] == "Level T row is invalid or unobserved"
    assert nulls["gate_results"][0]["reason"] == "Level T row is invalid or unobserved"
    assert cohort["verdict"] == "BLOCKED"
    assert cohort["n_valid_windows"] == 0
    for report in (quality, alignment, phase, connectivity, nulls, group, decoding, cohort):
        json.dumps(report, allow_nan=False)


def test_post_construction_nonfinite_mutation_is_rejected_by_aggregates():
    row = _valid_row(0)
    row.q_abs = float("nan")

    quality = build_topology_quality_report([row])
    cohort = audit_cohort_missingness([row], [], max_skip_rate=0.0)

    assert quality["n_valid_rows"] == 0
    assert quality["n_missing_rows"] == 1
    assert quality["quality_passed"] is False
    assert cohort["n_valid_windows"] == 0
    assert cohort["verdict"] == "BLOCKED"


def test_direct_row_with_nonfinite_window_bounds_is_demoted():
    from dataclasses import replace

    row = replace(_valid_row(0), window_start_s=float("nan"))

    assert row.is_valid is False
    assert row.topology_status == "skipped"
    assert row.missingness_state == "unobserved"
    assert row.q_net is None and row.q_abs is None


def test_group_report_fails_closed_when_an_eligible_row_lacks_group_metadata():
    rows = [
        _valid_row(0, subject_id="sub-01", task_label="awake"),
        _valid_row(1, subject_id="sub-01", task_label="sedated"),
        _valid_row(2, subject_id="sub-02", task_label="awake"),
        _valid_row(3, subject_id="sub-02", task_label="sedated"),
    ]
    m_rows = [
        {"row_id": row.row_id, "state_label": "" if index == 3 else row.task_label}
        for index, row in enumerate(rows)
    ]

    report = build_group_significance_report(rows, m_rows, n_permutations=20)

    assert report["status"] == "not_applicable"
    assert report["n_rows_missing_group_metadata"] == 1
    assert report["n_rows_used"] == 0
    assert "group metadata" in report["reason"]


def test_group_report_rejects_nonfinite_skip_threshold():
    with pytest.raises(ValueError, match="max_skip_rate must be finite"):
        build_group_significance_report([], [], max_skip_rate=float("nan"))


def test_ml_report_fails_closed_when_an_eligible_row_lacks_group_metadata():
    rows = [
        _valid_row(index, subject_id=f"sub-{index}", task_label="awake" if index < 5 else "sedated")
        for index in range(10)
    ]
    m_rows = [
        {"row_id": row.row_id, "state_label": "" if index == 9 else row.task_label}
        for index, row in enumerate(rows)
    ]

    report = build_ml_decoding_report(rows, m_rows)

    assert report["status"] == "not_applicable"
    assert report["n_rows_missing_group_metadata"] == 1
    assert report["n_rows_used"] == 0
    assert "group metadata" in report["reason"]



def test_boolean_and_out_of_range_metrics_or_triangles_demote_row():
    from dataclasses import replace

    bool_window_row = replace(_valid_row(0), window_start_s=False, window_end_s=True)
    bool_metric_row = replace(_valid_row(1), q_abs=True)
    bad_triangles_row = replace(_valid_row(2), n_triangles=2, n_valid_triangles=5)
    negative_triangles_row = replace(_valid_row(3), n_triangles=-4, n_valid_triangles=0)
    bad_quality_row = replace(_valid_row(4), topology_quality=1.5)
    negative_q_abs_row = replace(_valid_row(5), q_abs=-0.1)

    assert bad_quality_row.topology_quality is None
    for row in (
        bool_window_row,
        bool_metric_row,
        bad_triangles_row,
        negative_triangles_row,
        bad_quality_row,
        negative_q_abs_row,
    ):
        assert row.is_valid is False
        assert row.topology_status == "skipped"
        assert row.missingness_state == "unobserved"
    for row in (
        bool_window_row,
        bool_metric_row,
        bad_triangles_row,
        negative_triangles_row,
        negative_q_abs_row,
    ):
        assert row.q_abs is None


def test_group_and_ml_reports_fail_closed_on_contradictory_metadata():
    rows = [
        _valid_row(index, subject_id=f"sub-{index % 2}", task_label="awake" if index % 2 == 0 else "sedated")
        for index in range(10)
    ]
    m_rows = [
        {"row_id": row.row_id, "subject_id": row.subject_id, "task_label": row.task_label}
        for row in rows
    ]
    m_rows[0]["task_label"] = "sedated"  # Contradicts rows[0].task_label == "awake"

    group = build_group_significance_report(rows, m_rows, group_col="task_label", n_permutations=20)
    decoding = build_ml_decoding_report(rows, m_rows, group_col="task_label")

    assert group["status"] == "not_applicable"
    assert group["n_rows_used"] == 0
    assert "contradictory" in group["reason"]
    assert decoding["status"] == "not_applicable"
    assert decoding["n_rows_used"] == 0
    assert "contradictory" in decoding["reason"]


def test_ml_report_ignores_skipped_and_nonfinite_extra_features(monkeypatch):
    import analysis.ml_decoding as ml_decoding

    captured_feature_dicts = []

    def fake_build_decoding_report(feature_dicts, labels, seed=0, n_permutations=1000, cv_folds=5):
        captured_feature_dicts.extend(feature_dicts)
        return {
            "status": "computed",
            "features_used": sorted({k for d in feature_dicts for k in d.keys()}),
        }

    monkeypatch.setattr(ml_decoding, "build_decoding_report", fake_build_decoding_report)

    rows = [
        _valid_row(index, subject_id=f"sub-{index}", task_label="awake" if index < 5 else "sedated")
        for index in range(10)
    ]
    m_rows = [{"row_id": row.row_id, "state_label": row.task_label} for row in rows]
    extra = [
        [
            {
                "row_id": r.row_id,
                "status": "skipped" if idx == 0 else "computed",
                "skipped_only_metric": 999.0 if idx == 0 else float("nan"),
                "valid_extra_metric": 0.5,
                "bad_nan": float("nan"),
                "bool_val": True,
            }
            for idx, r in enumerate(rows)
        ]
    ]

    report = build_ml_decoding_report(rows, m_rows, extra_feature_reports=extra, n_permutations=10)
    assert "bad_nan" not in report["features_used"]
    assert "bool_val" not in report["features_used"]
    assert "skipped_only_metric" not in report["features_used"]
    assert "valid_extra_metric" in report["features_used"]
    assert "valid_extra_metric" not in captured_feature_dicts[0]  # row 0 was skipped in extra report
    json.dumps(report, allow_nan=False)


def test_optional_signal_window_computers_fail_closed_on_nonfinite_samples(tmp_path, monkeypatch):
    pytest.importorskip("scipy")
    from data import bids_ingest

    source = tmp_path / "synthetic.edf"
    source.write_bytes(b"synthetic-only test marker")

    monkeypatch.setattr(bids_ingest, "get_sample_rate", lambda *_args, **_kwargs: 100.0)
    monkeypatch.setattr(
        bids_ingest,
        "read_window_signal",
        lambda *_args, **_kwargs: np.array([[0.1, float("nan"), 0.2, 0.3], [0.2, 0.1, 0.3, 0.4]], dtype=float),
    )
    m_row = {
        "row_id": "synthetic-nan-window",
        "source_file": str(source),
        "window_start_s": "0",
        "window_end_s": "2",
    }

    phase = compute_phase_based_topology_for_window(m_row)
    conn = compute_connectivity_for_window(m_row)
    surr = compute_surrogate_gate_for_window(m_row, n_surrogates=4)

    for res in (phase, conn, surr):
        assert res["status"] == "skipped"
        assert "non-finite" in res["reason"]
        json.dumps(res, allow_nan=False)


@pytest.mark.parametrize(
    "status_kwargs",
    [
        {"run_status": "failed"},
        {"run_status": "partial"},
        {"missingness_state": "unobserved", "missingness_reason": "status-only exclusion"},
        {"missingness_state": "partial_run", "missingness_reason": "status-only exclusion"},
        {"missingness_state": "failed_read", "missingness_reason": "status-only exclusion"},
        {"replicate_count": 0},
    ],
    ids=[
        "failed_run_status",
        "partial_run_status",
        "unobserved_missingness",
        "partial_run_missingness",
        "failed_read_missingness",
        "zero_replicate_count",
    ],
)
def test_incomplete_status_metadata_cannot_enter_reports_as_valid_evidence(status_kwargs):
    """Regression: finite metrics must not override incomplete status/missingness."""
    from dataclasses import replace

    from sciencer_d.btc_icft.level_t.base_real_topology import _is_eligible_topology_row

    row = replace(_valid_row(0), **status_kwargs)
    m_row = {
        "row_id": row.row_id,
        "subject_id": row.subject_id,
        "task_label": row.task_label,
        "state_label": row.task_label,
        "source_file": "synthetic-missing.edf",
        "window_start_s": 0.0,
        "window_end_s": 2.0,
    }

    assert _is_eligible_topology_row(row) is False

    quality = build_topology_quality_report([row])
    alignment = build_artifact_alignment_report([row], [{"row_id": row.row_id, "artifact_score": 0.2}])
    phase = build_phase_based_topology_report([row], [m_row])
    connectivity = build_connectivity_report([row], [m_row])
    nulls = build_null_gate_report([row], [m_row])
    group = build_group_significance_report([row], [m_row], max_skip_rate=0.0)
    decoding = build_ml_decoding_report([row], [m_row])
    cohort = audit_cohort_missingness([row], [m_row], max_skip_rate=0.0)

    assert quality["n_valid_rows"] == 0
    assert quality["n_missing_rows"] == 1
    assert quality["quality_passed"] is False
    assert quality["status"] != "pass"
    assert alignment["topology_quality_mean"] is None
    assert group["status"] == "blocked_high_skip_rate"
    assert group["n_rows_eligible"] == 0
    assert decoding["status"] == "not_applicable"
    assert phase["results"][0]["reason"] == "Level T row is invalid or unobserved"
    assert connectivity["results"][0]["reason"] == "Level T row is invalid or unobserved"
    assert nulls["gate_results"][0]["reason"] == "Level T row is invalid or unobserved"
    assert cohort["verdict"] != "PASS"
    assert cohort["gate_passed"] is False
    assert cohort["n_valid_windows"] == 0
    assert cohort["n_missing_windows"] == 1
    assert any(
        rec["row_id"] == row.row_id for rec in cohort["missing_records"]
    ), "exclusions must remain visible in missing_records"
    for report in (quality, alignment, phase, connectivity, nulls, group, decoding, cohort):
        json.dumps(report, allow_nan=False)
