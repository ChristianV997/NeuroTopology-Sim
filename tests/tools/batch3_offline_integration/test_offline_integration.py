"""Tests for Batch 3 offline integration harness."""
from __future__ import annotations

import json
import math
import os
import signal
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
    except (OSError, NotImplementedError):
        link.write_text('{"request":{"marker":"SYNTHETIC_SYMLINK_ESCAPE_381"}}', encoding="utf-8")
        orig_is_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda self: True if self == link else orig_is_symlink(self),
        )
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


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_report_serialization_rejects_nonfinite_values_before_writing(tmp_path: Path, nonfinite: float):
    from tools.batch3_offline_integration.serialization import canonical_bytes

    invalid = {"nested": [{"metric": nonfinite}]}
    with pytest.raises(ValueError, match="non-finite"):
        dumps(invalid)
    with pytest.raises(ValueError, match="non-finite"):
        canonical_bytes(invalid)

    destination = tmp_path / "invalid-report.json"
    with pytest.raises(ValueError, match="non-finite"):
        write_report(invalid, str(destination))
    assert not destination.exists()


def test_does_not_overlap_batch2_paths():
    # Guard: this package must not import or own Batch 2 MOABB/DANDI lanes.
    report = run_offline_integration(fixture_name="workflow_request.json")
    blob = dumps(report)
    assert "moabb_protocol_conformance" not in blob
    assert "dandi_nwb" not in blob


def test_duplicate_stage_ids_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        run_offline_integration(
            stage_ids=["load_synthetic_fixture", "load_synthetic_fixture"],
        )


def test_plan_quality_rejects_unrecognized_or_missing_status(monkeypatch):
    from tools.batch3_offline_integration import stages as stages_mod

    orig_resolve = stages_mod.resolve_callable

    def fake_resolve(spec):
        if spec.stage_id == "plan_quality":
            return (lambda _plan: {"overall_status": "UNRECOGNIZED_STATUS", "plan_id": "P-1"}), None
        return orig_resolve(spec)

    monkeypatch.setattr(stages_mod, "resolve_callable", fake_resolve)
    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["plan_quality"]["outcome"] == StageOutcome.FAILED.value
    assert by_id["preflight"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert report["workflow_executed_successfully"] is False


def test_plan_quality_rejects_missing_plan_object(monkeypatch):
    from tools.batch3_offline_integration import stages as stages_mod

    monkeypatch.setattr(
        stages_mod,
        "load_workflow_request",
        lambda fixture_name: {
            "producer": "fixture_producer",
            "fixture_name": fixture_name,
            "fixture_sha256": "0" * 64,
            "request": {"claim": {"claim_id": "C1", "text": "t", "claim_class": "engineering_fact"}},
            "actual_upstream_producer_ran": False,
        },
    )
    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["plan_quality"]["outcome"] == StageOutcome.REJECTED_INVALID_INPUT.value
    assert by_id["preflight"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert report["workflow_executed_successfully"] is False


@pytest.mark.parametrize("bad_decision", ["CLAIM_NOT_COMPARABLE", "UNRECOGNIZED_DECISION", None])
def test_claim_gate_rejects_non_admissible_or_unknown_decisions(monkeypatch, bad_decision):
    from tools.batch3_offline_integration import stages as stages_mod

    orig_resolve = stages_mod.resolve_callable

    def fake_resolve(spec):
        if spec.stage_id == "claim_gate":
            return (lambda _claim: {"decision": bad_decision, "scientific_pass": False}), None
        return orig_resolve(spec)

    monkeypatch.setattr(stages_mod, "resolve_callable", fake_resolve)
    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["claim_gate"]["outcome"] == StageOutcome.FAILED.value
    assert by_id["preflight"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert report["workflow_executed_successfully"] is False


@pytest.mark.parametrize(
    "bad_decision",
    [
        "EVIDENCE_INCOMPLETE",
        "PROVENANCE_FAILURE",
        "ARTIFACT_FAILURE",
        "VALIDATION_FAILURE",
        "RESOURCE_FAILURE",
        "NETWORK_POLICY_FAILURE",
        "INFRASTRUCTURE_BLOCKED",
        "NOT_COMPARABLE",
        "UNKNOWN_DECISION",
        None,
    ],
)
def test_release_evaluate_rejects_failure_or_unknown_decisions(monkeypatch, bad_decision):
    from tools.batch3_offline_integration import stages as stages_mod

    orig_resolve = stages_mod.resolve_callable

    def fake_resolve(spec):
        if spec.stage_id == "release_evaluate":
            return (
                lambda _bundle, **_kw: {
                    "decision": bad_decision,
                    "evidence_class": "research_cycle_release_operational",
                    "synthetic_flag": True,
                    "scientific_pass_emitted": False,
                    "bayes_factor_emitted": False,
                    "reason_codes": ["forced_bad_decision"],
                }
            ), None
        return orig_resolve(spec)

    monkeypatch.setattr(stages_mod, "resolve_callable", fake_resolve)
    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["release_evaluate"]["outcome"] == StageOutcome.FAILED.value
    assert report["workflow_executed_successfully"] is False


def test_required_stage_missing_callable_blocks_downstream(monkeypatch):
    from tools.batch3_offline_integration import stages as stages_mod

    orig_resolve = stages_mod.resolve_callable

    def fake_resolve(spec):
        if spec.stage_id == "plan_quality":
            return None, "import_failed:tools.research_plan_quality.rubric:ModuleNotFoundError"
        return orig_resolve(spec)

    monkeypatch.setattr(stages_mod, "resolve_callable", fake_resolve)
    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["plan_quality"]["outcome"] != StageOutcome.SUCCEEDED.value
    assert by_id["preflight"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert by_id["registry_probe"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert by_id["release_evaluate"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert report["workflow_executed_successfully"] is False


def test_release_bundle_fixture_enforces_containment_and_duplicate_key_rejection(
    tmp_path: Path, monkeypatch
):
    import shutil
    from tools.batch3_offline_integration import fixture_producers

    fixture_root = tmp_path / "fixtures"
    shutil.copytree(fixture_producers.FIXTURE_DIR, fixture_root)
    (fixture_root / "release_bundle_synthetic.json").write_text(
        '{"cycle_id": "a", "cycle_id": "b"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(fixture_producers, "FIXTURE_DIR", fixture_root)

    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["release_evaluate"]["outcome"] == StageOutcome.REJECTED_INVALID_INPUT.value
    assert report["workflow_executed_successfully"] is False


def test_complete_plan_request_fixture_succeeds_end_to_end():
    report = run_offline_integration(fixture_name="complete_plan_request.json")
    assert report["workflow_executed_successfully"] is True
    assert report["scientific_validity_claimed"] is False
    assert report["scientific_pass_emitted"] is False


def test_no_network_context_manager_blocks_and_restores_socket():
    from tools.batch3_offline_integration.guards import no_network

    orig_socket = socket.socket
    orig_create_conn = socket.create_connection
    orig_getaddrinfo = socket.getaddrinfo

    with no_network():
        with pytest.raises(RuntimeError, match="network_disabled"):
            socket.socket()
        with pytest.raises(RuntimeError, match="network_disabled"):
            socket.create_connection(("127.0.0.1", 80))
        with pytest.raises(RuntimeError, match="network_disabled"):
            socket.getaddrinfo("localhost", 80)

    assert socket.socket is orig_socket
    assert socket.create_connection is orig_create_conn
    assert socket.getaddrinfo is orig_getaddrinfo


@pytest.mark.parametrize("bad_scientific_pass", [1, "yes", True, None, 0.1])
def test_claim_gate_rejects_non_false_scientific_pass(monkeypatch, bad_scientific_pass):
    """Regression: only exact False admits; truthy non-bool must not yield workflow success."""
    from tools.batch3_offline_integration import stages as stages_mod

    orig_resolve = stages_mod.resolve_callable

    def fake_resolve(spec):
        if spec.stage_id == "claim_gate":
            return (
                lambda _claim: {
                    "decision": "CLAIM_ADMISSIBLE",
                    "scientific_pass": bad_scientific_pass,
                }
            ), None
        return orig_resolve(spec)

    monkeypatch.setattr(stages_mod, "resolve_callable", fake_resolve)
    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["claim_gate"]["outcome"] == StageOutcome.FAILED.value
    assert by_id["claim_gate"]["error"] == "scientific_pass_must_be_false"
    assert by_id["preflight"]["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    assert report["workflow_executed_successfully"] is False


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("scientific_pass_emitted", 1),
        ("scientific_pass_emitted", "yes"),
        ("scientific_pass_emitted", True),
        ("scientific_pass_emitted", None),
        ("bayes_factor_emitted", 1),
        ("bayes_factor_emitted", "yes"),
        ("bayes_factor_emitted", True),
        ("bayes_factor_emitted", None),
    ],
)
def test_release_evaluate_rejects_non_false_scientific_markers(monkeypatch, field, bad_value):
    """Regression: release admission requires exact False scientific/Bayes markers."""
    from tools.batch3_offline_integration import stages as stages_mod

    orig_resolve = stages_mod.resolve_callable

    def fake_resolve(spec):
        if spec.stage_id == "release_evaluate":
            payload = {
                "decision": "SYNTHETIC_ONLY",
                "evidence_class": "research_cycle_release_operational",
                "synthetic_flag": True,
                "scientific_pass_emitted": False,
                "bayes_factor_emitted": False,
                "reason_codes": ["forced_marker"],
            }
            payload[field] = bad_value
            return (lambda _bundle, **_kw: payload), None
        return orig_resolve(spec)

    monkeypatch.setattr(stages_mod, "resolve_callable", fake_resolve)
    report = run_offline_integration(fixture_name="workflow_request.json")
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["release_evaluate"]["outcome"] == StageOutcome.FAILED.value
    assert report["workflow_executed_successfully"] is False
    if field == "scientific_pass_emitted":
        assert by_id["release_evaluate"]["error"] == "scientific_pass_emitted_must_be_false"
    else:
        assert by_id["release_evaluate"]["error"] == "bayes_factor_emitted_must_be_false"


def test_force_fail_optional_stage_clears_workflow_success():
    """Regression: force-failing optional_artifact_lineage must not claim workflow success."""
    report = run_offline_integration(
        fixture_name="workflow_request.json",
        force_fail_stage="optional_artifact_lineage",
    )
    by_id = {s["stage_id"]: s for s in report["stages"]}
    assert by_id["optional_artifact_lineage"]["outcome"] == StageOutcome.FAILED.value
    assert by_id["optional_artifact_lineage"]["error"] == "forced_stage_failure"
    assert report["workflow_executed_successfully"] is False


def test_cli_force_fail_optional_exits_nonzero():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.batch3_offline_integration",
            "--force-fail-stage",
            "optional_artifact_lineage",
            "--json-stdout",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["workflow_executed_successfully"] is False


@pytest.mark.skipif(
    not hasattr(os, "mkfifo") or not hasattr(signal, "alarm"),
    reason="POSIX FIFO and SIGALRM facilities are unavailable on this platform",
)
def test_fifo_allowlisted_fixture_name_fails_closed_without_hang(tmp_path: Path, monkeypatch):
    """Regression: FIFO under an allowlisted name must reject before a blocking open."""
    import shutil
    from tools.batch3_offline_integration import fixture_producers
    from tools.batch3_offline_integration.fixture_producers import _read_fixture

    fixture_root = tmp_path / "fixtures"
    shutil.copytree(fixture_producers.FIXTURE_DIR, fixture_root)
    target = fixture_root / "workflow_request.json"
    target.unlink()
    os.mkfifo(target)
    monkeypatch.setattr(fixture_producers, "FIXTURE_DIR", fixture_root)

    def _alarm_handler(_signum, _frame):
        raise TimeoutError("fifo_open_blocked")

    previous = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(2)
    try:
        with pytest.raises(ValueError, match="regular file"):
            _read_fixture("workflow_request.json")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
