import json
import math
import subprocess
import sys

from sciencer_d.btc_icft.simulations.validation_runner import run_synthetic_validation


def test_synthetic_output_contract(tmp_path):
    run_synthetic_validation(str(tmp_path))

    metrics_path = tmp_path / "synthetic_metrics.json"
    omega_path = tmp_path / "omega_event.json"
    report_path = tmp_path / "report.md"

    assert metrics_path.exists()
    assert omega_path.exists()
    assert report_path.exists()

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    _ = json.loads(omega_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8").lower()

    expected_keys = {
        "reactive_delta_d_lock",
        "trained_delta_d_lock",
        "random_phase_foam_promotion_safe",
        "random_phase_foam_blocked",
        "random_phase_foam_block_reason",
        "random_phase_foam_q_net",
        "random_phase_foam_q_abs",
        "random_phase_foam_f_dress",
    }
    assert expected_keys.issubset(metrics)
    assert metrics["random_phase_foam_promotion_safe"] is False
    assert metrics["random_phase_foam_blocked"] is True
    assert metrics["random_phase_foam_block_reason"] == "high_q_abs_zero_net_foam"
    assert metrics["random_phase_foam_q_net"] == 0
    assert metrics["random_phase_foam_q_abs"] == 10
    assert math.isfinite(metrics["random_phase_foam_f_dress"])

    assert "telemetry" in report
    assert "proxy" in report
    assert "synthetic scaffold" in report or "scaffold" in report
    banned = [
        "proves consciousness",
        "soul proven",
        "afterlife proven",
        "liberation detected",
        "ontology solved",
        "ultimate reality",
        "q equals self",
        "q equals soul",
        "q_abs equals suffering",
        "f_dress equals karma",
    ]
    for phrase in banned:
        assert phrase not in report


def test_synthetic_validation_cli_smoke(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sciencer_d.btc_icft.pipelines.run_synthetic_validation",
            "--out",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "synthetic_metrics.json").exists()
    assert (tmp_path / "omega_event.json").exists()
    assert (tmp_path / "report.md").exists()
