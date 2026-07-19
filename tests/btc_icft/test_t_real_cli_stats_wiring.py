"""CLI-level regression tests for Phase 3's stats wiring: each
run_{ds}_t_real.py must emit a group_significance_report.json by default
(cheap, always-on) and a null_gate_report.json only when --compute-nulls is
passed (compute-heavy, opt-in) -- see base_real_topology.py's
build_group_significance_report/build_null_gate_report.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

_MODULES = [
    "sciencer_d.btc_icft.pipelines.run_ds005620_t_real",
    "sciencer_d.btc_icft.pipelines.run_ds003969_t_real",
    "sciencer_d.btc_icft.pipelines.run_ds001787_t_real",
]


@pytest.mark.parametrize("module", _MODULES)
def test_group_significance_report_emitted_by_default(tmp_path: Path, module: str):
    out = tmp_path / "o"
    c = [sys.executable, "-m", module, "--out", str(out), "--mock-fixture"]
    r = subprocess.run(c, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (out / "group_significance_report.json").exists()
    assert not (out / "null_gate_report.json").exists()

    report = json.loads((out / "group_significance_report.json").read_text())
    assert report["status"] in ("computed", "not_applicable")
    assert "Group significance report" in (out / "report.md").read_text()


@pytest.mark.parametrize("module", _MODULES)
def test_null_gate_report_only_with_compute_nulls_flag(tmp_path: Path, module: str):
    out = tmp_path / "o"
    c = [
        sys.executable, "-m", module, "--out", str(out), "--mock-fixture",
        "--compute-nulls", "--n-surrogates", "3", "--gate-sample-size", "2",
    ]
    r = subprocess.run(c, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (out / "null_gate_report.json").exists()

    report = json.loads((out / "null_gate_report.json").read_text())
    assert report["status"] == "real_nulls_performed"
    assert report["real_nulls_performed"] is True
    assert report["n_surrogates_per_window"] == 3
    assert "Null gate report" in (out / "report.md").read_text()


@pytest.mark.parametrize("module", _MODULES)
def test_group_significance_deterministic_across_reruns(tmp_path: Path, module: str):
    m_rows = [
        {"row_id": f"r{i}", "subject_id": f"sub-{i:03d}", "session_id": "ses-01", "run_id": "",
         "window_id": "w0", "task_label": "x", "state_label": "a" if i < 5 else "b",
         "source_file": "missing.edf", "window_start_s": "0", "window_end_s": "1", "artifact_score": "0.1"}
        for i in range(10)
    ]
    m_dir = tmp_path / "m"
    m_dir.mkdir()
    with (m_dir / "features_m.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(m_rows[0].keys()))
        w.writeheader()
        w.writerows(m_rows)

    def _run(out_dir: Path) -> dict:
        c = [sys.executable, "-m", module, "--m-windows", str(m_dir), "--out", str(out_dir), "--real", "--seed", "5"]
        r = subprocess.run(c, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return json.loads((out_dir / "group_significance_report.json").read_text())

    r1 = _run(tmp_path / "o1")
    r2 = _run(tmp_path / "o2")
    assert r1 == r2
