"""Tests for `job_runner.result.PipelineJobResultV1`: dict roundtrip,
result_id determinism, and structural validation rules."""
from __future__ import annotations

from job_runner.result import PipelineJobResultV1, compute_result_id


def _valid_result(**overrides):
    kwargs = dict(
        job_id="abc123", job_status="completed", output_root="outputs/jobs/demo",
        limitations=["test result"], provenance="test",
    )
    kwargs.update(overrides)
    return PipelineJobResultV1.make(**kwargs)


def test_to_dict_from_dict_roundtrip():
    result = _valid_result(report_pack_id="rp1", generated_files=["a.json", "b.json"])
    restored = PipelineJobResultV1.from_dict(result.to_dict())
    assert restored == result


def test_to_json_from_json_roundtrip():
    result = _valid_result()
    restored = PipelineJobResultV1.from_json(result.to_json())
    assert restored == result


def test_result_id_stable_for_same_outcome():
    a = _valid_result(report_pack_id="rp1", generated_files=["a.json"])
    b = _valid_result(report_pack_id="rp1", generated_files=["a.json"])
    assert a.result_id == b.result_id


def test_result_id_does_not_depend_on_created_at():
    result = _valid_result(report_pack_id="rp1")
    assert result.recompute_id() == result.result_id
    # created_at differs across two independently-made objects but result_id
    # (the "same finished outcome" identity) still matches.
    other = _valid_result(report_pack_id="rp1")
    assert result.created_at != "" and other.created_at != ""
    assert result.result_id == other.result_id


def test_result_id_changes_with_job_status():
    a = _valid_result(job_status="completed")
    b = _valid_result(job_status="failed", errors=["boom"])
    assert a.result_id != b.result_id


def test_compute_result_id_is_pure_and_deterministic():
    first = compute_result_id(
        job_id="abc123", job_status="completed", report_pack_id="rp1",
        html_pack_id=None, generated_files=["a.json"],
    )
    second = compute_result_id(
        job_id="abc123", job_status="completed", report_pack_id="rp1",
        html_pack_id=None, generated_files=["a.json"],
    )
    assert first == second
    assert len(first) == 16


def test_valid_result_has_no_errors():
    result = _valid_result()
    assert result.validate() == []
    result.validate_or_raise()


def test_empty_limitations_is_invalid():
    result = _valid_result(limitations=[])
    errors = result.validate()
    assert any("limitations" in e for e in errors)


def test_empty_provenance_is_invalid():
    result = _valid_result(provenance="")
    errors = result.validate()
    assert any("provenance" in e for e in errors)


def test_failed_result_without_errors_is_invalid():
    result = _valid_result(job_status="failed", errors=[])
    errors = result.validate()
    assert any("errors" in e for e in errors)


def test_failed_result_with_errors_is_valid():
    result = _valid_result(job_status="failed", errors=["something broke"])
    assert result.validate() == []


def test_invalid_job_status_is_invalid():
    result = _valid_result()
    result.job_status = "not_a_real_status"
    errors = result.validate()
    assert any("job_status" in e for e in errors)


def test_no_claim_scope_or_evidence_level_field():
    result = _valid_result()
    assert not hasattr(result, "claim_scope")
    assert not hasattr(result, "evidence_level")


def test_result_records_generated_paths_for_completed_job():
    result = _valid_result(
        report_pack_id="rp1", html_pack_id="hp1",
        generated_files=["outputs/report_packs/demo/ReportPack.json"],
    )
    assert result.report_pack_id == "rp1"
    assert result.html_pack_id == "hp1"
    assert "outputs/report_packs/demo/ReportPack.json" in result.generated_files


def test_banned_phrase_in_provenance_is_rejected():
    result = _valid_result(provenance="this run confirms diagnosis beyond doubt")
    errors = result.validate()
    assert any("banned phrase" in e for e in errors)
