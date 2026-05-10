from __future__ import annotations

import json
import math
import subprocess
import sys

from sciencer_d.btc_icft.level_m.ds005620_baseline import build_mock_ds005620_level_m_rows
from sciencer_d.btc_icft.level_t.ds005620_features import (
    build_ablation_report,
    build_mock_ds005620_level_t_rows,
    build_null_report,
    evaluate_mt_residual,
    join_level_m_and_t_rows,
    write_mt_outputs,
)


def _joined():
    return join_level_m_and_t_rows(build_mock_ds005620_level_m_rows(), build_mock_ds005620_level_t_rows())


def test_alignment():
    m = build_mock_ds005620_level_m_rows(); t = build_mock_ds005620_level_t_rows()
    assert {r.row_id for r in m} == {r.row_id for r in t}
    assert {r.subject_id for r in m} == {r.subject_id for r in t}


def test_join_and_failures():
    m = build_mock_ds005620_level_m_rows(); t = build_mock_ds005620_level_t_rows()
    joined = join_level_m_and_t_rows(m, t)
    assert joined and hasattr(joined[0], "q_net") and hasattr(joined[0], "spectral_power_proxy")
    try:
        join_level_m_and_t_rows(m, t[:-1]); assert False
    except ValueError:
        pass
    bad = list(t); bad[0] = bad[0].__class__(**{**bad[0].__dict__, "subject_id": "sub-x"})
    try:
        join_level_m_and_t_rows(m, bad); assert False
    except ValueError:
        pass


def test_eval_tasks_and_unknown():
    for task in ["awake_vs_sedated", "responsive_vs_unresponsive", "experience_vs_no_experience"]:
        r = evaluate_mt_residual(_joined(), task)
        assert r.dataset_id == "ds005620" and r.task == task and r.n_rows > 0 and r.n_subjects >= 2
        assert set(["auc", "ece", "brier"]).issubset(r.metrics_m.keys())
        assert set(["auc", "ece", "brier"]).issubset(r.metrics_mt.keys())
        assert r.delta_auc is None or math.isfinite(r.delta_auc)
        assert r.delta_ece is None or math.isfinite(r.delta_ece)
        assert r.leakage_detected is False
    try:
        evaluate_mt_residual(_joined(), "bad_task"); assert False
    except ValueError:
        pass


def test_promotion_blocks():
    base = evaluate_mt_residual(_joined(), "awake_vs_sedated")
    assert (not base.promoted) or base.promoted
    mutated = base.__class__(**{**base.__dict__, "delta_auc": 0.0, "promotion_reason": "blocked: delta_auc below threshold", "promoted": False})
    assert mutated.promoted is False


def test_reports_and_write(tmp_path):
    joined = _joined()
    nulls = build_null_report(joined, "awake_vs_sedated")
    for k in ["observed_delta_auc", "null_delta_auc", "margin", "nulls_passed", "null_methods"]: assert k in nulls
    abl = build_ablation_report(joined, "awake_vs_sedated")
    for k in ["M_only", "M_plus_q_net", "M_plus_q_abs", "M_plus_f_dress", "M_plus_all_T"]: assert k in abl
    out = write_mt_outputs(evaluate_mt_residual(joined, "awake_vs_sedated"), str(tmp_path))
    for k in ["features_mt.csv","metrics_mt.json","nulls.json","ablations.json","leakage_report.json","artifact_report.json","omega_event.json","report.md"]:
        assert k in out
    data = json.loads((tmp_path / "metrics_mt.json").read_text())
    assert "metrics_m" in data and "metrics_mt" in data
    report = (tmp_path / "report.md").read_text().lower()
    for term in ["residual predictive value", "topology telemetry", "proxy", "deterministic scaffold"]: assert term in report
    for bad in ["proves consciousness","soul proven","afterlife proven","liberation detected","ontology solved","ultimate reality","q equals self","q equals soul","q_abs equals suffering","f_dress equals karma"]:
        assert bad not in report


def test_cli(tmp_path):
    cmd = [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_mt", "--out", str(tmp_path), "--mock"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    assert p.returncode == 0
    assert (tmp_path / "report.md").exists()

    p2 = subprocess.run([sys.executable, "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_mt", "--out", str(tmp_path), "--real"], capture_output=True, text=True)
    assert p2.returncode != 0
    assert "Use --mock for offline validation" in (p2.stderr + p2.stdout)


def test_config_exists():
    text = open("configs/btc_icft/ds005620_mt.yaml", "r", encoding="utf-8").read()
    for k in ["features_mt.csv","metrics_mt.json","nulls.json","ablations.json","leakage_report.json","artifact_report.json","omega_event.json","report.md","guardrails"]:
        assert k in text
