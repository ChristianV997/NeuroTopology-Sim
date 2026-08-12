"""Tests for `job_runner.worker.WorkerRunManifestV1`: dict roundtrip,
worker_run_id determinism, and structural validation rules."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from job_runner.validation import MAX_JOBS_CEILING, MAX_POLL_INTERVAL_SECONDS_CEILING
from job_runner.worker import WorkerRunManifestV1, compute_worker_run_id


def _valid_manifest(**overrides):
    kwargs = dict(
        jobs_root="outputs/jobs", worker_id="w1", max_jobs=1,
        limitations=["test worker manifest"], provenance="test",
        _now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    kwargs.update(overrides)
    return WorkerRunManifestV1.make(**kwargs)


def test_to_dict_from_dict_roundtrip():
    manifest = _valid_manifest(jobs_selected=["a"], jobs_completed=["a"])
    restored = WorkerRunManifestV1.from_dict(manifest.to_dict())
    assert restored == manifest


def test_to_json_from_json_roundtrip():
    manifest = _valid_manifest()
    restored = WorkerRunManifestV1.from_json(manifest.to_json())
    assert restored == manifest


def test_worker_run_id_stable_for_identical_inputs():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = _valid_manifest(_now=ts)
    b = _valid_manifest(_now=ts)
    assert a.worker_run_id == b.worker_run_id


def test_worker_run_id_changes_with_started_at():
    a = _valid_manifest(_now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    b = _valid_manifest(_now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert a.worker_run_id != b.worker_run_id


def test_compute_worker_run_id_is_pure_and_deterministic():
    first = compute_worker_run_id(
        jobs_root="outputs/jobs", worker_id="w1", started_at="2026-01-01T00:00:00+00:00",
        max_jobs=1, dry_run=False,
    )
    second = compute_worker_run_id(
        jobs_root="outputs/jobs", worker_id="w1", started_at="2026-01-01T00:00:00+00:00",
        max_jobs=1, dry_run=False,
    )
    assert first == second
    assert len(first) == 16


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


@pytest.mark.parametrize("max_jobs", [0, -1, MAX_JOBS_CEILING + 1, 1.5])
def test_max_jobs_out_of_bounds_is_invalid(max_jobs):
    manifest = _valid_manifest()
    manifest.max_jobs = max_jobs
    errors = manifest.validate()
    assert any("max_jobs" in e for e in errors)


@pytest.mark.parametrize("poll_interval", [-1, MAX_POLL_INTERVAL_SECONDS_CEILING + 1])
def test_poll_interval_out_of_bounds_is_invalid(poll_interval):
    manifest = _valid_manifest()
    manifest.poll_interval_seconds = poll_interval
    errors = manifest.validate()
    assert any("poll_interval_seconds" in e for e in errors)


def test_invalid_jobs_root_is_invalid():
    manifest = _valid_manifest(jobs_root="/tmp/not-allowed")
    errors = manifest.validate()
    assert any("jobs_root" in e for e in errors)


def test_dry_run_manifest_has_no_result_paths_when_selected_but_not_run():
    manifest = _valid_manifest(jobs_selected=["a", "b"], dry_run=True)
    assert manifest.result_paths == []
    assert manifest.jobs_completed == []


def test_lock_conflicts_field_records_conflicting_job_ids():
    manifest = _valid_manifest(jobs_selected=["a"], lock_conflicts=["a"])
    assert manifest.lock_conflicts == ["a"]


def test_no_claim_scope_or_evidence_level_field():
    manifest = _valid_manifest()
    assert not hasattr(manifest, "claim_scope")
    assert not hasattr(manifest, "evidence_level")


def test_banned_phrase_in_provenance_is_rejected():
    manifest = _valid_manifest(provenance="this run confirms diagnosis beyond doubt")
    errors = manifest.validate()
    assert any("banned phrase" in e for e in errors)
