from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from sciencer_d.btc_icft.level_t import ds003969_real_topology as topo


def _m_rows():
    return [
        {"row_id":"r1","subject_id":"sub-001","session_id":"","run_id":"","window_id":"w1","task_label":"med1breath","source_file":"a","window_start_s":"0","window_end_s":"10","artifact_score":"0.1"},
        {"row_id":"r2","subject_id":"sub-002","session_id":"","run_id":"","window_id":"w2","task_label":"think1","source_file":"b","window_start_s":"10","window_end_s":"20","artifact_score":"0.6"},
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
        assert "Run run_ds003969_m_real first or use --mock-fixture" in str(e)


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
    res = topo.LevelTRealTopologyResult("ds003969", len(rows), 2, len(rows), q, n, a, topo.build_level_t_omega_event(rows),
        "Local DS003969-style EEG windows were mapped into operational Level T topology telemetry candidates for future M+T residual testing.",
        ["No topology proof."], [])
    out = topo.write_level_t_topology_outputs(res, str(tmp_path / "out"))
    for f in ["features_t.csv","topology_quality_report.json","null_placeholder_report.json","artifact_alignment_report.json","omega_event.json","report.md"]:
        assert (tmp_path / "out" / f).exists()
    assert "operational Level T" in (tmp_path / "out" / "report.md").read_text()
    bad = ["proves consciousness","soul proven","afterlife proven","liberation detected","enlightenment proven","nirvana confirmed","ontology solved","ultimate reality","Q equals self","Q equals soul","Q_abs equals suffering","f_dress equals karma"]
    text = (tmp_path / "out" / "report.md").read_text().lower()
    for b in bad:
        assert b.lower() not in text
    assert "promoted" not in json.dumps(json.loads((tmp_path / "out" / "omega_event.json").read_text()))


def test_cli(tmp_path: Path):
    c = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds003969_t_real", "--out", str(tmp_path / "o"), "--mock-fixture"]
    r = subprocess.run(c, capture_output=True, text=True)
    assert r.returncode == 0

    # neither --real nor --mock-fixture: must fail loudly, not silently pick one
    c2 = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds003969_t_real", "--m-windows", str(tmp_path / "nope"), "--out", str(tmp_path / "o2")]
    r2 = subprocess.run(c2, capture_output=True, text=True)
    assert r2.returncode != 0
    assert "One of --real or --mock-fixture is required" in (r2.stdout + r2.stderr)

    # --real with a missing m-windows dir: same missing-input error as --mock-fixture's non-fallback path
    c3 = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds003969_t_real", "--m-windows", str(tmp_path / "nope"), "--out", str(tmp_path / "o3"), "--real"]
    r3 = subprocess.run(c3, capture_output=True, text=True)
    assert r3.returncode != 0
    assert "Run run_ds003969_m_real first or use --mock-fixture" in (r3.stdout + r3.stderr)

    # --real and --mock-fixture together: rejected as contradictory
    c4 = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds003969_t_real", "--out", str(tmp_path / "o4"), "--real", "--mock-fixture"]
    r4 = subprocess.run(c4, capture_output=True, text=True)
    assert r4.returncode != 0
    assert "mutually exclusive" in (r4.stdout + r4.stderr)

    # --real with an existing m-windows table whose source files don't exist: skips
    # gracefully (zeroed row + warning) rather than crashing or fabricating data.
    m_dir = tmp_path / "m_missing_files"
    m_dir.mkdir()
    with (m_dir / "features_m.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(_m_rows()[0].keys()))
        w.writeheader()
        w.writerows(_m_rows())
    c5 = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds003969_t_real", "--m-windows", str(m_dir), "--out", str(tmp_path / "o5"), "--real"]
    r5 = subprocess.run(c5, capture_output=True, text=True)
    assert r5.returncode == 0, r5.stderr
    with (tmp_path / "o5" / "features_t.csv").open(encoding="utf-8") as f:
        out_rows = list(csv.DictReader(f))
    assert len(out_rows) == 2
    assert all(row["q_abs"] == "0.0" for row in out_rows)  # skipped: no real signal available


def test_real_topology_derived_from_signal_not_metadata(tmp_path: Path, monkeypatch):
    """Regression test for the fabrication bug (same as ds005620's): must produce
    different output for different signal content, not a constant derived from
    row_id/metadata text.
    """
    import numpy as np

    f1 = tmp_path / "a.bdf"
    f2 = tmp_path / "b.bdf"
    f1.write_bytes(b"x")
    f2.write_bytes(b"x")

    signals = {
        str(f1): np.array([[1.0, 1.0, 1.0, 1.0] for _ in range(4)]),
        str(f2): np.array([[float(i % 7) for i in range(40)] for _ in range(6)]),
    }
    monkeypatch.setattr(
        "data.bids_ingest.read_window_signal",
        lambda path, *a, **k: signals[path],
    )

    row_a = {"row_id": "ra", "subject_id": "sub-001", "session_id": None, "run_id": None,
              "window_id": "w0", "task_label": "med1breath", "source_file": str(f1),
              "window_start_s": "0", "window_end_s": "1"}
    row_b = {"row_id": "rb", "subject_id": "sub-001", "session_id": None, "run_id": None,
              "window_id": "w1", "task_label": "think1", "source_file": str(f2),
              "window_start_s": "0", "window_end_s": "1"}

    out_a = topo.compute_real_topology_for_window(row_a)
    out_b = topo.compute_real_topology_for_window(row_b)

    assert (out_a.q_abs, out_a.n_valid_triangles) != (out_b.q_abs, out_b.n_valid_triangles)

    row_a_relabeled = {**row_a, "row_id": "totally_different_row_id", "source_file": str(f2)}
    out_relabeled = topo.compute_real_topology_for_window(row_a_relabeled)
    assert out_relabeled.q_abs == out_b.q_abs
    assert out_relabeled.n_valid_triangles == out_b.n_valid_triangles


def test_config_contains_contract():
    t = Path("configs/btc_icft/ds003969_t_real.yaml").read_text(encoding="utf-8")
    for k in ["required_outputs", "topology_columns", "guardrails", "omega_event.json", "no_m_plus_t_benchmark"]:
        assert k in t
