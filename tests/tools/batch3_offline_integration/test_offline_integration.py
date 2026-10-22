"""Tests for Batch 3 offline integration harness."""
from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tools.batch3_offline_integration.allowlist import STAGE_ORDER, STAGE_SPECS, assert_stage_allowlisted
from tools.batch3_offline_integration.runner import run_offline_integration, write_report
from tools.batch3_offline_integration.schema import RESULT_LABEL_ENGINEERING, StageOutcome
from tools.batch3_offline_integration.serialization import dumps

REPO = Path(__file__).resolve().parents[3]


def test_allowlist_is_fixed_and_ordered():
    assert STAGE_ORDER[0] == "load_synthetic_fixture"
    assert STAGE_ORDER[-1] == "optional_artifact_lineage"
    assert [s.order for s in STAGE_SPECS] == sorted(s.order for s in STAGE_SPECS)
    with pytest.raises(KeyError):
        assert_stage_allowlisted("not_a_real_stage")


def test_happy_path_stage_order_and_engineering_only():
    report = run_offline_integration(fixture_name="workflow_request.json")
    assert report["stage_order_ok"] is True
    assert report["stage_order_observed"] == list(STAGE_ORDER)
    assert report["workflow_executed_successfully"] is True
    assert report["scientific_validity_claimed"] is False
    assert report["scientific_pass_emitted"] is False
    assert report["network_accessed"] is False
    assert report["result_label"] == RESULT_LABEL_ENGINEERING
    assert report["release_decision"] == "SYNTHETIC_ONLY"
    # Fixture producer stage never claims upstream producer ran.
    load = next(s for s in report["stages"] if s["stage_id"] == "load_synthetic_fixture")
    assert load["actual_upstream_producer_ran"] is False
    assert load["execution_mode"] == "fixture_producer"
    # Optional lineage absent → marked substitute / skip, not silent success.
    opt = next(s for s in report["stages"] if s["stage_id"] == "optional_artifact_lineage")
    assert opt["outcome"] == StageOutcome.SKIPPED_OPTIONAL_ABSENT.value
    assert opt["actual_upstream_producer_ran"] is False
    assert opt["outputs"]["missing_dependency"] == "prior_run_dir"


def test_incomplete_plan_fails_and_stops_downstream():
    report = run_offline_integration(fixture_name="incomplete_plan_request.json")
    assert report["workflow_executed_successfully"] is False
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["plan_quality"]["outcome"] == StageOutcome.FAILED.value
    # preflight depends on plan_quality; must not run after required upstream fail
    assert by_id["preflight"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert by_id["registry_probe"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert by_id["release_evaluate"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    # claim_gate only depends on load — may still run
    assert by_id["claim_gate"]["outcome"] in {
        StageOutcome.SUCCEEDED.value,
        StageOutcome.FAILED.value,
    }


def test_forced_stage_failure_propagates_safe_stop():
    report = run_offline_integration(
        fixture_name="workflow_request.json",
        force_fail_stage="claim_gate",
    )
    assert report["workflow_executed_successfully"] is False
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["claim_gate"]["outcome"] == StageOutcome.FAILED.value
    assert by_id["claim_gate"]["error"] == "forced_stage_failure"
    assert by_id["preflight"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert "preflight" in report["stages_skipped_upstream_failed"]
    # Downstream required stages must not have executed allowlisted callables.
    assert by_id["preflight"]["actual_upstream_producer_ran"] is False
    assert by_id["release_evaluate"]["actual_upstream_producer_ran"] is False


def test_nonfinite_fixture_rejected():
    report = run_offline_integration(fixture_name="nonfinite_probe.json")
    assert report["workflow_executed_successfully"] is False
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["load_synthetic_fixture"]["outcome"] == StageOutcome.REJECTED_NONFINITE.value
    assert by_id["plan_quality"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value


def test_schema_incompatibility_rejected(monkeypatch):
    from tools.batch3_offline_integration import stages as stages_mod

    def boom(*_a, **_k):
        raise TypeError("incompatible")

    monkeypatch.setattr(
        "tools.research_plan_quality.models.ResearchPlan.from_dict",
        boom,
    )
    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["plan_quality"]["outcome"] == StageOutcome.REJECTED_SCHEMA.value
    assert report["workflow_executed_successfully"] is False


def test_deterministic_rerun_checksum():
    a = run_offline_integration(fixture_name="workflow_request.json")
    b = run_offline_integration(fixture_name="workflow_request.json")
    assert a["report_sha256"] == b["report_sha256"]
    assert dumps(a) == dumps(b)


def test_no_network_behavior(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    report = run_offline_integration(fixture_name="workflow_request.json")
    assert report["network_accessed"] is False
    assert report["workflow_executed_successfully"] is True


def test_optional_dependency_absence_marked():
    report = run_offline_integration(fixture_name="workflow_request.json", prior_run_dir=None)
    opt = next(s for s in report["stages"] if s["stage_id"] == "optional_artifact_lineage")
    assert "optional_artifact_lineage" in report["stages_fixture_substituted_or_producer"]
    assert opt["outputs"]["producer"] == "fixture_substitute"
    assert opt["outputs"]["actual_upstream_producer_ran"] is False


def test_invalid_missing_fixture():
    report = run_offline_integration(fixture_name="does_not_exist.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["load_synthetic_fixture"]["outcome"] == StageOutcome.REJECTED_INVALID_INPUT.value
    assert report["workflow_executed_successfully"] is False


@pytest.mark.parametrize("escape_kind", ["absolute", "traversal"])
def test_fixture_path_escape_is_rejected_without_reading_external_content(tmp_path: Path, escape_kind: str):
    marker = "SYNTHETIC_PATH_ESCAPE_MARKER_381"
    external_fixture = tmp_path / "outside_fixture.json"
    external_fixture.write_text(json.dumps({"request": {"marker": marker}}), encoding="utf-8")
    fixture_root = REPO / "tools" / "batch3_offline_integration" / "fixtures"
    fixture_name = (
        str(external_fixture)
        if escape_kind == "absolute"
        else os.path.relpath(external_fixture, fixture_root)
    )

    report = run_offline_integration(fixture_name=fixture_name)
    by_id = {s["stage_id"]: s for s in report["stages"]}

    assert by_id["load_synthetic_fixture"]["outcome"] == StageOutcome.REJECTED_INVALID_INPUT.value
    assert report["workflow_executed_successfully"] is False
    assert marker not in dumps(report)
    assert str(external_fixture) not in dumps(report)


def test_cli_fixture_path_escape_has_stable_nonzero_result(tmp_path: Path):
    marker = "SYNTHETIC_CLI_PATH_ESCAPE_MARKER_381"
    external_fixture = tmp_path / "cli_outside_fixture.json"
    external_fixture.write_text(json.dumps({"request": {"marker": marker}}), encoding="utf-8")
    fixture_root = REPO / "tools" / "batch3_offline_integration" / "fixtures"
    traversal_name = os.path.relpath(external_fixture, fixture_root)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.batch3_offline_integration",
            "--fixture-name",
            traversal_name,
            "--json-stdout",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    by_id = {s["stage_id"]: s for s in payload["stages"]}
    assert by_id["load_synthetic_fixture"]["outcome"] == StageOutcome.REJECTED_INVALID_INPUT.value
    assert marker not in proc.stdout
    assert marker not in proc.stderr
    assert str(external_fixture) not in proc.stdout


def test_fixture_size_limit_is_enforced(tmp_path: Path, monkeypatch):
    from tools.batch3_offline_integration import fixture_producers

    monkeypatch.setattr(fixture_producers, "FIXTURE_DIR", tmp_path)
    monkeypatch.setattr(fixture_producers, "MAX_FIXTURE_BYTES", 16, raising=False)
    (tmp_path / "workflow_request.json").write_text('{"request":"' + "x" * 64 + '"}', encoding="utf-8")

    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}

    assert by_id["load_synthetic_fixture"]["outcome"] == StageOutcome.REJECTED_INVALID_INPUT.value
    assert report["workflow_executed_successfully"] is False


@pytest.mark.parametrize(
    "fixture_contents",
    ["{\"request\":", "{\"request\":{},\"request\":{\"ambiguous\":true}}", "{\"value\":NaN}"],
)
def test_malformed_ambiguous_or_nonfinite_fixture_is_rejected(
    tmp_path: Path, monkeypatch, fixture_contents: str
):
    from tools.batch3_offline_integration import fixture_producers

    monkeypatch.setattr(fixture_producers, "FIXTURE_DIR", tmp_path)
    (tmp_path / "workflow_request.json").write_text(fixture_contents, encoding="utf-8")

    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}

    assert by_id["load_synthetic_fixture"]["outcome"] == StageOutcome.REJECTED_INVALID_INPUT.value
    assert report["workflow_executed_successfully"] is False


def test_fixture_symlink_escape_is_rejected(tmp_path: Path, monkeypatch):
    from tools.batch3_offline_integration import fixture_producers

    fixture_root = tmp_path / "fixtures"
    fixture_root.mkdir()
    external_fixture = tmp_path / "outside.json"
    external_fixture.write_text('{"request":{"marker":"SYNTHETIC_SYMLINK_ESCAPE_381"}}', encoding="utf-8")
    link = fixture_root / "workflow_request.json"
    try:
        link.symlink_to(external_fixture)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable on this platform: {type(exc).__name__}")
    monkeypatch.setattr(fixture_producers, "FIXTURE_DIR", fixture_root)

    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}

    assert by_id["load_synthetic_fixture"]["outcome"] == StageOutcome.REJECTED_INVALID_INPUT.value
    assert report["workflow_executed_successfully"] is False
    assert "SYNTHETIC_SYMLINK_ESCAPE_381" not in dumps(report)


def test_empty_stage_selection_is_not_reported_as_success():
    with pytest.raises(ValueError, match="at least one"):
        run_offline_integration(stage_ids=[])


def test_optional_only_selection_cannot_report_success_when_prerequisite_is_missing():
    report = run_offline_integration(stage_ids=["optional_artifact_lineage"])

    assert report["stages"][0]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert report["workflow_executed_successfully"] is False


def test_partial_required_stage_selection_cannot_report_workflow_success():
    report = run_offline_integration(stage_ids=["load_synthetic_fixture"])

    assert report["stages"][0]["outcome"] == StageOutcome.SUCCEEDED.value
    assert len(report["stages"]) == 1
    assert report["workflow_executed_successfully"] is False


def test_stage_selection_is_bounded_by_fixed_allowlist():
    with pytest.raises(ValueError, match="maximum"):
        run_offline_integration(stage_ids=list(STAGE_ORDER) * 100)


def test_prior_run_directory_is_not_scanned_by_offline_fixture_runner(tmp_path: Path, monkeypatch):
    from tools.simulation_artifacts import extractor

    marker = "SYNTHETIC_PRIOR_RUN_MARKER_381"
    (tmp_path / "RunRecord.json").write_text(
        json.dumps({"run_id": "synthetic-381", "data_mode": "synthetic", "synthetic": True,
                    "subject_marker": marker}),
        encoding="utf-8",
    )
    calls = []

    def record_scan(path):
        calls.append(path)
        raise AssertionError("offline fixture runner must not scan caller directories")

    monkeypatch.setattr(extractor, "extract_run", record_scan)
    report = run_offline_integration(
        fixture_name="workflow_request.json",
        prior_run_dir=str(tmp_path),
    )
    lineage = next(s for s in report["stages"] if s["stage_id"] == "optional_artifact_lineage")

    assert calls == []
    assert lineage["outcome"] == StageOutcome.REJECTED_INVALID_INPUT.value
    assert lineage["actual_upstream_producer_ran"] is False
    assert report["workflow_executed_successfully"] is False
    assert marker not in dumps(report)


def test_cli_prior_run_directory_is_explicitly_rejected(tmp_path: Path):
    marker = "SYNTHETIC_CLI_PRIOR_RUN_MARKER_381"
    (tmp_path / "RunRecord.json").write_text(
        json.dumps({"run_id": "synthetic-381", "synthetic": True, "subject_marker": marker}),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.batch3_offline_integration",
            "--prior-run-dir",
            str(tmp_path),
            "--json-stdout",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    lineage = next(s for s in payload["stages"] if s["stage_id"] == "optional_artifact_lineage")
    assert lineage["error"] == "caller_run_directory_not_scanned"
    assert payload["caller_run_data_scanned"] is False
    assert marker not in proc.stdout + proc.stderr
    assert str(tmp_path) not in proc.stdout


def test_unknown_forced_failure_stage_is_rejected():
    with pytest.raises(ValueError, match="fixed allowlist"):
        run_offline_integration(force_fail_stage="not_a_real_stage")


def test_cli_unknown_forced_failure_stage_has_argparse_error():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.batch3_offline_integration",
            "--force-fail-stage",
            "not_a_real_stage",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "invalid choice" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_write_report_and_cli(tmp_path: Path):
    report = run_offline_integration(fixture_name="workflow_request.json")
    out = tmp_path / "report.json"
    write_report(report, str(out))
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["report_sha256"] == report["report_sha256"]
    assert "NaN" not in out.read_text(encoding="utf-8")
    assert math.isfinite(1.0)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.batch3_offline_integration",
            "--fixture-name",
            "workflow_request.json",
            "--output",
            str(tmp_path / "cli.json"),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    cli_payload = json.loads((tmp_path / "cli.json").read_text(encoding="utf-8"))
    assert cli_payload["workflow_executed_successfully"] is True

    proc_fail = subprocess.run(
        [
            sys.executable,
            "scripts/run_batch3_offline_integration.py",
            "--fixture-name",
            "incomplete_plan_request.json",
            "--output",
            str(tmp_path / "cli_fail.json"),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_fail.returncode == 1


def test_does_not_overlap_batch2_paths():
    # Guard: this package must not import or own Batch 2 MOABB/DANDI lanes.
    report = run_offline_integration(fixture_name="workflow_request.json")
    blob = dumps(report)
    assert "moabb_protocol_conformance" not in blob
    assert "dandi_nwb" not in blob
