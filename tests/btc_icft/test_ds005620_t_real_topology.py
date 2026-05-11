from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from sciencer_d.btc_icft.level_t import ds005620_real_topology as topo


def _m_rows():
    return [
        {"row_id":"r1","subject_id":"s1","session_id":"ses1","run_id":"1","window_id":"w1","task_label":"awake","source_file":"a","window_start_s":"0","window_end_s":"10","artifact_score":"0.1"},
        {"row_id":"r2","subject_id":"s2","session_id":"ses1","run_id":"1","window_id":"w2","task_label":"sedated","source_file":"b","window_start_s":"10","window_end_s":"20","artifact_score":"0.6"},
    ]


def test_fixture_rows_build():
    rows = topo.build_level_t_rows_from_m_windows(_m_rows(), mock_fixture=True)
    assert len(rows) > 0
    assert len({r.subject_id for r in rows}) >= 2
    for r in rows:
        assert r.n_valid_triangles <= r.n_triangles
        assert 0 <= r.topology_quality <= 1


def test_load_and_missing_columns(tmp_path: Path):
    d = tmp_path / "m"; d.mkdir()
    with (d / "features_m.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(_m_rows()[0].keys())); w.writeheader(); w.writerows(_m_rows())
    rows = topo.load_level_m_window_features(str(d))
    assert len(rows) == 2

    d2 = tmp_path / "m2"; d2.mkdir()
    with (d2 / "features_m.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["row_id"]); w.writeheader(); w.writerow({"row_id":"x"})
    try:
        topo.load_level_m_window_features(str(d2))
        assert False
    except ValueError as e:
        assert "Missing required columns" in str(e)


def test_missing_features_raises(tmp_path: Path):
    try:
        topo.load_level_m_window_features(str(tmp_path / "missing"))
        assert False
    except FileNotFoundError as e:
        assert "Run run_ds005620_m_real first or use --mock-fixture" in str(e)


def test_reports_and_outputs(tmp_path: Path):
    m = _m_rows(); rows = topo.build_level_t_rows_from_m_windows(m, mock_fixture=True)
    topo.result_rows_cache = rows
    q = topo.build_topology_quality_report(rows)
    n = topo.build_null_placeholder_report(rows)
    a = topo.build_artifact_alignment_report(rows, m)
    assert q["n_rows"] == len(rows)
    assert n["status"] == "placeholder_only"
    assert "channel_shuffle" in n["methods_planned"]
    assert "artifact_dominance_proxy" in a
    res = topo.LevelTRealTopologyResult("ds005620", len(rows), 2, len(rows), q, n, a, topo.build_level_t_omega_event(rows),
        "Local DS005620-style EEG windows were mapped into operational Level T topology telemetry candidates for future M+T residual testing.",
        ["No topology proof."], [])
    out = topo.write_level_t_topology_outputs(res, str(tmp_path / "out"))
    for f in ["features_t.csv","topology_quality_report.json","null_placeholder_report.json","artifact_alignment_report.json","omega_event.json","report.md"]:
        assert (tmp_path / "out" / f).exists()
    assert "operational Level T" in (tmp_path / "out" / "report.md").read_text()
    bad = ["proves consciousness","soul proven","afterlife proven","liberation detected","ontology solved","ultimate reality","Q equals self","Q equals soul","Q_abs equals suffering","f_dress equals karma"]
    text = (tmp_path / "out" / "report.md").read_text().lower()
    for b in bad:
        assert b.lower() not in text
    assert "promoted" not in json.dumps(json.loads((tmp_path / "out" / "omega_event.json").read_text()))


def test_cli(tmp_path: Path):
    c = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_t_real", "--out", str(tmp_path / "o"), "--mock-fixture"]
    r = subprocess.run(c, capture_output=True, text=True)
    assert r.returncode == 0
    c2 = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_t_real", "--m-windows", str(tmp_path / "nope"), "--out", str(tmp_path / "o2")]
    r2 = subprocess.run(c2, capture_output=True, text=True)
    assert r2.returncode != 0
    assert "Run run_ds005620_m_real first or use --mock-fixture" in (r2.stdout + r2.stderr)
    c3 = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_t_real", "--out", str(tmp_path / "o3"), "--real"]
    r3 = subprocess.run(c3, capture_output=True, text=True)
    assert r3.returncode != 0
    assert "Use --mock-fixture for offline validation" in (r3.stdout + r3.stderr)


def test_config_contains_contract():
    t = Path("configs/btc_icft/ds005620_t_real.yaml").read_text(encoding="utf-8")
    for k in ["required_outputs", "topology_columns", "guardrails", "omega_event.json", "no_m_plus_t_benchmark"]:
        assert k in t
