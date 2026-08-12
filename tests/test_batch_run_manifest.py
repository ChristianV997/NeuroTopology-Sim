"""Tests for `job_runner.batch_manifest.BatchRunManifestV1`: dict
roundtrip, batch_id determinism, and structural validation rules."""
from __future__ import annotations

from datetime import datetime, timezone

from job_runner.batch_manifest import BatchRunManifestV1, compute_batch_id


def _valid_manifest(**overrides):
    kwargs = dict(
        jobs_root="outputs/jobs", spec_paths=["a.json", "b.json"], batch_name="demo",
        limitations=["test batch manifest"], provenance="test",
        _now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    kwargs.update(overrides)
    return BatchRunManifestV1.make(**kwargs)


def test_to_dict_from_dict_roundtrip():
    manifest = _valid_manifest(job_ids=["j1", "j2"])
    restored = BatchRunManifestV1.from_dict(manifest.to_dict())
    assert restored == manifest


def test_to_json_from_json_roundtrip():
    manifest = _valid_manifest()
    restored = BatchRunManifestV1.from_json(manifest.to_json())
    assert restored == manifest


def test_batch_id_stable_for_identical_inputs():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = _valid_manifest(_now=ts)
    b = _valid_manifest(_now=ts)
    assert a.batch_id == b.batch_id


def test_batch_id_changes_with_created_at():
    a = _valid_manifest(_now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    b = _valid_manifest(_now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert a.batch_id != b.batch_id


def test_batch_id_changes_with_spec_paths():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = _valid_manifest(_now=ts, spec_paths=["a.json"])
    b = _valid_manifest(_now=ts, spec_paths=["b.json"])
    assert a.batch_id != b.batch_id


def test_compute_batch_id_is_pure_and_deterministic():
    first = compute_batch_id(jobs_root="outputs/jobs", batch_name="demo", spec_paths=["a.json"], created_at="2026-01-01T00:00:00+00:00")
    second = compute_batch_id(jobs_root="outputs/jobs", batch_name="demo", spec_paths=["a.json"], created_at="2026-01-01T00:00:00+00:00")
    assert first == second
    assert len(first) == 16


def test_recompute_id_matches_original():
    manifest = _valid_manifest()
    assert manifest.recompute_id() == manifest.batch_id


def test_created_batch_records_job_ids_and_spec_paths():
    manifest = _valid_manifest(job_ids=["j1", "j2"])
    assert manifest.job_ids == ["j1", "j2"]
    assert manifest.spec_paths == ["a.json", "b.json"]
    assert manifest.batch_status == "created"


def test_valid_manifest_has_no_errors():
    manifest = _valid_manifest()
    assert manifest.validate() == []
    manifest.validate_or_raise()


def test_empty_limitations_is_invalid():
    manifest = _valid_manifest(limitations=[])
    errors = manifest.validate()
    assert any("limitations" in e for e in errors)


def test_empty_provenance_is_invalid():
    manifest = _valid_manifest(provenance="")
    errors = manifest.validate()
    assert any("provenance" in e for e in errors)


def test_empty_spec_paths_is_invalid():
    manifest = _valid_manifest(spec_paths=[])
    errors = manifest.validate()
    assert any("spec_paths" in e for e in errors)


def test_invalid_jobs_root_is_invalid():
    manifest = _valid_manifest(jobs_root="/tmp/not-allowed")
    errors = manifest.validate()
    assert any("jobs_root" in e for e in errors)


def test_invalid_batch_status_is_invalid():
    manifest = _valid_manifest()
    manifest.batch_status = "not_a_real_status"
    errors = manifest.validate()
    assert any("batch_status" in e for e in errors)


def test_unsupported_requested_output_is_invalid():
    manifest = _valid_manifest(requested_outputs=["pdf_export"])
    errors = manifest.validate()
    assert any("requested_outputs" in e for e in errors)


def test_status_aggregation_counts_are_settable_and_roundtrip():
    manifest = _valid_manifest(job_ids=["j1", "j2", "j3"])
    manifest.completed_count = 2
    manifest.failed_count = 1
    manifest.batch_status = "completed_with_failures"
    restored = BatchRunManifestV1.from_dict(manifest.to_dict())
    assert restored.completed_count == 2
    assert restored.failed_count == 1
    assert restored.batch_status == "completed_with_failures"


def test_no_claim_scope_or_evidence_level_field():
    manifest = _valid_manifest()
    assert not hasattr(manifest, "claim_scope")
    assert not hasattr(manifest, "evidence_level")


def test_banned_phrase_in_provenance_is_rejected():
    manifest = _valid_manifest(provenance="this run confirms diagnosis beyond doubt")
    errors = manifest.validate()
    assert any("banned phrase" in e for e in errors)
