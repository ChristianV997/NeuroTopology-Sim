"""DatasetAcquisitionManifestV1 validation + target-root safety
(dataset_acquisition.store). Synthetic fixtures only.
"""
from __future__ import annotations

from dataset_acquisition.manifest import DatasetAcquisitionManifestV1
from dataset_acquisition.store import TargetRootError, validate_target_root
from dataset_acquisition.validation import DatasetAcquisitionValidationError


def _minimal_valid_manifest(**overrides) -> DatasetAcquisitionManifestV1:
    kwargs = dict(
        plan_id="plan-1",
        candidate_id="cand-1",
        execution_status="planned_only",
        risks=["r"],
        limitations=["l"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return DatasetAcquisitionManifestV1.make(**kwargs)


def test_manifest_dict_roundtrip():
    manifest = _minimal_valid_manifest()
    d = manifest.to_dict()
    manifest2 = DatasetAcquisitionManifestV1.from_dict(d)
    assert manifest2.to_dict() == d


def test_manifest_json_roundtrip():
    manifest = _minimal_valid_manifest()
    text = manifest.to_json()
    manifest2 = DatasetAcquisitionManifestV1.from_json(text)
    assert manifest2.to_dict() == manifest.to_dict()


def test_valid_manifest_has_no_errors():
    assert _minimal_valid_manifest().validate() == []


def test_validation_fails_on_missing_limitations():
    manifest = _minimal_valid_manifest(limitations=[])
    assert any("limitations" in e for e in manifest.validate())


def test_validation_fails_on_missing_risks():
    manifest = _minimal_valid_manifest(risks=[])
    assert any("risks" in e for e in manifest.validate())


def test_validation_fails_on_missing_provenance():
    manifest = _minimal_valid_manifest(provenance="")
    assert any("provenance" in e for e in manifest.validate())


def test_validate_or_raise_raises():
    manifest = _minimal_valid_manifest(provenance="")
    try:
        manifest.validate_or_raise()
        assert False, "expected DatasetAcquisitionValidationError"
    except DatasetAcquisitionValidationError:
        pass


def test_planned_only_manifest_has_no_acquired_paths():
    manifest = _minimal_valid_manifest(execution_status="planned_only")
    assert manifest.validate() == []
    assert manifest.acquired_paths == []
    assert manifest.acquired_file_count == 0


def test_planned_only_manifest_with_acquired_paths_fails():
    manifest = _minimal_valid_manifest(execution_status="planned_only", acquired_paths=["outputs/x/y.tsv"], acquired_file_count=1)
    errors = manifest.validate()
    assert any("acquired_paths" in e for e in errors)


def test_verified_existing_manifest_records_local_files():
    manifest = _minimal_valid_manifest(
        execution_status="verified_existing",
        acquired_paths=["outputs/datasets/x/a.tsv", "outputs/datasets/x/b.tsv"],
        acquired_file_count=2,
        acquired_size_bytes=42,
        checksums={"outputs/datasets/x/a.tsv": "abc123"},
    )
    assert manifest.validate() == []
    assert manifest.acquired_file_count == 2
    assert manifest.checksums["outputs/datasets/x/a.tsv"] == "abc123"


def test_manifest_id_deterministic_for_identical_content():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    m1 = _minimal_valid_manifest(_now=now)
    m2 = _minimal_valid_manifest(_now=now)
    assert m1.manifest_id == m2.manifest_id


def test_manifest_id_differs_with_different_acquired_paths():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    m1 = _minimal_valid_manifest(_now=now, execution_status="verified_existing", acquired_paths=["a"])
    m2 = _minimal_valid_manifest(_now=now, execution_status="verified_existing", acquired_paths=["b"])
    assert m1.manifest_id != m2.manifest_id


def test_manifest_metadata_cannot_claim_evidence():
    manifest = _minimal_valid_manifest(metadata={"validation_ready": True})
    errors = manifest.validate()
    assert any("rule 15" in e for e in errors)


def test_manifest_banned_phrase_fails():
    manifest = _minimal_valid_manifest(provenance="this manifest is evidence of a real effect")
    errors = manifest.validate()
    assert any("banned phrase" in e for e in errors)


def test_bad_execution_status_fails():
    manifest = _minimal_valid_manifest(execution_status="not_a_real_status")
    errors = manifest.validate()
    assert any("execution_status" in e for e in errors)


# ── target-root safety (dataset_acquisition.store) ───────────────────────


def test_valid_target_root_under_outputs():
    resolved = validate_target_root("outputs/datasets/ds1")
    assert resolved.name == "ds1"


def test_valid_target_root_under_data():
    resolved = validate_target_root("data/ds999999")
    assert resolved.name == "ds999999"


def test_absolute_target_root_rejected():
    try:
        validate_target_root("/etc/passwd")
        assert False, "expected TargetRootError"
    except TargetRootError:
        pass


def test_target_root_outside_allowed_prefixes_rejected():
    for bad in ("adapters/evil", "core/evil", "tests/evil", "dataset_importers/evil"):
        try:
            validate_target_root(bad)
            assert False, f"expected TargetRootError for {bad}"
        except TargetRootError:
            pass


def test_target_root_traversal_rejected():
    try:
        validate_target_root("outputs/../secrets")
        assert False, "expected TargetRootError"
    except TargetRootError:
        pass


def test_empty_target_root_rejected():
    try:
        validate_target_root("")
        assert False, "expected TargetRootError"
    except TargetRootError:
        pass
