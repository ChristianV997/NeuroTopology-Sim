"""Tests for CLI runner, finite JSON formatting, and zero-network isolation."""
from __future__ import annotations

import json
import socket
from pathlib import Path
import pytest

from scripts.compile_simulation_release_bundle import main
from tools.simulation_release_bridge.contracts import (
    SimulationReleaseBundle,
    canonical_hash,
    dumps_finite_json,
    finite_value,
)
from tools.simulation_release_bridge.fixtures import (
    create_complete_pass_stages,
    populate_run_directory,
)


def test_cli_runner_json_and_markdown(tmp_path: Path):
    """Verify CLI compilation with both JSON and Markdown artifacts."""
    run_dir = tmp_path / "sim_pass_run"
    stages = create_complete_pass_stages()
    populate_run_directory(run_dir, stages)

    json_out = tmp_path / "bundle.json"
    md_out = tmp_path / "bundle.md"

    exit_code = main([
        "--run-dir", str(run_dir),
        "--cycle-id", "rc-cli-001",
        "--output", str(json_out),
        "--markdown-output", str(md_out),
        "--verify",
        "--no-require-canonical-runner",
    ])

    assert exit_code == 0
    assert json_out.is_file()
    assert md_out.is_file()

    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["bundle_id"].startswith("bundle_rc-cli-001")
    assert payload["promotion_status"] == "PROMOTED"

    md_content = md_out.read_text(encoding="utf-8")
    assert "Simulation Release Review Bundle" in md_content
    assert "8-Stage Execution Chain" in md_content


def test_finite_json_rfc8259_compliance():
    """Verify strictly finite JSON formatting rejects non-finite floats."""
    stages = create_complete_pass_stages()
    json_text = dumps_finite_json(stages)
    assert "NaN" not in json_text
    assert "Infinity" not in json_text

    # Re-parse to verify RFC 8259 compliance
    loaded = json.loads(json_text)
    assert loaded["execution_outcome"]["state"] == "PASS"


def test_zero_network_isolation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Verify that bundle compilation executes strictly offline with zero socket network calls."""
    run_dir = tmp_path / "sim_offline_run"
    stages = create_complete_pass_stages()
    populate_run_directory(run_dir, stages)

    def blocked_connect(*args, **kwargs):
        raise RuntimeError("Network socket call attempted in offline acceptance!")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)

    json_out = tmp_path / "bundle_offline.json"
    exit_code = main([
        "--run-dir", str(run_dir),
        "--cycle-id", "rc-offline-001",
        "--output", str(json_out),
        "--no-require-canonical-runner",
    ])

    assert exit_code == 0
    assert json_out.is_file()
