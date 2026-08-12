"""Tests for `job_runner.queue.JobQueueStateV1`: dict roundtrip,
queue_id determinism, and structural validation rules."""
from __future__ import annotations

from datetime import datetime, timezone

from job_runner.queue import JobQueueStateV1, compute_queue_id


def _valid_state(**overrides):
    kwargs = dict(
        jobs_root="outputs/jobs", limitations=["test queue state"], provenance="test",
        _now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    kwargs.update(overrides)
    return JobQueueStateV1.make(**kwargs)


def test_to_dict_from_dict_roundtrip():
    state = _valid_state(queued_job_ids=["a", "b"], completed_job_ids=["c"])
    restored = JobQueueStateV1.from_dict(state.to_dict())
    assert restored == state


def test_to_json_from_json_roundtrip():
    state = _valid_state()
    restored = JobQueueStateV1.from_json(state.to_json())
    assert restored == state


def test_queue_id_stable_for_identical_inputs():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = _valid_state(_now=ts)
    b = _valid_state(_now=ts)
    assert a.queue_id == b.queue_id


def test_queue_id_changes_with_last_scan_at():
    a = _valid_state(_now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    b = _valid_state(_now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert a.queue_id != b.queue_id


def test_compute_queue_id_is_pure_and_deterministic():
    first = compute_queue_id(jobs_root="outputs/jobs", last_scan_at="2026-01-01T00:00:00+00:00", total_jobs=3)
    second = compute_queue_id(jobs_root="outputs/jobs", last_scan_at="2026-01-01T00:00:00+00:00", total_jobs=3)
    assert first == second
    assert len(first) == 16


def test_total_jobs_defaults_to_sum_of_buckets():
    state = _valid_state(queued_job_ids=["a"], running_job_ids=["b"], completed_job_ids=["c", "d"])
    assert state.total_jobs == 4


def test_valid_state_has_no_errors():
    state = _valid_state()
    assert state.validate() == []
    state.validate_or_raise()


def test_empty_limitations_is_invalid():
    state = _valid_state(limitations=[])
    errors = state.validate()
    assert any("limitations" in e for e in errors)


def test_empty_provenance_is_invalid():
    state = _valid_state(provenance="")
    errors = state.validate()
    assert any("provenance" in e for e in errors)


def test_invalid_jobs_root_is_invalid():
    state = _valid_state(jobs_root="/tmp/not-allowed")
    errors = state.validate()
    assert any("jobs_root" in e for e in errors)


def test_no_claim_scope_or_evidence_level_field():
    state = _valid_state()
    assert not hasattr(state, "claim_scope")
    assert not hasattr(state, "evidence_level")


def test_banned_phrase_in_provenance_is_rejected():
    state = _valid_state(provenance="this run confirms diagnosis beyond doubt")
    errors = state.validate()
    assert any("banned phrase" in e for e in errors)
