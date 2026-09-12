"""Subprocess integration tests for compile_research_cycle_evidence.py CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import pytest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


@pytest.fixture
def sample_run_dir(tmp_path: Path) -> Path:
    run = tmp_path / "cli_sample_run"
    _write_json(
        run / "RunRecord.json",
        {
            "run_id": "run_cli_001",
            "created_at": "2026-09-11T00:00:00Z",
            "source": "cli_test_generator",
            "data_mode": "synthetic",
            "synthetic": True,
            "git_commit": "d4dc5fc",
        },
    )
    _write_json(run / "summary.json", {"status": "complete", "loss": 0.1})
    _write_json(run / "metrics.json", {"accuracy": 0.99})
    _write_json(run / "validation_report.json", {"status": "complete", "checks_passed": True})
    return run


def test_cli_json_output(sample_run_dir: Path) -> None:
    """Ensure compile_research_cycle_evidence.py outputs valid JSON and exits 0 on complete run."""
    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "compile_research_cycle_evidence.py"
    cmd = [
        sys.executable,
        str(script_path),
        "--run-dir", str(sample_run_dir),
        "--cycle-id", "rc-cycle-cli-test",
        "--verify",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["cycle_id"] == "rc-cycle-cli-test"
    assert data["status"] == "COMPLETE"
    assert "checksum" in data


def test_cli_markdown_output(sample_run_dir: Path) -> None:
    """Ensure compile_research_cycle_evidence.py outputs valid Markdown format."""
    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "compile_research_cycle_evidence.py"
    cmd = [
        sys.executable,
        str(script_path),
        "--run-dir", str(sample_run_dir),
        "--format", "markdown",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "# Research Cycle Evidence Bridge Record" in proc.stdout
    assert "run_cli_001" in proc.stdout


def test_cli_missing_run_dir_error(tmp_path: Path) -> None:
    """Ensure non-existent run directory exits with code 2."""
    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "compile_research_cycle_evidence.py"
    non_existent = tmp_path / "does_not_exist"
    cmd = [
        sys.executable,
        str(script_path),
        "--run-dir", str(non_existent),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 2
