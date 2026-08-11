"""Subprocess CLI tests for `python -m external_tools.export_registry`,
run against the real committed seed registry. No network access.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "external_tools.export_registry", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def test_cli_validate_succeeds():
    result = _run_cli("--validate")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["tools"] >= 30


def test_cli_list_succeeds():
    result = _run_cli("--list")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) >= 30
    assert {"tool_id", "name", "category", "priority"} <= set(payload[0])


def test_cli_priority_filter():
    result = _run_cli("--priority", "P0")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert all(t["priority"] == "P0" for t in payload)
    assert len(payload) > 0


def test_cli_integration_mode_filter():
    result = _run_cli("--integration-mode", "reference_only")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert all(t["integration_mode"] == "reference_only" for t in payload)
    assert len(payload) > 0


def test_cli_category_filter():
    result = _run_cli("--category", "topology_tda")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert all(t["category"] == "topology_tda" for t in payload)
    assert len(payload) > 0


def test_cli_recommended_next_excludes_unsafe_tools():
    result = _run_cli("--recommended-next")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    tool_ids = {t["tool_id"] for t in payload}
    assert "giotto-tda" not in tool_ids
    assert "eeglab" not in tool_ids
    assert "fieldtrip" not in tool_ids
    assert "brainstorm" not in tool_ids
    for t in payload:
        assert t["integration_mode"] not in ("reference_only", "avoid_core")
        assert t["license_risk"] not in ("proprietary_high", "unknown_high")


def test_cli_recommended_next_includes_high_value_safe_candidates():
    result = _run_cli("--recommended-next")
    payload = json.loads(result.stdout)
    tool_ids = {t["tool_id"] for t in payload}
    assert "mne-python" in tool_ids
    assert "gudhi" in tool_ids
    assert "networkx" in tool_ids


def test_cli_recommended_next_respects_limit():
    result = _run_cli("--recommended-next", "--limit", "3")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload) == 3


def test_cli_out_writes_validated_snapshot(tmp_path):
    out_path = tmp_path / "registry.json"
    result = _run_cli("--out", str(out_path))
    assert result.returncode == 0, result.stderr
    assert out_path.exists()
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(written["tools"]) >= 30


def test_cli_fails_clearly_on_missing_registry(tmp_path):
    result = _run_cli("--registry", str(tmp_path / "does_not_exist.json"), "--validate")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_no_action_prints_help_and_fails():
    result = _run_cli()
    assert result.returncode == 1
