"""Tests for `benchmark_packs.pack_manifest.BenchmarkPackV1`/
`BenchmarkPackIndexV1`: dict roundtrip, id determinism, and structural
validation rules."""
from __future__ import annotations

from benchmark_packs.pack_manifest import (
    BenchmarkPackIndexV1,
    BenchmarkPackV1,
    compute_benchmark_pack_id,
    compute_index_id,
)


def _valid_pack(**overrides):
    kwargs = dict(
        source_spec_id="spec1", batch_id="batch1", report_pack_ids=["rp1"], html_pack_ids=["hp1"],
        pack_name="demo pack", pack_kind="demo_pack", pack_purpose="demo purpose",
        execution_summary={"total_jobs": 1, "completed": 1, "failed": 0, "status": "completed"},
        coverage_summary={"n_report_packs": 1},
        limitations=["test pack"],
    )
    kwargs.update(overrides)
    return BenchmarkPackV1.make(**kwargs)


def _valid_index(**overrides):
    kwargs = dict(
        benchmark_pack_id="pack1", linked_html_packs=["outputs/x/html/index.html"],
        title="Demo Pack", limitations=["test index"],
    )
    kwargs.update(overrides)
    return BenchmarkPackIndexV1.make(**kwargs)


# -- BenchmarkPackV1 --


def test_pack_to_dict_from_dict_roundtrip():
    pack = _valid_pack(job_ids=["j1"], pipeline_ids=["p1"])
    restored = BenchmarkPackV1.from_dict(pack.to_dict())
    assert restored == pack


def test_pack_to_json_from_json_roundtrip():
    pack = _valid_pack()
    restored = BenchmarkPackV1.from_json(pack.to_json())
    assert restored == pack


def test_benchmark_pack_id_stable_for_identical_inputs():
    a = _valid_pack()
    b = _valid_pack()
    assert a.benchmark_pack_id == b.benchmark_pack_id


def test_benchmark_pack_id_changes_with_batch_id():
    a = _valid_pack(batch_id="batch1")
    b = _valid_pack(batch_id="batch2")
    assert a.benchmark_pack_id != b.benchmark_pack_id


def test_benchmark_pack_id_changes_with_report_pack_ids():
    a = _valid_pack(report_pack_ids=["rp1"])
    b = _valid_pack(report_pack_ids=["rp2"])
    assert a.benchmark_pack_id != b.benchmark_pack_id


def test_compute_benchmark_pack_id_is_pure_and_deterministic():
    first = compute_benchmark_pack_id(source_spec_id="s1", batch_id="b1", report_pack_ids=["rp1"], html_pack_ids=[])
    second = compute_benchmark_pack_id(source_spec_id="s1", batch_id="b1", report_pack_ids=["rp1"], html_pack_ids=[])
    assert first == second
    assert len(first) == 16


def test_pack_includes_job_pipeline_report_html_ids():
    pack = _valid_pack(job_ids=["j1", "j2"], pipeline_ids=["p1"], report_pack_ids=["rp1"], html_pack_ids=["hp1"])
    assert pack.job_ids == ["j1", "j2"]
    assert pack.pipeline_ids == ["p1"]
    assert pack.report_pack_ids == ["rp1"]
    assert pack.html_pack_ids == ["hp1"]


def test_pack_valid_has_no_errors():
    pack = _valid_pack()
    assert pack.validate() == []
    pack.validate_or_raise()


def test_pack_empty_limitations_is_invalid():
    pack = _valid_pack(limitations=[])
    errors = pack.validate()
    assert any("limitations" in e for e in errors)


def test_pack_execution_summary_required():
    pack = _valid_pack(execution_summary={})
    errors = pack.validate()
    assert any("execution_summary" in e for e in errors)


def test_pack_coverage_summary_required():
    pack = _valid_pack(coverage_summary={})
    errors = pack.validate()
    assert any("coverage_summary" in e for e in errors)


def test_pack_blocked_interpretations_default_non_empty():
    pack = _valid_pack()
    assert pack.blocked_interpretations


def test_pack_blocked_interpretations_required():
    pack = _valid_pack(blocked_interpretations=[])
    errors = pack.validate()
    assert any("blocked_interpretations" in e for e in errors)


def test_pack_no_claim_scope_or_evidence_level_field():
    pack = _valid_pack()
    assert not hasattr(pack, "claim_scope")
    assert not hasattr(pack, "evidence_level")
    assert not hasattr(pack, "validation_ready")


def test_pack_banned_phrase_in_pack_purpose_is_rejected():
    pack = _valid_pack(pack_purpose="this run confirms diagnosis beyond doubt")
    errors = pack.validate()
    assert any("banned phrase" in e for e in errors)


# -- BenchmarkPackIndexV1 --


def test_index_to_dict_from_dict_roundtrip():
    index = _valid_index(sections_rendered=["Purpose"])
    restored = BenchmarkPackIndexV1.from_dict(index.to_dict())
    assert restored == index


def test_index_id_stable_for_identical_inputs():
    a = _valid_index()
    b = _valid_index()
    assert a.index_id == b.index_id


def test_index_id_changes_with_linked_html_packs():
    a = _valid_index(linked_html_packs=["a.html"])
    b = _valid_index(linked_html_packs=["b.html"])
    assert a.index_id != b.index_id


def test_compute_index_id_is_pure_and_deterministic():
    first = compute_index_id(benchmark_pack_id="pack1", linked_html_packs=["a.html"])
    second = compute_index_id(benchmark_pack_id="pack1", linked_html_packs=["a.html"])
    assert first == second
    assert len(first) == 16


def test_index_valid_has_no_errors():
    index = _valid_index()
    assert index.validate() == []
    index.validate_or_raise()


def test_index_empty_limitations_is_invalid():
    index = _valid_index(limitations=[])
    errors = index.validate()
    assert any("limitations" in e for e in errors)


def test_index_no_claim_scope_or_evidence_level_field():
    index = _valid_index()
    assert not hasattr(index, "claim_scope")
    assert not hasattr(index, "evidence_level")
