from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.batch3_provenance_join import AuditLimits, audit_provenance
from tools.batch3_provenance_join import auditor as provenance_auditor
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


def test_windows_reparse_point_is_detected_without_pathlib_junction_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LegacyWindowsPath:
        # Python versions before 3.12 do not expose Path.is_junction().
        is_junction = None

        def __init__(self, info: SimpleNamespace) -> None:
            self.info = info

        def lstat(self) -> SimpleNamespace:
            return self.info

    monkeypatch.setattr(
        provenance_auditor.stat,
        "FILE_ATTRIBUTE_REPARSE_POINT",
        0x400,
        raising=False,
    )

    for info in (
        SimpleNamespace(
            st_mode=provenance_auditor.stat.S_IFDIR,
            st_file_attributes=0x400,
            st_reparse_tag=0,
        ),
        SimpleNamespace(
            st_mode=provenance_auditor.stat.S_IFDIR,
            st_file_attributes=0,
            st_reparse_tag=0xA0000003,
        ),
    ):
        assert provenance_auditor._is_link(LegacyWindowsPath(info))


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

    report = audit_provenance(
        tmp_path,
        paths,
        limits=AuditLimits(
            max_manifest_bytes=1024 * 1024,
            max_artifact_bytes=1024,
            max_total_bytes=1024 * 1024,
            max_files=1,
        ),
    )
    assert report["status"] == "INVALID"
    assert "file_count_limit_exceeded" in _codes(report)


def test_directory_only_tree_is_bounded_by_inventory_entry_limit(tmp_path: Path) -> None:
    path = write_json(tmp_path / "manifest.json", {"schema": "unknown"})
    for index in range(5):
        (tmp_path / f"directory-{index}").mkdir()

    report = audit_provenance(
        tmp_path,
        [path],
        limits=AuditLimits(
            max_manifest_bytes=1024 * 1024,
            max_artifact_bytes=1024,
            max_total_bytes=1024 * 1024,
            max_files=100,
            max_inventory_entries=3,
        ),
    )
    repeated = audit_provenance(
        tmp_path,
        [path],
        limits=AuditLimits(
            max_manifest_bytes=1024 * 1024,
            max_artifact_bytes=1024,
            max_total_bytes=1024 * 1024,
            max_files=100,
            max_inventory_entries=3,
        ),
    )

    assert report["status"] == "INVALID"
    assert "inventory_entry_limit_exceeded" in _codes(report)
    assert report == repeated
    assert report["orphan_artifacts"] == []


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


def test_boolean_event_sequence_is_rejected_even_with_a_valid_hash_chain(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    ledger = json.loads(paths[3].read_text(encoding="utf-8"))
    first, second = ledger["events"]
    first["sequence"] = True
    first["event_hash"] = sha({key: value for key, value in first.items() if key != "event_hash"})
    second["previous_hash"] = first["event_hash"]
    second["event_hash"] = sha({key: value for key, value in second.items() if key != "event_hash"})
    ledger.pop("export_checksum")
    ledger["export_checksum"] = sha(ledger)
    ledger_path = write_json(tmp_path / "boolean-sequence-ledger.json", ledger)

    report = audit_provenance(tmp_path, [paths[0], paths[1], paths[2], ledger_path, paths[4]])

    assert report["status"] == "INVALID"
    assert "malformed_ledger_event" in _codes(report)
    assert any(
        item["code"] == "malformed_ledger_event"
        and "positive integer" in item["detail"]
        for item in report["findings"]
    )


def test_unknown_record_schema_cannot_satisfy_a_typed_reference(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    ledger = json.loads(paths[3].read_text(encoding="utf-8"))
    source = ledger["records"][0]
    source["schema_version"] = "awareness-studio-research-cycle.v0"
    source["checksum"] = sha({key: value for key, value in source.items() if key != "checksum"})

    previous_hash = None
    for event in ledger["events"]:
        event.pop("event_hash", None)
        if event["event_type"] == "source_snapshot":
            event["payload"] = source
        event["previous_hash"] = previous_hash
        event["event_hash"] = sha(event)
        previous_hash = event["event_hash"]
    ledger.pop("export_checksum")
    ledger["export_checksum"] = sha(ledger)
    ledger_path = write_json(tmp_path / "unknown-record-schema-ledger.json", ledger)

    report = audit_provenance(tmp_path, [paths[0], paths[1], paths[2], ledger_path, paths[4]])

    assert "unverifiable_ledger_record_schema" in _codes(report)
    assert any(
        item["code"] == "unresolved_ledger_reference"
        and item["subject"] == "evidence-fixture-1.source_snapshot_ids"
        for item in report["findings"]
    )


def test_local_root_exclusion_uses_filesystem_resolved_path(tmp_path: Path) -> None:
    paths = valid_fixture(tmp_path)
    actual_source_root = tmp_path / "source_data"
    case_alias_resolves = (tmp_path / "SOURCE_DATA").is_dir()
    (actual_source_root / "local-input.fixture").write_bytes(b"synthetic local input\n")

    source_manifest = json.loads(paths[2].read_text(encoding="utf-8"))
    source_manifest["local_root"] = "SOURCE_DATA"
    source_manifest_path = write_json(tmp_path / "case-aliased-source-manifest.json", source_manifest)

    report = audit_provenance(
        tmp_path,
        [paths[0], paths[1], source_manifest_path, paths[3], paths[4]],
    )

    if case_alias_resolves:
        assert not any(path.lower().endswith("local-input.fixture") for path in report["orphan_artifacts"])
        assert not any(
            item["code"] == "orphan_artifact" and "local-input.fixture" in item["subject"]
            for item in report["findings"]
        )
    else:
        # On a case-sensitive filesystem the wrong-case declaration must not
        # be treated as an alias for the real directory.
        assert any(item["code"] == "source_root_unverifiable" for item in report["findings"])


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


def test_cycle_parent_loop_is_reported(tmp_path: Path) -> None:
    first = write_json(tmp_path / "cycle-a.json", ledger_export("cycle-a", [], parent_cycle_id="cycle-b"))
    second = write_json(tmp_path / "cycle-b.json", ledger_export("cycle-b", [], parent_cycle_id="cycle-a"))

    report = audit_provenance(tmp_path, [first, second])

    assert report["status"] == "INVALID"
    assert "cycle_parent_loop" in _codes(report)


def test_malformed_cycle_parent_is_reported_instead_of_crashing(tmp_path: Path) -> None:
    path = write_json(
        tmp_path / "malformed-parent.json",
        ledger_export("cycle-malformed-parent", [], parent_cycle_id=[]),
    )

    report = audit_provenance(tmp_path, [path])

    assert report["status"] == "INVALID"
    assert "malformed_cycle_parent_reference" in _codes(report)


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


def test_unsupported_typed_field_is_reported_without_joining(tmp_path: Path) -> None:
    cycle_id = "cycle-unsupported-edge"
    snapshot = ledger_record(
        "source_snapshot",
        cycle_id,
        snapshot_id="shared-namespace-text",
        source_uri="local:fixture",
        source_sha256="c" * 64,
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture",
        scientific_limitations=["Fixture only."],
    )
    claim = ledger_record(
        "claim",
        cycle_id,
        claim_id="claim-with-wrong-edge",
        statement="Fixture claim only.",
        evidence_ids=[],
        source_snapshot_ids=["shared-namespace-text"],
        evidence_class="hypothesis",
        claim_scope="fixture",
        scientific_limitations=["Not evidence."],
    )
    path = write_json(tmp_path / "unsupported-edge.json", ledger_export(cycle_id, [snapshot, claim]))

    report = audit_provenance(tmp_path, [path])

    finding = next(item for item in report["findings"] if item["code"] == "unsupported_typed_reference")
    assert finding["subject"] == "unsupported-edge.json:record[1]#/source_snapshot_ids"
    assert "no relationship was inferred" in finding["detail"]


def test_unknown_record_type_cannot_satisfy_a_generic_record_reference(tmp_path: Path) -> None:
    cycle_id = "cycle-unknown-generic-target"
    unknown = {
        "record_type": "source_pack_record",
        "record_id": "unknown-target-id",
        "cycle_id": cycle_id,
        "parent_ids": [],
        "child_ids": [],
        "status": "COMPLETED",
        "schema_version": "awareness-studio-research-cycle.v1",
    }
    unknown["checksum"] = sha(unknown)
    claim = ledger_record(
        "claim",
        cycle_id,
        claim_id="known-source-record",
        statement="Fixture claim only.",
        evidence_ids=[],
        parent_ids=["unknown-target-id"],
        evidence_class="hypothesis",
        claim_scope="fixture",
        scientific_limitations=["Not evidence."],
    )
    path = write_json(
        tmp_path / "unknown-generic-target.json",
        ledger_export(
            cycle_id,
            [unknown, claim],
            links=[{"parent_id": "unknown-target-id", "child_id": "known-source-record"}],
        ),
    )

    report = audit_provenance(tmp_path, [path])

    assert "unverifiable_ledger_record_type" in _codes(report)
    unresolved = next(item for item in report["findings"] if item["code"] == "unresolved_ledger_reference")
    assert "unknown-target-id" in unresolved["detail"]
    assert "unresolved_ledger_link" in _codes(report)


def test_typed_join_rejects_record_id_mismatching_record_type_identifier(tmp_path: Path) -> None:
    cycle_id = "cycle-record-id-mismatch"
    snapshot = ledger_record(
        "source_snapshot",
        cycle_id,
        snapshot_id="canonical-snapshot-id",
        source_uri="local:fixture",
        source_sha256="a" * 64,
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture",
        scientific_limitations=["Fixture only."],
    )
    snapshot["record_id"] = "forged-record-id"
    snapshot["checksum"] = sha({key: value for key, value in snapshot.items() if key != "checksum"})
    evidence = ledger_record(
        "evidence_record",
        cycle_id,
        evidence_id="evidence-identity-check",
        source_snapshot_ids=["forged-record-id"],
        observation="Fixture only.",
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture",
        scientific_limitations=["Not scientific evidence."],
        metrics={},
    )
    path = write_json(tmp_path / "identity-mismatch.json", ledger_export(cycle_id, [snapshot, evidence]))

    report = audit_provenance(tmp_path, [path])

    assert report["status"] == "INVALID"
    assert "ledger_record_identity_mismatch" in _codes(report)
    assert "unresolved_ledger_reference" in _codes(report)


def test_missing_serialized_record_id_is_not_inferred_from_typed_identifier(tmp_path: Path) -> None:
    cycle_id = "cycle-record-id-missing"
    snapshot = ledger_record(
        "source_snapshot",
        cycle_id,
        snapshot_id="snapshot-without-record-id",
        source_uri="local:fixture",
        source_sha256="b" * 64,
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture",
        scientific_limitations=["Fixture only."],
    )
    snapshot.pop("record_id")
    snapshot["checksum"] = sha({key: value for key, value in snapshot.items() if key != "checksum"})
    path = write_json(tmp_path / "missing-record-id.json", ledger_export(cycle_id, [snapshot]))

    report = audit_provenance(tmp_path, [path])

    assert report["status"] == "INVALID"
    assert "ledger_record_identity_mismatch" in _codes(report)


def test_file_identity_change_between_lstat_and_open_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "stable-file.json"
    path.write_bytes(b"before")
    original_open = os.open
    changed = False

    def replace_before_open(
        candidate: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        *args: object,
        **kwargs: object,
    ) -> int:
        nonlocal changed
        if Path(candidate) == path and not changed:
            changed = True
            path.write_bytes(b"replacement with a different length")
        return original_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(provenance_auditor.os, "open", replace_before_open)

    with pytest.raises(ValueError, match="file changed between validation and open"):
        provenance_auditor._read_stable_file(path, maximum=1024)


def test_final_component_symlink_swap_is_rejected_when_platform_allows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "selected.json"
    target = tmp_path / "target.json"
    path.write_bytes(b"selected-before-open")
    target.write_bytes(b"outside-target")
    original_open = os.open
    swapped = False

    def replace_with_symlink(
        candidate: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        *args: object,
        **kwargs: object,
    ) -> int:
        nonlocal swapped
        if Path(candidate) == path and not swapped:
            swapped = True
            path.unlink()
            try:
                os.symlink(target, path)
            except (OSError, NotImplementedError):
                pytest.skip("symbolic links are unavailable in this environment")
        return original_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(provenance_auditor.os, "open", replace_with_symlink)

    with pytest.raises((OSError, ValueError)):
        provenance_auditor._read_stable_file(path, maximum=1024)


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
