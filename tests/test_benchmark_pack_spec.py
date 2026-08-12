"""Tests for `benchmark_packs.pack_spec.BenchmarkPackSpecV1`: dict/JSON
roundtrip, benchmark_pack_spec_id determinism, and structural validation
rules."""
from __future__ import annotations

import pytest

from benchmark_packs.pack_spec import BenchmarkPackSpecV1, compute_benchmark_pack_spec_id
from benchmark_packs.validation import ALLOWED_PACK_KINDS


def _valid_spec(**overrides):
    kwargs = dict(
        pack_name="demo pack", output_root="outputs/benchmark_packs/demo",
        pipeline_spec_paths=["a.json", "b.json"], requested_outputs=["report_pack"],
        limitations=["test spec"], provenance="test",
    )
    kwargs.update(overrides)
    return BenchmarkPackSpecV1.make(**kwargs)


def test_to_dict_from_dict_roundtrip():
    spec = _valid_spec(pack_purpose="demo purpose")
    restored = BenchmarkPackSpecV1.from_dict(spec.to_dict())
    assert restored == spec


def test_to_json_from_json_roundtrip():
    spec = _valid_spec()
    restored = BenchmarkPackSpecV1.from_json(spec.to_json())
    assert restored == spec


def test_benchmark_pack_spec_id_is_stable_for_identical_inputs():
    a = _valid_spec()
    b = _valid_spec()
    assert a.benchmark_pack_spec_id == b.benchmark_pack_spec_id


def test_benchmark_pack_spec_id_changes_with_pack_name():
    a = _valid_spec(pack_name="pack a")
    b = _valid_spec(pack_name="pack b")
    assert a.benchmark_pack_spec_id != b.benchmark_pack_spec_id


def test_benchmark_pack_spec_id_changes_with_pipeline_spec_paths():
    a = _valid_spec(pipeline_spec_paths=["a.json"])
    b = _valid_spec(pipeline_spec_paths=["b.json"])
    assert a.benchmark_pack_spec_id != b.benchmark_pack_spec_id


def test_recompute_id_matches_original():
    spec = _valid_spec()
    assert spec.recompute_id() == spec.benchmark_pack_spec_id


def test_compute_benchmark_pack_spec_id_is_pure_and_deterministic():
    first = compute_benchmark_pack_spec_id(
        pack_name="demo", pack_kind="demo_pack", pipeline_spec_identities=["a.json"],
        requested_outputs=["report_pack"], output_root="outputs/benchmark_packs/demo",
    )
    second = compute_benchmark_pack_spec_id(
        pack_name="demo", pack_kind="demo_pack", pipeline_spec_identities=["a.json"],
        requested_outputs=["report_pack"], output_root="outputs/benchmark_packs/demo",
    )
    assert first == second
    assert len(first) == 16


def test_valid_spec_has_no_errors():
    spec = _valid_spec()
    assert spec.validate() == []
    spec.validate_or_raise()


def test_empty_limitations_is_invalid():
    spec = _valid_spec(limitations=[])
    errors = spec.validate()
    assert any("limitations" in e for e in errors)


def test_empty_provenance_is_invalid():
    spec = _valid_spec(provenance="")
    errors = spec.validate()
    assert any("provenance" in e for e in errors)


def test_invalid_pack_kind_is_invalid():
    spec = _valid_spec()
    spec.pack_kind = "not_a_real_kind"
    errors = spec.validate()
    assert any("pack_kind" in e for e in errors)


@pytest.mark.parametrize("kind", sorted(ALLOWED_PACK_KINDS))
def test_every_allowed_pack_kind_is_accepted(kind):
    spec = _valid_spec(pack_kind=kind)
    errors = spec.validate()
    assert not any("pack_kind" in e for e in errors)


def test_invalid_output_root_is_invalid():
    spec = _valid_spec(output_root="/tmp/not-allowed")
    errors = spec.validate()
    assert any("output_root" in e for e in errors)


def test_invalid_jobs_root_is_invalid():
    spec = _valid_spec(jobs_root="/tmp/not-allowed")
    errors = spec.validate()
    assert any("jobs_root" in e for e in errors)


def test_unsupported_requested_output_is_invalid():
    spec = _valid_spec(requested_outputs=["pdf_export"])
    errors = spec.validate()
    assert any("requested_outputs" in e for e in errors)


def test_missing_pipeline_specs_is_invalid():
    spec = _valid_spec(pipeline_spec_paths=[])
    errors = spec.validate()
    assert any("pipeline_specs or pipeline_spec_paths" in e for e in errors)


def test_embedded_pipeline_spec_validates():
    from workflows.report_pipeline import ReportPipelineSpecV1

    bad_pipeline_spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root="outputs/report_packs/embedded-bad", source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        limitations=["test"], provenance="test",
    ).to_dict()
    bad_pipeline_spec["dataset_id"] = ""  # now structurally invalid

    spec = _valid_spec(pipeline_specs=[bad_pipeline_spec], pipeline_spec_paths=[])
    errors = spec.validate()
    assert any("pipeline_specs[0]" in e for e in errors)


def test_embedded_valid_pipeline_spec_has_no_errors():
    from workflows.report_pipeline import ReportPipelineSpecV1

    good_pipeline_spec = ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root="outputs/report_packs/embedded-good", source_paths=["contracts/btc_icft/ds005620/pitnn_cohort"],
        registry_path="benchmarks/registry_seed.json", include_report=True,
        limitations=["test"], provenance="test",
    ).to_dict()

    spec = _valid_spec(pipeline_specs=[good_pipeline_spec], pipeline_spec_paths=[])
    assert spec.validate() == []


def test_no_claim_scope_or_evidence_level_field():
    spec = _valid_spec()
    assert not hasattr(spec, "claim_scope")
    assert not hasattr(spec, "evidence_level")
    assert not hasattr(spec, "validation_ready")


def test_banned_phrase_in_pack_name_is_rejected():
    spec = _valid_spec(pack_name="this run confirms diagnosis beyond doubt")
    errors = spec.validate()
    assert any("banned phrase" in e for e in errors)
