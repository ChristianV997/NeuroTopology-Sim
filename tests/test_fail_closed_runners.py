"""Fail-closed behaviour of the hypothesis verdict and the missing-input runners.

Regression coverage for three silent-success paths found by running the offline stack:

* governance-schema thresholds (``pass_fail.thresholds``) were never read, so a spec
  could return PASS with nothing evaluated; ``HYP-20260507-001`` declares Qabs_max 2.0 and
  fails on its own declared parameters;
* a spec declaring ``data.mode: openneuro`` was executed as a synthetic run and could still PASS;
* a nonexistent input directory produced an empty, exit-0 result for EEG, qzt and PhysioNet.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _run_spec(tmp_path: Path, text: str) -> dict:
    from pipelines.hypothesis import run

    spec = tmp_path / "spec.yaml"
    spec.write_text(text, encoding="utf-8")
    return run(spec, tmp_path / "out")


def test_governance_thresholds_are_enforced(tmp_path):
    summary = _run_spec(
        tmp_path,
        "id: GOV-STRICT\nclaim_type: K\n"
        "data:\n  mode: synthetic\n  params:\n    N: 16\n    n_steps: 5\n    seed: 0\n"
        "pass_fail:\n  criteria: strict\n  thresholds:\n    Qabs_max: 0.001\n",
    )
    assert summary["verdict"] == "FAIL"
    assert any("Qabs" in failure for failure in summary["threshold_failures"])
    assert summary["metrics_summary"]["N"] == 16  # declared data.params is honoured


def test_documented_threshold_that_passes_gives_pass_with_no_reason(tmp_path):
    summary = _run_spec(
        tmp_path,
        "spec_id: OK-SYN\nthreshold:\n  I_mean_min: 0.0\nsim_params:\n  N: 8\n  n_steps: 3\n  seed: 1\n",
    )
    assert summary["verdict"] == "PASS"
    assert summary["verdict_reason"] is None


def test_spec_without_thresholds_is_ambiguous_not_pass(tmp_path):
    summary = _run_spec(tmp_path, "id: NO-THRESH\npass_fail:\n  thresholds: {}\n")
    assert summary["verdict"] == "ambiguous"
    assert "nothing was evaluated" in summary["verdict_reason"]


def test_declared_openneuro_scope_is_never_reported_as_pass(tmp_path):
    summary = _run_spec(
        tmp_path,
        "id: ON-SCOPE\ndata:\n  mode: openneuro\n  dataset_id: ds002094\n"
        "pass_fail:\n  thresholds:\n    I_mean_min: 0.0\n",
    )
    assert summary["verdict"] == "ambiguous"
    assert "openneuro" in summary["verdict_reason"]
    assert summary["declared_data_mode"] == "openneuro"
    assert summary["data_mode"] is None  # nothing was executed on any data


def test_conflicting_threshold_declarations_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="Conflicting"):
        _run_spec(tmp_path, "threshold:\n  Qabs_max: 2.0\npass_fail:\n  thresholds:\n    Qabs_max: 5.0\n")


def test_bundled_governed_spec_is_not_pass_on_its_declared_parameters(tmp_path):
    from pipelines.hypothesis import run

    summary = run(REPO / "governance" / "specs" / "HYP-20260507-001.yaml", tmp_path / "out")
    assert summary["verdict"] == "FAIL"
    assert any("Qabs" in failure for failure in summary["threshold_failures"])


def test_eeg_missing_input_directory_raises(tmp_path):
    from pipelines.run_eeg import run as run_eeg

    with pytest.raises(FileNotFoundError, match="does not exist"):
        run_eeg(tmp_path / "absent", tmp_path / "out.csv", dataset="ds002094")


def test_qzt_missing_checkpoint_directory_raises(tmp_path):
    from pipelines.run_qzt import run as run_qzt

    with pytest.raises(FileNotFoundError, match="does not exist"):
        run_qzt(tmp_path / "absent", tmp_path / "out")


def test_physionet_missing_input_directory_raises(tmp_path):
    from pipelines.run_physionet import run as run_physionet

    with pytest.raises(FileNotFoundError, match="does not exist"):
        run_physionet(tmp_path / "absent", tmp_path / "out.csv")


def test_cli_eeg_missing_input_exits_nonzero(tmp_path):
    proc = subprocess.run(
        [sys.executable, "main.py", "--mode", "eeg", "--dataset", "ds002094",
         "--input", str(tmp_path / "absent"), "--output", str(tmp_path / "out.csv")],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode != 0
    assert "does not exist" in proc.stderr


def test_external_file_connector_missing_path_raises(tmp_path):
    from external.ecosystem import FileSensorConnector

    with pytest.raises(FileNotFoundError, match="does not exist"):
        list(FileSensorConnector(tmp_path / "absent.jsonl").stream())


def test_external_run_with_missing_sensor_file_is_recorded_failed(tmp_path):
    import sqlite3

    from pipelines.run_external import run as run_external

    config = tmp_path / "config.yaml"
    config.write_text(
        "external:\n  connectors:\n    - type: file\n"
        f"      params:\n        path: {tmp_path / 'absent.jsonl'}\n        sensor_id: s\n",
        encoding="utf-8",
    )
    db = tmp_path / "runs.sqlite"
    with pytest.raises(FileNotFoundError):
        run_external(config, tmp_path / "out.csv", db)
    status = sqlite3.connect(db).execute("SELECT status FROM runs").fetchone()[0]
    assert status == "failed"


def test_cross_domain_missing_results_root_raises(tmp_path):
    from pipelines.run_cross_domain import run as run_cross_domain

    with pytest.raises(FileNotFoundError, match="does not exist"):
        run_cross_domain(tmp_path / "absent", tmp_path / "cross.csv")
