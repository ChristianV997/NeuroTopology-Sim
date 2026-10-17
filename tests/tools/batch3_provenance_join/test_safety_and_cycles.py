from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from tools.batch3_provenance_join import AuditLimits, audit_provenance
from tests.tools.batch3_provenance_join.helpers import ledger_export, ledger_record, sha, valid_fixture, write_json


def _codes(report: dict) -> set[str]:
    return {item["code"] for item in report["findings"]}


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    manifest = json.loads(paths[1].read_text(encoding="utf-8"))
    manifest["artifacts"][0]["relative_path"] = "../outside.json"
    manifest_path = write_json(tmp_path / "unsafe-manifest.json", manifest)

    report = audit_provenance(tmp_path, [paths[0], manifest_path, paths[2], paths[3], paths[4]])

    assert report["status"] == "INVALID"
    assert "unsafe_or_missing_reference" in _codes(report)


def test_absolute_embedded_artifact_reference_is_rejected(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    manifest = json.loads(paths[1].read_text(encoding="utf-8"))
    manifest["artifacts"][0]["relative_path"] = str(tmp_path / "summary.json")
    manifest_path = write_json(tmp_path / "absolute-manifest.json", manifest)

    report = audit_provenance(tmp_path, [paths[0], manifest_path, paths[2], paths[3], paths[4]])

    assert report["status"] == "INVALID"
    assert "unsafe_or_missing_reference" in _codes(report)


def test_symlink_reference_is_rejected_when_platform_allows(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.bin"
    outside.write_bytes(b"outside")
    link = tmp_path / "linked.bin"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable in this environment")
    manifest = json.loads(paths[1].read_text(encoding="utf-8"))
    manifest["artifacts"] = [{"relative_path": "linked.bin", "sha256": "0" * 64, "size_bytes": 7}]
    manifest_path = write_json(tmp_path / "symlink-manifest.json", manifest)

    report = audit_provenance(tmp_path, [paths[0], manifest_path, paths[2], paths[3], paths[4]])

    assert report["status"] == "INVALID"
    assert "unsafe_or_missing_reference" in _codes(report)


def test_manifest_artifact_and_total_size_limits_are_enforced(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    report = audit_provenance(
        tmp_path,
        paths,
        limits=AuditLimits(max_manifest_bytes=1024 * 1024, max_artifact_bytes=4, max_total_bytes=1024 * 1024, max_files=100),
    )
    assert report["status"] == "INVALID"
    assert "artifact_size_limit_exceeded" in _codes(report)

    report = audit_provenance(
        tmp_path,
        paths,
        limits=AuditLimits(max_manifest_bytes=1024 * 1024, max_artifact_bytes=1024, max_total_bytes=8, max_files=100),
    )
    assert report["status"] == "INVALID"
    assert "total_size_limit_exceeded" in _codes(report)


def test_malformed_duplicate_key_and_non_finite_json_are_rejected(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
    report = audit_provenance(tmp_path, [duplicate])
    assert report["status"] == "INVALID"
    assert "malformed_manifest" in _codes(report)

    non_finite = tmp_path / "non-finite.json"
    non_finite.write_text('{"schema":"NeuroTopologySim.EmpiricalSourceManifest.v1","x":NaN}', encoding="utf-8")
    report = audit_provenance(tmp_path, [non_finite])
    assert report["status"] == "INVALID"
    assert "malformed_manifest" in _codes(report)


def test_ledger_cross_cycle_parent_reference_resolves_only_with_declared_ancestor(tmp_path: Path) -> None:
    parent_source = ledger_record(
        "source_snapshot",
        "cycle-parent",
        snapshot_id="snapshot-parent",
        source_uri="local:fixture",
        source_sha256="a" * 64,
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture",
        scientific_limitations=["Fixture only."],
        metadata={"dataset_identifier": "dataset-parent", "license_id": "license-fixture"},
    )
    child_evidence = ledger_record(
        "evidence_record",
        "cycle-child",
        evidence_id="evidence-child",
        source_snapshot_ids=["snapshot-parent"],
        observation="Fixture only.",
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture",
        scientific_limitations=["Fixture only."],
        metrics={},
    )
    parent_path = write_json(tmp_path / "parent-cycle.json", ledger_export("cycle-parent", [parent_source]))
    child_path = write_json(tmp_path / "child-cycle.json", ledger_export("cycle-child", [child_evidence], parent_cycle_id="cycle-parent"))

    report = audit_provenance(tmp_path, [parent_path, child_path])

    assert "cross_cycle_reference_invalid" not in _codes(report)
    assert "unresolved_ledger_reference" not in _codes(report)


def test_sibling_cycle_reference_is_invalid(tmp_path: Path) -> None:
    parent = ledger_export("cycle-root", [])
    source = ledger_record(
        "source_snapshot",
        "cycle-sibling-a",
        snapshot_id="snapshot-sibling-a",
        source_uri="local:fixture",
        source_sha256="b" * 64,
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture",
        scientific_limitations=["Fixture only."],
        metadata={"dataset_identifier": "dataset-fixture", "license_id": "license-fixture"},
    )
    evidence = ledger_record(
        "evidence_record",
        "cycle-sibling-b",
        evidence_id="evidence-sibling-b",
        source_snapshot_ids=["snapshot-sibling-a"],
        observation="Fixture only.",
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture",
        scientific_limitations=["Fixture only."],
        metrics={},
    )
    root_path = write_json(tmp_path / "root-cycle.json", parent)
    source_path = write_json(tmp_path / "sibling-a.json", ledger_export("cycle-sibling-a", [source], parent_cycle_id="cycle-root"))
    evidence_path = write_json(tmp_path / "sibling-b.json", ledger_export("cycle-sibling-b", [evidence], parent_cycle_id="cycle-root"))

    report = audit_provenance(tmp_path, [root_path, source_path, evidence_path])

    assert report["status"] == "INVALID"
    assert "cross_cycle_reference_invalid" in _codes(report)


def test_typed_ledger_reference_does_not_resolve_other_record_type(tmp_path: Path) -> None:
    cycle_id = "cycle-typed-collision"
    claim_with_collision_id = ledger_record(
        "claim",
        cycle_id,
        claim_id="shared-text-id",
        statement="Fixture claim only.",
        evidence_ids=[],
        evidence_class="hypothesis",
        claim_scope="fixture",
        scientific_limitations=["Not evidence."],
    )
    claim_referencing_evidence = ledger_record(
        "claim",
        cycle_id,
        claim_id="claim-referrer",
        statement="Another fixture claim.",
        evidence_ids=["shared-text-id"],
        evidence_class="hypothesis",
        claim_scope="fixture",
        scientific_limitations=["Not evidence."],
    )
    path = write_json(
        tmp_path / "typed-collision.json",
        ledger_export(cycle_id, [claim_with_collision_id, claim_referencing_evidence]),
    )

    report = audit_provenance(tmp_path, [path])

    assert report["status"] == "INVALID"
    finding = next(item for item in report["findings"] if item["code"] == "typed_reference_type_mismatch")
    assert finding["subject"] == "claim-referrer.evidence_ids"
    assert "evidence_record" in finding["detail"]
    assert "claim" in finding["detail"]


def test_malformed_typed_reference_is_not_silently_omitted(tmp_path: Path) -> None:
    cycle_id = "cycle-malformed-reference"
    malformed = ledger_record(
        "claim",
        cycle_id,
        claim_id="claim-malformed",
        statement="Malformed fixture claim.",
        evidence_ids=["valid-id", 7],
        evidence_class="hypothesis",
        claim_scope="fixture",
        scientific_limitations=["Not evidence."],
    )
    path = write_json(tmp_path / "malformed-reference.json", ledger_export(cycle_id, [malformed]))

    report = audit_provenance(tmp_path, [path])

    assert report["status"] == "INVALID"
    finding = next(item for item in report["findings"] if item["code"] == "malformed_ledger_reference")
    assert finding["subject"] == "claim-malformed.evidence_ids"


def test_missing_typed_ledger_reference_is_reported(tmp_path: Path) -> None:
    cycle_id = "cycle-missing-reference"
    evidence = ledger_record(
        "evidence_record",
        cycle_id,
        evidence_id="evidence-missing-source",
        source_snapshot_ids=["snapshot-not-supplied"],
        observation="Fixture only.",
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture",
        scientific_limitations=["Not evidence."],
        metrics={},
    )
    path = write_json(tmp_path / "missing-reference.json", ledger_export(cycle_id, [evidence]))

    report = audit_provenance(tmp_path, [path])

    assert "unresolved_ledger_reference" in _codes(report)


def test_unknown_ledger_record_type_is_unverifiable(tmp_path: Path) -> None:
    cycle_id = "cycle-unknown-record-type"
    record = {
        "record_type": "source_pack_record",
        "record_id": "pack-record-1",
        "cycle_id": cycle_id,
        "status": "COMPLETED",
        "parent_ids": [],
        "child_ids": [],
        "schema_version": "awareness-studio-research-cycle.v1",
    }
    record["checksum"] = sha(record)
    path = write_json(tmp_path / "unknown-record-type.json", ledger_export(cycle_id, [record]))

    report = audit_provenance(tmp_path, [path])

    assert report["status"] == "INCOMPLETE"
    finding = next(item for item in report["findings"] if item["code"] == "unverifiable_ledger_record_type")
    assert finding["subject"] == "unknown-record-type.json:record[0]"
    assert "source_pack_record" in finding["detail"]


def test_our_runtime_modules_do_not_import_network_solver_or_subprocess_modules() -> None:
    package = Path(__file__).resolve().parents[3] / "tools" / "batch3_provenance_join"
    forbidden = {"socket", "requests", "urllib", "http", "httpx", "aiohttp", "subprocess", "numpy", "scipy", "sklearn", "mne", "torch"}
    imports: set[str] = set()
    source_files = [*package.glob("*.py"), Path(__file__).resolve().parents[3] / "scripts" / "run_batch3_provenance_join.py"]
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    assert not (imports & forbidden)
