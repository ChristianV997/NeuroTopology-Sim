"""Unit and integration tests for cohort missingness auditing and pairing gates.

Verifies:
1. Complete paired cohorts pass all gates with PASS and gate_passed=True.
2. Incomplete cohorts fail closed with INCOMPLETE when windows are missing.
3. Excessive missingness (>20% skip rate) blocks evaluation with BLOCKED.
4. Insufficient paired subjects (<5) yields INSUFFICIENT_POWER.
5. Unpaired subjects in 2-condition experiments are detected and reported.
6. Missing expected subjects from preregistered cohorts are caught.
7. BrainVision companion file failures are accurately categorized.
8. Empty datasets fail closed with EMPTY_DATASET.
9. All audit outputs are deterministic, finite, and strictly JSON-serializable (no NaNs).
10. Isolated subprocess execution verifies cross-platform execution safety.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import pytest

from sciencer_d.btc_icft.level_t.base_real_topology import (
    LevelTRealTopologyRow,
    audit_cohort_missingness,
)


def _make_row(
    index: int,
    subject_id: str,
    task_label: str,
    is_valid: bool = True,
    state: str = "computed",
    reason: str | None = None,
) -> tuple[LevelTRealTopologyRow, dict]:
    t_row = LevelTRealTopologyRow(
        row_id=f"row-{index}",
        subject_id=subject_id,
        session_id="ses-01",
        run_id="run-01",
        window_id=f"win-{index}",
        task_label=task_label if is_valid else None,
        q_net=0.15 if is_valid else None,
        q_abs=0.30 if is_valid else None,
        f_dress=0.08 if is_valid else None,
        defect_density=0.03 if is_valid else None,
        n_triangles=10 if is_valid else 0,
        n_valid_triangles=9 if is_valid else 0,
        topology_quality=0.9 if is_valid else None,
        null_method="real_none",
        null_seed=index,
        source_file=f"/data/{subject_id}_{task_label}.edf",
        window_start_s=float(index * 2),
        window_end_s=float((index + 1) * 2),
        warnings=[] if is_valid else ([reason] if reason else ["missing window"]),
        topology_status="computed" if is_valid else "skipped",
        missingness_state=state,
        missingness_reason=reason,
        is_valid=is_valid,
        run_status="complete" if is_valid else "failed",
        replicate_count=1 if is_valid else 0,
    )
    m_row = {
        "row_id": f"row-{index}",
        "subject_id": subject_id,
        "task_label": task_label,
        "state_label": task_label,
    }
    return t_row, m_row


def _build_paired_cohort(
    n_subjects: int = 6,
    windows_per_condition: int = 2,
    conditions: tuple[str, str] = ("awake", "sedated"),
) -> tuple[list[LevelTRealTopologyRow], list[dict]]:
    t_rows: list[LevelTRealTopologyRow] = []
    m_rows: list[dict] = []
    idx = 0
    for s in range(1, n_subjects + 1):
        sub_id = f"sub-{s:02d}"
        for cond in conditions:
            for _ in range(windows_per_condition):
                t_row, m_row = _make_row(idx, sub_id, cond, is_valid=True)
                t_rows.append(t_row)
                m_rows.append(m_row)
                idx += 1
    return t_rows, m_rows


# ---------------------------------------------------------------------------
# 1. Complete paired cohort passes all gates
# ---------------------------------------------------------------------------

def test_complete_paired_cohort_passes():
    t_rows, m_rows = _build_paired_cohort(n_subjects=6, windows_per_condition=2)
    report = audit_cohort_missingness(t_rows, m_rows, group_col="task_label")

    assert report["verdict"] == "PASS"
    assert report["gate_passed"] is True
    assert report["skip_rate"] == 0.0
    assert report["n_total_windows"] == 24
    assert report["n_valid_windows"] == 24
    assert report["n_missing_windows"] == 0
    assert report["n_total_subjects"] == 6
    assert report["n_complete_subjects"] == 6
    assert report["n_partial_subjects"] == 0
    assert report["n_failed_subjects"] == 0
    assert report["n_paired_subjects"] == 6
    assert len(report["unpaired_subjects"]) == 0
    assert "complete and valid" in report["verdict_reason"]


# ---------------------------------------------------------------------------
# 2. Incomplete cohort with missing window fails closed
# ---------------------------------------------------------------------------

def test_incomplete_cohort_with_missing_window_fails_closed():
    t_rows, m_rows = _build_paired_cohort(n_subjects=6, windows_per_condition=2)
    # Invalidate one window for sub-03
    t_rows[8] = LevelTRealTopologyRow(
        row_id="row-8",
        subject_id="sub-03",
        session_id=None,
        run_id=None,
        window_id="win-8",
        task_label=None,
        q_net=None,
        q_abs=None,
        f_dress=None,
        defect_density=None,
        n_triangles=0,
        n_valid_triangles=0,
        topology_quality=None,
        null_method="real_none",
        null_seed=0,
        source_file="/data/sub-03_awake.edf",
        window_start_s=0.0,
        window_end_s=2.0,
        warnings=["signal corrupted"],
        topology_status="skipped",
        missingness_state="failed_read",
        missingness_reason="signal corrupted",
        is_valid=False,
        run_status="failed",
        replicate_count=0,
    )

    report = audit_cohort_missingness(t_rows, m_rows, group_col="task_label")

    assert report["verdict"] == "INCOMPLETE"
    assert report["gate_passed"] is False
    assert report["n_missing_windows"] == 1
    assert report["n_valid_windows"] == 23
    assert report["missingness_by_reason"]["failed_read"] == 1
    assert "sub-03" in report["partial_subjects"]
    assert report["subject_details"]["sub-03"]["status"] == "partial"
    assert "1 missing windows" in report["verdict_reason"]


# ---------------------------------------------------------------------------
# 3. Excessive missingness blocks evaluation
# ---------------------------------------------------------------------------

def test_blocked_when_skip_rate_exceeds_threshold():
    t_rows, m_rows = _build_paired_cohort(n_subjects=6, windows_per_condition=2)
    # Invalidate 7 out of 24 windows -> 29.2% > 20%
    for i in range(7):
        t_rows[i] = LevelTRealTopologyRow(
            row_id=f"row-{i}",
            subject_id=t_rows[i].subject_id,
            session_id=None,
            run_id=None,
            window_id=f"win-{i}",
            task_label=None,
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
            window_start_s=0.0,
            window_end_s=2.0,
            warnings=["source missing"],
            topology_status="skipped",
            missingness_state="missing_source_file",
            missingness_reason="source missing",
            is_valid=False,
            run_status="failed",
            replicate_count=0,
        )

    report = audit_cohort_missingness(t_rows, m_rows, max_skip_rate=0.20)

    assert report["verdict"] == "BLOCKED"
    assert report["gate_passed"] is False
    assert report["skip_rate"] > 0.20
    assert "exceeds maximum threshold" in report["verdict_reason"]


# ---------------------------------------------------------------------------
# 4. Insufficient power when paired subjects below minimum requirement
# ---------------------------------------------------------------------------

def test_insufficient_power_when_paired_subjects_below_minimum():
    # Only 3 paired subjects, but min_paired_subjects is 5
    t_rows, m_rows = _build_paired_cohort(n_subjects=3, windows_per_condition=2)
    report = audit_cohort_missingness(t_rows, m_rows, min_paired_subjects=5)

    assert report["verdict"] == "INSUFFICIENT_POWER"
    assert report["gate_passed"] is False
    assert report["n_paired_subjects"] == 3
    assert report["min_paired_subjects"] == 5
    assert "below minimum power requirement" in report["verdict_reason"]


# ---------------------------------------------------------------------------
# 5. Unpaired subjects in condition comparison are flagged
# ---------------------------------------------------------------------------

def test_unpaired_condition_subjects_detected():
    # 8 subjects total: 6 paired (meets min_paired_subjects=5), plus 2 unpaired ("awake" only)
    t_rows, m_rows = _build_paired_cohort(n_subjects=6, windows_per_condition=2)
    idx = len(t_rows)
    for s in (7, 8):
        sub_id = f"sub-{s:02d}"
        for _ in range(2):
            t_r, m_r = _make_row(idx, sub_id, "awake", is_valid=True)
            t_rows.append(t_r)
            m_rows.append(m_r)
            idx += 1

    report = audit_cohort_missingness(t_rows, m_rows, group_col="task_label")

    assert report["verdict"] == "INCOMPLETE"
    assert report["gate_passed"] is False
    assert report["n_paired_subjects"] == 6
    assert set(report["unpaired_subjects"]) == {"sub-07", "sub-08"}


# ---------------------------------------------------------------------------
# 6. Missing expected subject from preregistered cohort
# ---------------------------------------------------------------------------

def test_missing_expected_subject_detected():
    t_rows, m_rows = _build_paired_cohort(n_subjects=5, windows_per_condition=2)
    expected = [f"sub-{i:02d}" for i in range(1, 7)]  # sub-06 missing!

    report = audit_cohort_missingness(
        t_rows, m_rows, min_paired_subjects=5, expected_subjects=expected
    )

    assert report["verdict"] == "INCOMPLETE"
    assert report["gate_passed"] is False
    assert "sub-06" in report["missing_expected_subjects"]


# ---------------------------------------------------------------------------
# 7. BrainVision companion file failures tracked accurately
# ---------------------------------------------------------------------------

def test_companion_file_failures_tracked():
    t_rows, m_rows = _build_paired_cohort(n_subjects=6, windows_per_condition=2)
    # Mark windows for sub-02 as missing companion file
    t_rows[2] = LevelTRealTopologyRow(
        row_id="row-2",
        subject_id="sub-02",
        session_id=None,
        run_id=None,
        window_id="win-2",
        task_label=None,
        q_net=None,
        q_abs=None,
        f_dress=None,
        defect_density=None,
        n_triangles=0,
        n_valid_triangles=0,
        topology_quality=None,
        null_method="real_none",
        null_seed=0,
        source_file="/data/sub-02_ses-01_task-rest.vhdr",
        window_start_s=0.0,
        window_end_s=2.0,
        warnings=["BrainVision companion file missing: sub-02_ses-01_task-rest.vmrk"],
        topology_status="skipped",
        missingness_state="missing_companion_file",
        missingness_reason="BrainVision companion file missing: sub-02_ses-01_task-rest.vmrk",
        is_valid=False,
        run_status="failed",
        replicate_count=0,
    )

    report = audit_cohort_missingness(t_rows, m_rows)

    assert report["missingness_by_reason"]["missing_companion_file"] == 1
    rec = report["missing_records"][0]
    assert rec["row_id"] == "row-2"
    assert rec["subject_id"] == "sub-02"
    assert rec["missingness_state"] == "missing_companion_file"


# ---------------------------------------------------------------------------
# 8. Empty dataset fails closed
# ---------------------------------------------------------------------------

def test_empty_dataset_fails_closed():
    report = audit_cohort_missingness([], [])
    assert report["verdict"] == "EMPTY_DATASET"
    assert report["gate_passed"] is False
    assert report["n_total_windows"] == 0
    assert report["n_valid_windows"] == 0


# ---------------------------------------------------------------------------
# 9. Audit output is deterministic and strictly JSON-serializable
# ---------------------------------------------------------------------------

def test_audit_output_deterministic_and_json():
    t_rows, m_rows = _build_paired_cohort(n_subjects=6, windows_per_condition=2)
    r1 = audit_cohort_missingness(t_rows, m_rows)
    r2 = audit_cohort_missingness(t_rows, m_rows)

    s1 = json.dumps(r1, sort_keys=True)
    s2 = json.dumps(r2, sort_keys=True)
    assert s1 == s2

    # Verify no NaN or Infinity exists in JSON
    assert "NaN" not in s1
    assert "Infinity" not in s1


# ---------------------------------------------------------------------------
# 10. Subprocess execution safety
# ---------------------------------------------------------------------------

def test_subprocess_isolated_audit_execution(tmp_path):
    repo_root = str(Path(__file__).resolve().parents[1]).replace("\\", "/")
    script_path = tmp_path / "run_audit.py"
    script_path.write_text(
        f"""
import json
import sys
from pathlib import Path

repo_root = {repo_root!r}
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from sciencer_d.btc_icft.level_t.base_real_topology import (
    LevelTRealTopologyRow,
    audit_cohort_missingness,
)

t_row = LevelTRealTopologyRow(
    row_id="r1", subject_id="sub-01", session_id="ses-01", run_id="run-01",
    window_id="w1", task_label="rest", q_net=0.1, q_abs=0.2, f_dress=0.05,
    defect_density=0.02, n_triangles=10, n_valid_triangles=9, topology_quality=0.95,
    null_method="real_none", null_seed=0, source_file="fake.edf",
    window_start_s=0.0, window_end_s=2.0, warnings=[],
)
m_row = {{"row_id": "r1", "subject_id": "sub-01", "task_label": "rest"}}

report = audit_cohort_missingness([t_row], [m_row], min_paired_subjects=1)
print(json.dumps(report))
""",
        encoding="utf-8",
    )

    cmd = [sys.executable, str(script_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    assert result.returncode == 0
    payload = json.loads(result.stdout.strip())
    assert payload["verdict"] == "PASS"
    assert payload["gate_passed"] is True
    assert payload["n_total_windows"] == 1
