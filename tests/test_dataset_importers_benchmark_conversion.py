"""Benchmark-candidate conversion: DatasetCandidateRecordV1 ->
DatasetRecordV1/ArtifactRecordV1 (conservative, never validation-ready,
never mutating the seed benchmark registry). Also covers the two new
AdapterContractV1 registrations for the MOABB/EEGDash importers.
"""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.artifact_registry import ArtifactRecordV1
from benchmarks.dataset_registry import DatasetRecordV1
from dataset_importers.candidate_record import DatasetCandidateRecordV1
from dataset_importers.export_candidates import convert_candidates_to_benchmark_records
from external_tools.adapter_contract import load_adapter_contracts

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
_ADAPTER_CONTRACTS_SEED = _REPO_ROOT / "external_tools" / "adapter_contracts_seed.json"


def _candidate(**overrides) -> DatasetCandidateRecordV1:
    kwargs = dict(
        source_catalog="synthetic_fixture",
        source_dataset_id=overrides.pop("source_dataset_id", "ds-conv-1"),
        display_name="Conversion fixture dataset",
        license="CC0",
        license_risk="permissive_low",
        access_status="public",
        download_required="true",
        modalities=["EEG"],
        condition_labels=["rest", "task"],
        subject_count=10,
        transition_readiness="candidate_transition_possible",
        benchmark_role_recommendation="development_candidate",
        potential_transition_classes=["rest_vs_task"],
        public_url="https://example.org/dataset",
        risks=["r"],
        limitations=["l"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return DatasetCandidateRecordV1.make(**kwargs)


def test_high_quality_candidate_converts_to_conservative_records():
    candidate = _candidate()
    result = convert_candidates_to_benchmark_records([candidate])
    assert len(result["dataset_records"]) == 1
    assert len(result["artifact_records"]) == 1

    ds = result["dataset_records"][0]
    art = result["artifact_records"][0]
    assert isinstance(ds, DatasetRecordV1)
    assert isinstance(art, ArtifactRecordV1)
    assert ds.validate() == []
    assert art.validate() == []


def test_output_registry_candidate_does_not_allow_final_confirmation():
    candidate = _candidate()
    result = convert_candidates_to_benchmark_records([candidate])
    ds = result["dataset_records"][0]
    art = result["artifact_records"][0]
    assert "final_claim_confirmation" not in ds.allowed_uses
    assert "final_claim_confirmation" in ds.forbidden_uses
    assert "final_claim_confirmation" not in art.allowed_uses
    assert "final_claim_confirmation" in art.forbidden_uses
    assert "transition_export" not in ds.allowed_uses
    assert "phase_space_export" not in ds.allowed_uses


def test_no_candidate_is_validation_ready():
    candidate = _candidate()
    result = convert_candidates_to_benchmark_records([candidate])
    ds = result["dataset_records"][0]
    art = result["artifact_records"][0]
    assert ds.current_role == "exploration"
    assert ds.contamination_status == "unseen"
    assert ds.evidence_level_ceiling == "L0_computational_artifact"
    assert ds.claim_scope_ceiling == "exploratory_metric"
    assert art.current_role == "exploration"
    assert art.record_kind == "candidate_unstructured"


def test_blocked_and_review_needed_candidates_are_not_converted():
    blocked = _candidate(
        source_dataset_id="blocked-ds",
        transition_readiness="blocked_missing_metadata",
        benchmark_role_recommendation="blocked",
        condition_labels=[],
        subject_count=None,
    )
    review_needed = _candidate(
        source_dataset_id="review-ds",
        access_status="unknown",
        benchmark_role_recommendation="review_needed",
    )
    result = convert_candidates_to_benchmark_records([blocked, review_needed])
    assert result["dataset_records"] == []
    assert result["artifact_records"] == []


def test_documentation_only_candidates_are_not_converted():
    doc_only = _candidate(
        source_dataset_id="doc-only-ds",
        condition_labels=[],
        subject_count=None,
        transition_readiness="metadata_only",
        benchmark_role_recommendation="documentation_only",
    )
    result = convert_candidates_to_benchmark_records([doc_only])
    assert result["dataset_records"] == []


def test_exploration_candidate_is_converted():
    exploration = _candidate(
        source_dataset_id="exploration-ds",
        subject_count=None,
        transition_readiness="derived_feature_extraction_needed",
        benchmark_role_recommendation="exploration_candidate",
    )
    result = convert_candidates_to_benchmark_records([exploration])
    assert len(result["dataset_records"]) == 1


def test_seed_benchmark_registry_is_not_mutated():
    original_text = _SEED_REGISTRY.read_text(encoding="utf-8")
    candidate = _candidate()
    convert_candidates_to_benchmark_records([candidate])
    assert _SEED_REGISTRY.read_text(encoding="utf-8") == original_text


def test_conversion_output_is_independent_json_file(tmp_path):
    candidate = _candidate()
    result = convert_candidates_to_benchmark_records([candidate])
    out = tmp_path / "bench.json"
    payload = {
        "dataset_records": [r.to_dict() for r in result["dataset_records"]],
        "artifact_records": [r.to_dict() for r in result["artifact_records"]],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded["dataset_records"][0]["dataset_id"].startswith("synthetic-fixture-")


def test_dataset_ids_distinct_across_source_catalogs():
    moabb_like = _candidate(source_catalog="synthetic_fixture", source_dataset_id="same-id")
    result = convert_candidates_to_benchmark_records([moabb_like])
    assert result["dataset_records"][0].dataset_id == "synthetic-fixture-same-id"


# ── external-tool / adapter-contract integration ─────────────────────────


def test_moabb_and_eegdash_adapter_contracts_exist_and_validate():
    contracts = load_adapter_contracts(_ADAPTER_CONTRACTS_SEED)
    by_tool = {c.tool_id: c for c in contracts.values()}
    assert "moabb" in by_tool
    assert "eegdash" in by_tool
    for tool_id in ("moabb", "eegdash"):
        contract = by_tool[tool_id]
        assert contract.validate() == []
        assert contract.integration_mode == "metadata_import"
        for target in ("external_metadata_only", "DatasetRecordV1", "ArtifactRecordV1"):
            assert target in contract.output_targets
        assert contract.allowed_claim_scope_ceiling in ("computational_artifact", "exploratory_metric")
        assert contract.evidence_level_ceiling == "L0_computational_artifact"


def test_moabb_and_eegdash_adapter_contracts_are_distinct():
    contracts = load_adapter_contracts(_ADAPTER_CONTRACTS_SEED)
    by_tool = {c.tool_id: c for c in contracts.values()}
    assert by_tool["moabb"].adapter_id != by_tool["eegdash"].adapter_id
