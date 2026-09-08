"""Loader round-trips and the CLI wiring, exercised as a real subprocess
against the fixture files -- no network anywhere."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.release_scientific_audit import loaders

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).parent / "fixtures"
_SCRIPT = _ROOT / "scripts" / "audit_integrated_release.py"


def test_loader_round_trips_clean_fixture():
    audit_input = loaders.audit_input_from_file(_FIXTURES / "clean_engineering_only.json")
    assert audit_input.scientific_gate_report is not None
    assert audit_input.scientific_gate_report.k_gate_threshold == 100.0
    assert len(audit_input.provenance_records) == 1
    assert audit_input.provenance_records[0].component == "eeg_pipeline"


def test_loader_handles_absent_optional_sections(tmp_path):
    minimal = tmp_path / "minimal.json"
    minimal.write_text(json.dumps({}), encoding="utf-8")
    audit_input = loaders.audit_input_from_file(minimal)
    assert audit_input.scientific_gate_report is None
    assert audit_input.provenance_records == ()
    assert audit_input.test_summary is None


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_SCRIPT), *args], capture_output=True, text=True, timeout=60)


def test_cli_runs_on_clean_fixture_and_exits_zero(tmp_path):
    clean_dashboard = tmp_path / "dashboard_src"
    clean_dashboard.mkdir()
    (clean_dashboard / "app.py").write_text("import json\n", encoding="utf-8")
    result = _run_cli(
        "--input", str(_FIXTURES / "clean_engineering_only.json"),
        "--dashboard-src", str(clean_dashboard),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["release_decision"] == "RELEASE_READY"


def test_cli_exits_nonzero_on_blocked_fixture():
    result = _run_cli("--input", str(_FIXTURES / "failed_ci.json"))
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["release_decision"] == "BLOCKED_BY_TESTS"


def test_cli_writes_json_and_markdown_to_output_dir(tmp_path):
    out_dir = tmp_path / "out"
    result = _run_cli("--input", str(_FIXTURES / "timed_out_tests.json"), "--output-dir", str(out_dir))
    assert result.returncode == 1, result.stderr
    assert (out_dir / "report.json").exists()
    assert (out_dir / "report.md").exists()
    payload = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["release_decision"] == "BLOCKED_BY_TESTS"
