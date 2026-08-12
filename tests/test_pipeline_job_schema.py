"""Tests for `job_runner.job.PipelineJobV1`: dict/JSON roundtrip, job_id
determinism, and structural validation rules."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from job_runner.job import PipelineJobV1, compute_job_id
from job_runner.validation import MAX_ATTEMPTS_CEILING


def _valid_job(**overrides):
    kwargs = dict(
        output_root="outputs/jobs/demo",
        pipeline_spec_path="some/spec.json",
        requested_outputs=["report_pack"],
        limitations=["test job"], provenance="test",
        _now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    kwargs.update(overrides)
    return PipelineJobV1.make(**kwargs)


def test_to_dict_from_dict_roundtrip():
    job = _valid_job(job_name="roundtrip job")
    restored = PipelineJobV1.from_dict(job.to_dict())
    assert restored == job


def test_to_json_from_json_roundtrip():
    job = _valid_job()
    restored = PipelineJobV1.from_json(job.to_json())
    assert restored == job


def test_job_id_is_stable_for_identical_inputs():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = _valid_job(_now=ts)
    b = _valid_job(_now=ts)
    assert a.job_id == b.job_id


def test_job_id_changes_with_created_at():
    a = _valid_job(_now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    b = _valid_job(_now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert a.job_id != b.job_id


def test_job_id_changes_with_requested_outputs():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = _valid_job(_now=ts, requested_outputs=["report_pack"])
    b = _valid_job(_now=ts, requested_outputs=["html_report_pack"])
    assert a.job_id != b.job_id


def test_compute_job_id_is_pure_and_deterministic():
    first = compute_job_id(
        pipeline_identity="spec.json", requested_outputs=["report_pack"],
        output_root="outputs/jobs/demo", created_at="2026-01-01T00:00:00+00:00",
    )
    second = compute_job_id(
        pipeline_identity="spec.json", requested_outputs=["report_pack"],
        output_root="outputs/jobs/demo", created_at="2026-01-01T00:00:00+00:00",
    )
    assert first == second
    assert len(first) == 16


def test_valid_job_has_no_errors():
    job = _valid_job()
    assert job.validate() == []
    job.validate_or_raise()


def test_empty_limitations_is_invalid():
    job = _valid_job(limitations=[])
    errors = job.validate()
    assert any("limitations" in e for e in errors)


def test_empty_provenance_is_invalid():
    job = _valid_job(provenance="")
    errors = job.validate()
    assert any("provenance" in e for e in errors)


def test_missing_spec_reference_is_invalid():
    job = _valid_job(pipeline_spec_path=None, pipeline_spec={})
    errors = job.validate()
    assert any("pipeline_spec" in e for e in errors)


def test_invalid_output_root_is_invalid():
    job = _valid_job(output_root="/tmp/not-allowed")
    errors = job.validate()
    assert any("output_root" in e for e in errors)


def test_invalid_job_status_is_invalid():
    job = _valid_job()
    job.job_status = "not_a_real_status"
    errors = job.validate()
    assert any("job_status" in e for e in errors)


def test_unsupported_requested_output_is_invalid():
    job = _valid_job(requested_outputs=["pdf_export"])
    errors = job.validate()
    assert any("requested_outputs" in e for e in errors)


@pytest.mark.parametrize("max_attempts", [0, -1, MAX_ATTEMPTS_CEILING + 1, 1.5])
def test_max_attempts_out_of_bounds_is_invalid(max_attempts):
    job = _valid_job()
    job.max_attempts = max_attempts
    errors = job.validate()
    assert any("max_attempts" in e for e in errors)


def test_running_without_started_at_is_invalid():
    job = _valid_job()
    job.job_status = "running"
    errors = job.validate()
    assert any("started_at" in e for e in errors)


def test_completed_without_completed_at_is_invalid():
    job = _valid_job()
    job.job_status = "completed"
    errors = job.validate()
    assert any("completed_at" in e for e in errors)


def test_failed_without_error_summary_is_invalid():
    job = _valid_job()
    job.job_status = "failed"
    errors = job.validate()
    assert any("error_summary" in e for e in errors)


def test_no_claim_scope_or_evidence_level_field():
    job = _valid_job()
    assert not hasattr(job, "claim_scope")
    assert not hasattr(job, "evidence_level")


def test_banned_phrase_in_job_name_is_rejected():
    job = _valid_job(job_name="this run confirms diagnosis beyond doubt")
    errors = job.validate()
    assert any("banned phrase" in e for e in errors)
