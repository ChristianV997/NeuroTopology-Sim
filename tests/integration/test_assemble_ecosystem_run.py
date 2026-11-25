"""End-to-end tests for scripts/assemble_ecosystem_run.py.

Covers, per the ecosystem-integration mission's explicit test list:
  - synthetic dry run
  - invalid input
  - missing provenance
  - no-network default
  - RunRecordV1 round-trip
  - error versus inconclusive classification

("all optional dependencies absent" is covered by test_capabilities.py /
test_run_plan.py at the unit level, and is additionally the *actual*
condition of the sandbox this suite runs in for pandas/sklearn/mne/ripser/
gudhi/boto3/statsmodels — see configs/integration/dependency_matrix.yaml's
capability check. "Deterministic manifest" is covered by
test_artifact_manifest.py; "graph/spatial field separation" by
test_quality_gate.py and test_topology_field_separation.py; "dashboard
read-only compatibility" / "no solver import from dashboard code" by
test_dashboard_isolation.py.)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from runs.run_record import read_json
from scripts.assemble_ecosystem_run import assemble


def test_synthetic_dry_run_produces_not_supported_never_pass(tmp_path):
    result = assemble(
        data_mode="synthetic", input_path=None, output_dir=tmp_path / "out",
        seed=1, n_samples=256, dataset_id="synthetic-dry-run",
    )
    assert result["status"] in {"NOT_SUPPORTED", "INCONCLUSIVE"}
    assert result["status"] != "PASS", (
        "synthetic data must never surface as an empirical PASS at the "
        "integration layer (hard guardrail)"
    )
    assert result["run_id"] is not None


def test_synthetic_dry_run_makes_no_network_request(tmp_path, monkeypatch):
    """Assert the default (non-live) synthetic path never touches sockets."""
    import socket

    def _forbidden(*args, **kwargs):
        raise AssertionError("socket.socket() was called during a default (no --live) run")

    monkeypatch.setattr(socket, "socket", _forbidden)
    result = assemble(
        data_mode="synthetic", input_path=None, output_dir=tmp_path / "out",
        seed=2, dataset_id="no-network-check",
    )
    assert result["run_id"] is not None


def test_invalid_input_path_is_refused_at_preflight_as_error(tmp_path):
    result = assemble(
        data_mode="empirical_local",
        input_path=tmp_path / "does_not_exist.csv",
        output_dir=tmp_path / "out",
        dataset_id="invalid-input",
    )
    assert result["status"] == "ERROR"
    assert result["run_id"] is None
    assert result["preflight"]["ok"] is False


def test_empirical_mode_without_input_path_is_inconclusive_not_pass(tmp_path):
    """empirical_local declared but no --input-path: ingestion cannot
    proceed, so the run must classify as INCONCLUSIVE, never PASS or a
    silent success."""
    result = assemble(
        data_mode="empirical_local", input_path=None, output_dir=tmp_path / "out",
        dataset_id="missing-input-path",
    )
    assert result["status"] == "INCONCLUSIVE"
    record = read_json(Path(result["artifacts"]["run_record"]))
    assert record.verdict == "INCONCLUSIVE"


def test_short_empirical_csv_below_minimum_samples_is_inconclusive(tmp_path):
    """A CSV too short for sim.pitnn.ingest_empirical's own >=8-sample
    guard must surface as INCONCLUSIVE at this integration layer, not
    crash the whole process uncaught."""
    csv_path = tmp_path / "too_short.csv"
    csv_path.write_text("1.0\n2.0\n3.0\n", encoding="utf-8")
    result = assemble(
        data_mode="empirical_local", input_path=csv_path, output_dir=tmp_path / "out",
        dataset_id="short-csv",
    )
    assert result["status"] in {"INCONCLUSIVE", "ERROR"}
    assert result["status"] != "PASS"


def test_no_network_refused_when_live_flag_set_without_env_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("NTS_INTEGRATION_ALLOW_NETWORK", raising=False)
    result = assemble(
        data_mode="synthetic", input_path=None, output_dir=tmp_path / "out",
        dataset_id="live-without-optin", live=True, allow_network=True,
    )
    assert result["status"] == "ERROR"
    assert result["run_id"] is None
    assert any("network" in e for e in result["preflight"]["errors"])


def test_run_record_v1_round_trip(tmp_path):
    result = assemble(
        data_mode="synthetic", input_path=None, output_dir=tmp_path / "out",
        seed=7, dataset_id="round-trip",
    )
    record_path = Path(result["artifacts"]["run_record"])
    record = read_json(record_path)
    assert record.run_id == result["run_id"]
    assert record.run_kind == "ecosystem_integration"
    assert record.verdict == result["status"]
    assert record.data_mode == "synthetic"
    assert record.dataset_id == "round-trip"
    # Round-trip through to_dict/from_dict once more for good measure.
    from runs.run_record import RunRecordV1

    reloaded = RunRecordV1.from_dict(json.loads(record_path.read_text(encoding="utf-8")))
    assert reloaded.to_dict() == record.to_dict()


def test_same_inputs_produce_the_same_run_id(tmp_path):
    result1 = assemble(
        data_mode="synthetic", input_path=None, output_dir=tmp_path / "out1",
        seed=5, n_samples=128, dataset_id="repeatable",
    )
    result2 = assemble(
        data_mode="synthetic", input_path=None, output_dir=tmp_path / "out2",
        seed=5, n_samples=128, dataset_id="repeatable",
    )
    assert result1["run_id"] == result2["run_id"]


def test_quality_report_artifact_is_valid_json_with_required_keys(tmp_path):
    result = assemble(
        data_mode="synthetic", input_path=None, output_dir=tmp_path / "out",
        seed=9, dataset_id="quality-report-shape",
    )
    payload = json.loads(Path(result["artifacts"]["quality_report"]).read_text(encoding="utf-8"))
    assert payload["schema"] == "NTS.IntegrationQualityReport.v1"
    assert payload["status"] in {"PASS", "NOT_SUPPORTED", "INCONCLUSIVE", "ERROR"}
    assert "checks" in payload


def test_manifest_references_every_written_artifact(tmp_path):
    result = assemble(
        data_mode="synthetic", input_path=None, output_dir=tmp_path / "out",
        seed=11, dataset_id="manifest-refs",
    )
    manifest = json.loads(Path(result["artifacts"]["manifest"]).read_text(encoding="utf-8"))
    referenced = {entry["relative_path"] for entry in manifest["artifacts"]}
    assert referenced == {"RunRecord.json", "quality_report.json", "summary.md"}
    assert "environment" in manifest["metadata"]
