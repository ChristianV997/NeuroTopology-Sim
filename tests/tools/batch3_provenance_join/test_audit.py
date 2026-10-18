from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.run_batch3_provenance_join import main
from tools.batch3_provenance_join import audit_provenance
from tools.batch3_provenance_join.models import run_configuration_fingerprint
from tests.tools.batch3_provenance_join.helpers import ledger_export, ledger_record, sha, valid_fixture, write_json


def _codes(report: dict) -> set[str]:
    return {item["code"] for item in report["findings"]}


def test_valid_explicit_run_source_ledger_output_and_bundle_join(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)

    report = audit_provenance(tmp_path, paths)

    assert report["status"] == "INCOMPLETE"
    assert "source_checksum_scope_unverifiable" in _codes(report)
    assert not any(item["severity"] == "error" for item in report["findings"])
    assert report["scientific_validation"] is False
    assert report["orphan_artifacts"] == []
    assert len(report["verified_output_entries"]) == 1
    assert report["verified_output_entries"][0]["relative_path"] == "summary.json"
    assert report["verified_output_entries"][0]["sha256"] == hashlib.sha256((tmp_path / "summary.json").read_bytes()).hexdigest()


def test_missing_run_manifest_and_source_reference_are_incomplete(tmp_path: Path) -> None:
    run = {
        "schema_version": "0.1",
        "run_id": "run-without-source",
        "dataset_id": "not-supplied",
        "input": {"source_id": "source-missing"},
        "artifacts": {},
    }
    path = write_json(tmp_path / "run.json", run)

    report = audit_provenance(tmp_path, [path])

    assert report["status"] == "INCOMPLETE"
    assert {"run_missing_output_manifest", "unresolved_source_reference"} <= _codes(report)


def test_artifact_checksum_mismatch_is_invalid(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    (tmp_path / "summary.json").write_text('{"fixture_metric":0.5}\n', encoding="utf-8")

    report = audit_provenance(tmp_path, paths)

    assert report["status"] == "INVALID"
    assert "checksum_mismatch" in _codes(report)


def test_manifest_entry_requires_documented_byte_size(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    manifest = json.loads(paths[1].read_text(encoding="utf-8"))
    manifest["artifacts"][0].pop("size_bytes")
    manifest_path = write_json(tmp_path / "out-manifest.json", manifest)

    report = audit_provenance(tmp_path, [paths[0], manifest_path, *paths[2:]])

    assert report["status"] == "INVALID"
    assert "malformed_artifact_entry" in _codes(report)


def test_duplicate_run_ids_are_invalid(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    duplicate = json.loads(paths[0].read_text(encoding="utf-8"))
    duplicate_path = write_json(tmp_path / "run-copy.json", duplicate)

    report = audit_provenance(tmp_path, [*paths, duplicate_path])

    assert report["status"] == "INVALID"
    assert "duplicate_run_id" in _codes(report)


def test_duplicate_output_content_is_detected_across_runs(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    source_bytes = (tmp_path / "summary.json").read_bytes()
    (tmp_path / "summary-copy.json").write_bytes(source_bytes)
    digest = hashlib.sha256(source_bytes).hexdigest()
    run = write_json(tmp_path / "run-copy.json", {
        "schema_version": "0.1",
        "run_id": "run-fixture-2",
        "data_mode": "synthetic",
        "input": {},
        "config": {},
        "artifacts": {"summary": "summary-copy.json"},
    })
    manifest = write_json(tmp_path / "manifest-copy.json", {
        "schema": "NTS.IntegrationArtifactManifest.v1",
        "run_id": "run-fixture-2",
        "artifacts": [{"relative_path": "summary-copy.json", "sha256": digest, "size_bytes": len(source_bytes)}],
    })

    report = audit_provenance(tmp_path, [*paths, run, manifest])

    assert "duplicate_artifact_content" in _codes(report)


def test_stale_configuration_fingerprint_is_reported(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    run = json.loads(paths[0].read_text(encoding="utf-8"))
    lineage = {
        "schema_version": "NeuroTopologySim.SimulationArtifactLineage.v1",
        "status": "COMPLETE",
        "artifact_manifest": {
            "run_directory": ".",
            "artifacts": [{
                "relative_path": "summary.json",
                "role": "summary",
                "sha256": hashlib.sha256((tmp_path / "summary.json").read_bytes()).hexdigest(),
                "size_bytes": (tmp_path / "summary.json").stat().st_size,
            }],
            "duplicate_content": [],
        },
        "provenance": {
            "run_id": run["run_id"],
            "configuration_fingerprint": "0" * 64,
            "input_fingerprint": run_configuration_fingerprint(run["input"]),
        },
        "evidence": {"evidence_class": "synthetic_demo_only", "synthetic": True},
        "diagnostics": {"missing": [], "stale": [], "partial": [], "failed": [], "conflicting": [], "errors": []},
        "relationships": [],
        "read_only": True,
        "solver_executed": False,
        "heavy_runtime_imported": False,
    }
    lineage["report_sha256"] = hashlib.sha256((json.dumps(lineage, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")).hexdigest()
    lineage_path = write_json(tmp_path / "lineage.json", lineage)

    report = audit_provenance(tmp_path, [*paths, lineage_path])

    assert report["status"] == "INCOMPLETE"
    assert "stale_configuration_fingerprint" in _codes(report)


def test_partial_producer_status_is_not_success(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    report_doc = {
        "schema_version": "NeuroTopologySim.SimulationArtifactLineage.v1",
        "status": "PARTIAL",
        "artifact_manifest": {"run_directory": ".", "artifacts": [], "duplicate_content": []},
        "provenance": {"run_id": "run-fixture-1"},
        "diagnostics": {"missing": ["metrics.json"], "stale": [], "partial": ["metrics.json"], "failed": [], "conflicting": [], "errors": []},
        "evidence": {"evidence_class": "synthetic_demo_only", "synthetic": True},
    }
    report_doc["report_sha256"] = hashlib.sha256((json.dumps(report_doc, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")).hexdigest()
    path = write_json(tmp_path / "partial-lineage.json", report_doc)

    report = audit_provenance(tmp_path, [*paths, path])

    assert report["status"] == "INCOMPLETE"
    assert "partial_input" in _codes(report)
    assert "producer_reports_missing_artifact" in _codes(report)


def test_license_ids_do_not_join_without_a_license_record_contract(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    run = json.loads(paths[0].read_text(encoding="utf-8"))
    run["input"]["license_ref"] = "fixture-license-1"
    run_path = write_json(tmp_path / "run.json", run)

    report = audit_provenance(tmp_path, [run_path, *paths[1:]])

    assert report["status"] == "INCOMPLETE"
    assert "unverifiable_license_reference" in _codes(report)
    assert "unverifiable_license_identity" in _codes(report)
    assert "unresolved_license_reference" not in _codes(report)


def test_untyped_license_field_spellings_are_reported_at_json_pointers(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    run = json.loads(paths[0].read_text(encoding="utf-8"))
    run["metadata"] = {
        "license_url": "https://example.invalid/license",
        "spdxLicense": "CC-BY-4.0",
        "nested": {"licence": "unknown"},
    }
    run_path = write_json(tmp_path / "run-license-variants.json", run)

    report = audit_provenance(tmp_path, [run_path, *paths[1:]])

    findings = {
        item["subject"]: item
        for item in report["findings"]
        if item["code"] == "unverifiable_license_field"
    }
    assert report["status"] == "INCOMPLETE"
    assert {
        "run-license-variants.json#/metadata/license_url",
        "run-license-variants.json#/metadata/spdxLicense",
        "run-license-variants.json#/metadata/nested/licence",
    } <= findings.keys()
    assert all("no typed license record contract" in item["detail"] for item in findings.values())


def test_explicit_configuration_version_mismatch_is_reported(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    run = json.loads(paths[0].read_text(encoding="utf-8"))
    run["config"].update({"configuration_id": "config-fixture", "configuration_version": "2"})
    run_path = write_json(tmp_path / "run.json", run)
    ledger = json.loads(paths[3].read_text(encoding="utf-8"))
    cycle_id = ledger["cycle"]["cycle_id"]
    experiment = ledger_record(
        "experiment_spec",
        cycle_id,
        experiment_id="experiment-config-fixture",
        hypothesis_ids=[],
        method="fixture only",
        parameters={"configuration_id": "config-fixture", "configuration_version": "1"},
    )
    ledger_path = write_json(tmp_path / "cycle-export.json", ledger_export(cycle_id, [*ledger["records"], experiment]))

    report = audit_provenance(tmp_path, [run_path, paths[1], paths[2], ledger_path, paths[4]])

    assert "stale_configuration_version" in _codes(report)


def test_untyped_source_version_pin_is_not_joined_to_snapshot_metadata(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    run = json.loads(paths[0].read_text(encoding="utf-8"))
    run["input"].update({"source_id": "dataset-fixture-1", "source_version": "2"})
    run_path = write_json(tmp_path / "run.json", run)
    ledger = json.loads(paths[3].read_text(encoding="utf-8"))
    cycle_id = ledger["cycle"]["cycle_id"]
    old_source = ledger["records"][0]
    source = ledger_record(
        "source_snapshot",
        cycle_id,
        snapshot_id=old_source["snapshot_id"],
        source_uri=old_source["source_uri"],
        source_sha256=old_source["source_sha256"],
        data_mode=old_source["data_mode"],
        evidence_class=old_source["evidence_class"],
        claim_scope=old_source["claim_scope"],
        scientific_limitations=old_source["scientific_limitations"],
        source_format=old_source["source_format"],
        captured_at=old_source["captured_at"],
        metadata={**old_source["metadata"], "source_version": "1"},
    )
    ledger_path = write_json(tmp_path / "cycle-export.json", ledger_export(cycle_id, [source, ledger["records"][1]]))

    report = audit_provenance(tmp_path, [run_path, paths[1], paths[2], ledger_path, paths[4]])

    assert "stale_source_version" not in _codes(report)
    assert "source_version_unverifiable" in _codes(report)
    assert "unverifiable_source_reference" in _codes(report)


def test_conflicting_explicit_origin_classes_are_reported(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    run = json.loads(paths[0].read_text(encoding="utf-8"))
    run["data_mode"] = "empirical_local"
    run_path = write_json(tmp_path / "run.json", run)

    report = audit_provenance(tmp_path, [run_path, *paths[1:]])

    assert report["status"] == "INCOMPLETE"
    assert "source_data_mode_conflict" in _codes(report)


def test_external_solver_origin_is_unverifiable_for_binary_origin_join(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    source = json.loads(paths[2].read_text(encoding="utf-8"))
    source["origin"] = "external_solver"
    source_path = write_json(tmp_path / "source-manifest.json", source)

    report = audit_provenance(tmp_path, [paths[0], paths[1], source_path, paths[3], paths[4]])

    findings = [item for item in report["findings"] if item["code"] == "unverifiable_origin"]
    assert report["status"] == "INCOMPLETE"
    assert any(item["subject"] == "source-manifest.json#/origin" for item in findings)
    assert any("external_solver" in item["detail"] for item in findings)
    assert any("recognized by the source-manifest schema" in item["detail"] for item in findings)


def test_unavailable_origin_is_unverifiable_for_binary_origin_join(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    source = json.loads(paths[2].read_text(encoding="utf-8"))
    source["origin"] = "unavailable"
    source_path = write_json(tmp_path / "source-manifest.json", source)

    report = audit_provenance(tmp_path, [paths[0], paths[1], source_path, paths[3], paths[4]])

    findings = [item for item in report["findings"] if item["code"] == "unverifiable_origin"]
    assert report["status"] == "INCOMPLETE"
    assert any(item["subject"] == "source-manifest.json#/origin" for item in findings)
    assert any("unavailable" in item["detail"] for item in findings)


def test_unknown_manifest_artifact_type_is_unverifiable(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    manifest = json.loads(paths[1].read_text(encoding="utf-8"))
    manifest["artifacts"][0]["artifact_type"] = "unregistered_trajectory"
    manifest_path = write_json(tmp_path / "manifest.json", manifest)

    report = audit_provenance(tmp_path, [paths[0], manifest_path, paths[2], paths[3], paths[4]])

    findings = [item for item in report["findings"] if item["code"] == "unverifiable_artifact_type"]
    assert report["status"] == "INCOMPLETE"
    assert any(item["subject"] == "manifest.json#/artifacts/0/artifact_type" for item in findings)
    assert any("unregistered_trajectory" in item["detail"] for item in findings)


def test_unclassified_fields_are_reported_anywhere_with_json_pointer_locations(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    run = json.loads(paths[0].read_text(encoding="utf-8"))
    run["metadata"] = {"uncertain/key~name": {"artifact_type": "mystery_blob", "data_mode": None}}
    run_path = write_json(tmp_path / "run.json", run)

    report = audit_provenance(tmp_path, [run_path, *paths[1:]])

    findings = [item for item in report["findings"] if item["code"] in {"unverifiable_origin", "unverifiable_artifact_type"}]
    assert report["status"] == "INCOMPLETE"
    assert any(item["subject"] == "run.json#/metadata/uncertain~1key~0name/artifact_type" for item in findings)
    assert any(item["subject"] == "run.json#/metadata/uncertain~1key~0name/data_mode" for item in findings)
    assert any("mystery_blob" in item["detail"] for item in findings)


def test_dataset_id_does_not_join_to_equal_source_snapshot_id(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    run = json.loads(paths[0].read_text(encoding="utf-8"))
    run["data_mode"] = "empirical_local"
    run_path = write_json(tmp_path / "run.json", run)
    source_manifest = json.loads(paths[2].read_text(encoding="utf-8"))
    source_manifest["origin"] = "empirical"
    source_path = write_json(tmp_path / "source-manifest.json", source_manifest)

    old_export = json.loads(paths[3].read_text(encoding="utf-8"))
    cycle_id = old_export["cycle"]["cycle_id"]
    old_snapshot, old_evidence = old_export["records"]
    shared_text = run["dataset_id"]
    snapshot = ledger_record(
        "source_snapshot",
        cycle_id,
        snapshot_id=shared_text,
        source_uri=old_snapshot["source_uri"],
        source_sha256=old_snapshot["source_sha256"],
        data_mode="synthetic",
        evidence_class=old_snapshot["evidence_class"],
        claim_scope=old_snapshot["claim_scope"],
        scientific_limitations=old_snapshot["scientific_limitations"],
        source_format=old_snapshot["source_format"],
        captured_at=old_snapshot["captured_at"],
        metadata={},
    )
    evidence = ledger_record(
        "evidence_record",
        cycle_id,
        evidence_id=old_evidence["evidence_id"],
        source_snapshot_ids=[shared_text],
        observation=old_evidence["observation"],
        data_mode=old_evidence["data_mode"],
        evidence_class=old_evidence["evidence_class"],
        claim_scope=old_evidence["claim_scope"],
        scientific_limitations=old_evidence["scientific_limitations"],
        metrics=old_evidence["metrics"],
    )
    ledger_path = write_json(tmp_path / "cycle-export.json", ledger_export(cycle_id, [snapshot, evidence]))

    report = audit_provenance(tmp_path, [run_path, paths[1], source_path, ledger_path, paths[4]])

    assert "source_data_mode_conflict" not in _codes(report)
    assert not any(item["subject"] == shared_text and item["code"] == "source_data_mode_conflict" for item in report["findings"])


def test_unknown_manifest_schema_is_reported_as_unverifiable(tmp_path: Path) -> None:
    path = write_json(tmp_path / "unknown.json", {"schema": "NTS.UnmergedSourcePack.v1", "origin": "unavailable"})

    report = audit_provenance(tmp_path, [path])

    finding = next(item for item in report["findings"] if item["code"] == "unverifiable_manifest_schema")
    assert report["status"] == "INCOMPLETE"
    assert finding["subject"] == "unknown.json"
    assert "NTS.UnmergedSourcePack.v1" in finding["detail"]
    assert {item["code"] for item in report["findings"]} >= {"unverifiable_origin"}


def test_untyped_source_manifest_checksum_is_not_assigned_a_scope(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    source = json.loads(paths[2].read_text(encoding="utf-8"))
    source["source_checksum"] = hashlib.sha256((tmp_path / "source.bin").read_bytes()).hexdigest()
    source["source_path"] = "source.bin"
    source_path = write_json(tmp_path / "source-manifest.json", source)

    report = audit_provenance(tmp_path, [paths[0], paths[1], source_path, paths[3], paths[4]])

    assert report["status"] == "INCOMPLETE"
    assert "source_manifest_checksum_unverifiable" in _codes(report)
    assert "checksum_mismatch" not in _codes(report)


def test_malformed_source_snapshot_checksum_is_invalid(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    ledger = json.loads(paths[3].read_text(encoding="utf-8"))
    cycle_id = ledger["cycle"]["cycle_id"]
    old_source = ledger["records"][0]
    source = ledger_record(
        "source_snapshot",
        cycle_id,
        snapshot_id=old_source["snapshot_id"],
        source_uri=old_source["source_uri"],
        source_sha256="not-a-sha256",
        data_mode=old_source["data_mode"],
        evidence_class=old_source["evidence_class"],
        claim_scope=old_source["claim_scope"],
        scientific_limitations=old_source["scientific_limitations"],
        source_format=old_source["source_format"],
        captured_at=old_source["captured_at"],
        metadata=old_source["metadata"],
    )
    ledger_path = write_json(tmp_path / "cycle-export.json", ledger_export(cycle_id, [source, ledger["records"][1]]))

    report = audit_provenance(tmp_path, [*paths[:3], ledger_path, paths[4]])

    assert report["status"] == "INVALID"
    assert "malformed_source_checksum" in _codes(report)


def test_source_snapshot_checksum_is_not_compared_to_uri_bytes_without_scope(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    run = json.loads(paths[0].read_text(encoding="utf-8"))
    run["input"].pop("source_sha256")
    run_path = write_json(tmp_path / "run.json", run)
    ledger = json.loads(paths[3].read_text(encoding="utf-8"))
    cycle_id = ledger["cycle"]["cycle_id"]
    old_source = ledger["records"][0]
    source = ledger_record(
        "source_snapshot",
        cycle_id,
        snapshot_id=old_source["snapshot_id"],
        source_uri=old_source["source_uri"],
        source_sha256="f" * 64,
        data_mode=old_source["data_mode"],
        evidence_class=old_source["evidence_class"],
        claim_scope=old_source["claim_scope"],
        scientific_limitations=old_source["scientific_limitations"],
        source_format=old_source["source_format"],
        captured_at=old_source["captured_at"],
        metadata=old_source["metadata"],
    )
    ledger_path = write_json(tmp_path / "cycle-export.json", ledger_export(cycle_id, [source, ledger["records"][1]]))

    report = audit_provenance(tmp_path, [run_path, paths[1], paths[2], ledger_path, paths[4]])

    assert report["status"] == "INCOMPLETE"
    assert "source_checksum_scope_unverifiable" in _codes(report)
    assert "checksum_mismatch" not in _codes(report)


def test_cli_emits_deterministic_json_without_writing_report(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    output = io.StringIO()
    with redirect_stdout(output):
        code = main(["--artifact-root", str(tmp_path), *sum((["--input-manifest", str(path)] for path in paths), [])])

    assert code == 1
    assert json.loads(output.getvalue())["status"] == "INCOMPLETE"


def test_cli_invalid_limits_fail_closed(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    error = io.StringIO()
    with redirect_stderr(error):
        code = main(["--artifact-root", str(tmp_path), "--input-manifest", str(paths[0]), "--max-files", "0"])

    assert code == 2
    assert json.loads(error.getvalue())["status"] == "INVALID"


def test_evidence_source_path_is_not_misjoined_to_registry_artifact_ids(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    bundle = json.loads(paths[4].read_text(encoding="utf-8"))
    bundle["artifact_paths"] = {"source": "source.bin"}
    bundle_path = write_json(tmp_path / "bundle.json", bundle)

    report = audit_provenance(tmp_path, [*paths[:4], bundle_path])

    assert report["status"] == "INCOMPLETE"
    assert "evidence_artifact_decision_missing" not in _codes(report)


def test_evidence_artifact_id_without_registry_decision_is_incomplete(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    bundle = json.loads(paths[4].read_text(encoding="utf-8"))
    bundle["registry_decisions"] = []
    bundle_path = write_json(tmp_path / "bundle.json", bundle)

    report = audit_provenance(tmp_path, [*paths[:4], bundle_path])

    assert report["status"] == "INCOMPLETE"
    assert "evidence_artifact_decision_missing" in _codes(report)


def test_positive_status_without_gate_event_is_only_a_warning(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    bundle = json.loads(paths[4].read_text(encoding="utf-8"))
    bundle["status"] = "VALIDATED"
    bundle_path = write_json(tmp_path / "bundle.json", bundle)

    report = audit_provenance(tmp_path, [*paths[:4], bundle_path])

    assert report["status"] == "INCOMPLETE"
    assert "unsupported_status_claim" in _codes(report)


def test_gate_event_identifier_in_another_namespace_does_not_support_status(tmp_path: Path) -> None:
    cycle_id = "cycle-gate-namespace"
    claim = ledger_record(
        "claim",
        cycle_id,
        claim_id="shared-status-id",
        statement="Fixture-only claim.",
        evidence_ids=[],
        evidence_class="hypothesis",
        claim_scope="fixture",
        scientific_limitations=["No scientific evidence."],
        status="PASS",
    )
    export = ledger_export(cycle_id, [claim])
    event = {
        "cycle_id": cycle_id,
        "event_id": "event-gate-namespace-1",
        "sequence": 1,
        "event_type": "validation_outcome",
        "producer": "fixture",
        "status": "PASS",
        "payload": {"artifact_manifest_id": "shared-status-id", "validation_status": "PASS"},
        "previous_hash": None,
        "schema_version": "awareness-studio-research-cycle-event.v1",
    }
    event["event_hash"] = sha({key: event[key] for key in (
        "cycle_id", "event_id", "sequence", "event_type", "producer", "status", "payload", "previous_hash", "schema_version",
    )})
    export["events"] = [event]
    export.pop("export_checksum")
    export["export_checksum"] = sha(export)
    path = write_json(tmp_path / "gate-namespace.json", export)

    report = audit_provenance(tmp_path, [path])

    assert "unsupported_status_claim" in _codes(report)
    assert any(item["subject"] == "shared-status-id.claim#/status" for item in report["findings"] if item["code"] == "unsupported_status_claim")


def test_run_record_link_checksum_scope_is_not_guessed(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    run = json.loads(paths[0].read_text(encoding="utf-8"))
    run_hash = hashlib.sha256(json.dumps(run, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    cycle_id = "cycle-with-run"
    run_ref = ledger_record(
        "run_record",
        cycle_id,
        run_record_id=run["run_id"],
        experiment_id="experiment-fixture",
        run_record_schema_version="0.1",
        run_record_sha256=run_hash,
        run_status="PASS",
        evidence_class="engineering_fact",
        claim_scope="engineering execution record",
        scientific_limitations=["Not scientific validation."],
    )
    experiment = ledger_record(
        "experiment_spec",
        cycle_id,
        experiment_id="experiment-fixture",
        hypothesis_ids=[],
        method="fixture only",
        parameters={},
    )
    ledger_path = write_json(tmp_path / "run-cycle.json", ledger_export(cycle_id, [experiment, run_ref]))

    report = audit_provenance(tmp_path, [*paths, ledger_path])

    assert "run_record_checksum_scope_unverifiable" in _codes(report)
    assert "unsupported_status_claim" in _codes(report)
    assert "unresolved_experiment_reference" not in _codes(report)
    assert report["status"] == "INCOMPLETE"


def test_repeated_audit_has_identical_report_and_checksum(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)

    first = audit_provenance(tmp_path, paths)
    second = audit_provenance(tmp_path, paths)

    assert first == second
    assert first["report_sha256"] == second["report_sha256"]
