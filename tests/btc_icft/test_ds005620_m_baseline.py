import json
import math
import subprocess
import sys
from pathlib import Path

from sciencer_d.btc_icft.level_m.ds005620_baseline import (
    build_artifact_report,
    build_leakage_report,
    build_mock_ds005620_level_m_rows,
    evaluate_level_m_baseline,
    write_level_m_outputs,
)


def test_mock_rows_exist_and_subjects():
    rows = build_mock_ds005620_level_m_rows()
    assert rows
    assert len({r.subject_id for r in rows}) >= 2


def test_extract_returns_finite_rows():
    rows = build_mock_ds005620_level_m_rows()
    for r in rows:
        assert math.isfinite(r.spectral_power_proxy)
        assert math.isfinite(r.entropy_proxy)
        assert math.isfinite(r.lzc_proxy)
        assert math.isfinite(r.artifact_score)


def test_awake_vs_sedated_metrics():
    rows = build_mock_ds005620_level_m_rows()
    res = evaluate_level_m_baseline(rows, task="awake_vs_sedated")
    assert res.dataset_id == "ds005620"
    assert res.task == "awake_vs_sedated"
    assert res.n_rows > 0
    assert res.n_subjects >= 2
    assert res.auc is None or 0 <= res.auc <= 1
    assert res.brier is None or 0 <= res.brier <= 1
    assert res.ece is None or res.ece >= 0
    assert res.leakage_detected is False


def test_responsive_task_works():
    res = evaluate_level_m_baseline(build_mock_ds005620_level_m_rows(), task="responsive_vs_unresponsive")
    assert res.n_rows > 0


def test_experience_task_works():
    res = evaluate_level_m_baseline(build_mock_ds005620_level_m_rows(), task="experience_vs_no_experience")
    assert res.n_rows > 0


def test_unknown_task_raises():
    try:
        evaluate_level_m_baseline(build_mock_ds005620_level_m_rows(), task="nope")
        assert False
    except ValueError:
        assert True


def test_artifact_report_keys():
    rep = build_artifact_report(build_mock_ds005620_level_m_rows())
    for key in ["mean_artifact_score", "max_artifact_score", "n_artifact_high", "artifact_dominance"]:
        assert key in rep


def test_leakage_report_keys():
    rep = build_leakage_report(build_mock_ds005620_level_m_rows())
    for key in ["n_subjects", "subject_split_possible", "leakage_detected"]:
        assert key in rep


def test_write_outputs(tmp_path: Path):
    res = evaluate_level_m_baseline(build_mock_ds005620_level_m_rows(), task="awake_vs_sedated")
    outs = write_level_m_outputs(res, str(tmp_path))
    required = ["features_m.csv", "metrics_m.json", "artifact_report.json", "leakage_report.json", "omega_event.json", "report.md"]
    for name in required:
        assert Path(outs[name]).exists()

    metrics = json.loads(Path(outs["metrics_m.json"]).read_text())
    assert metrics["dataset_id"] == "ds005620"
    report = Path(outs["report.md"]).read_text().lower()
    assert "operational empirical baseline" in report
    assert ("telemetry" in report) or ("proxy" in report)
    assert "residual testing" in report
    for bad in ["proves consciousness", "soul proven", "afterlife proven", "liberation detected", "ontology solved", "ultimate reality"]:
        assert bad not in report


def test_cli_mock(tmp_path: Path):
    cmd = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_m", "--out", str(tmp_path), "--mock"]
    run = subprocess.run(cmd, capture_output=True, text=True)
    assert run.returncode == 0
    assert (tmp_path / "features_m.csv").exists()
    assert (tmp_path / "metrics_m.json").exists()
    assert (tmp_path / "artifact_report.json").exists()
    assert (tmp_path / "leakage_report.json").exists()
    assert (tmp_path / "omega_event.json").exists()
    assert (tmp_path / "report.md").exists()


def test_cli_real_fails(tmp_path: Path):
    cmd = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_m", "--out", str(tmp_path), "--real"]
    run = subprocess.run(cmd, capture_output=True, text=True)
    assert run.returncode != 0
    msg = (run.stdout + run.stderr)
    assert "Use --mock for offline validation" in msg


def test_config_exists_required_outputs():
    txt = Path("configs/btc_icft/ds005620_m.yaml").read_text()
    for name in ["features_m.csv", "metrics_m.json", "artifact_report.json", "leakage_report.json", "omega_event.json", "report.md"]:
        assert name in txt
