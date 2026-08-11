"""Structural validation tests for benchmarks.dataset_registry / artifact_registry.

Uses the real committed benchmarks/registry_seed.json where a real record is
needed, and small synthetic in-memory records (built directly via the
dataclasses) to exercise specific failure modes -- no fixture files, no
network, no raw data.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.artifact_registry import ArtifactRecordV1, compute_artifact_id
from benchmarks.dataset_registry import DatasetRecordV1
from benchmarks.export_registry import BenchmarkRegistry

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _base_dataset(**overrides):
    kwargs = dict(
        dataset_id="ds_test",
        display_name="Test dataset",
        modalities=["EEG"],
        current_role="development",
        allowed_uses=["transition_export"],
        forbidden_uses=["final_claim_confirmation"],
        contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling="L0_computational_artifact",
        provenance="synthetic test fixture",
        limitations=["test only"],
    )
    kwargs.update(overrides)
    return DatasetRecordV1.make(**kwargs)


def _base_artifact(**overrides):
    kwargs = dict(
        dataset_id="ds_test",
        path="tests/test_benchmarks_registry.py",
        artifact_kind="test_fixture",
        modality="EEG",
        current_role="development",
        allowed_uses=["transition_export"],
        forbidden_uses=["final_claim_confirmation"],
        contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling="L0_computational_artifact",
        produced_by="test fixture",
        limitations=["test only"],
    )
    kwargs.update(overrides)
    return ArtifactRecordV1.make(**kwargs)


# ── 1. DatasetRecord validation ─────────────────────────────────────────────

def test_seed_datasets_all_validate_cleanly():
    registry = BenchmarkRegistry.load(_SEED)
    for dataset_id, record in registry.datasets.items():
        assert record.validate() == [], (dataset_id, record.validate())


def test_valid_synthetic_dataset_passes():
    record = _base_dataset()
    assert record.validate() == []


def test_dataset_missing_limitations_fails():
    record = _base_dataset(limitations=[])
    errors = record.validate()
    assert any("limitations" in e for e in errors)


def test_dataset_unknown_role_fails():
    record = _base_dataset(current_role="not_a_real_role")
    errors = record.validate()
    assert any("current_role" in e for e in errors)


def test_dataset_allowed_uses_containing_blocked_use_fails():
    record = _base_dataset(allowed_uses=["transition_export", "clinical_claim"])
    errors = record.validate()
    assert any("clinical_claim" in e and "rule 6" in e for e in errors)


@pytest.mark.parametrize(
    "blocked_use",
    [
        "clinical_claim", "diagnostic_claim", "treatment_claim",
        "consciousness_biomarker_claim", "spiritual_attainment_claim",
        "mechanistic_causal_claim",
    ],
)
def test_each_always_blocked_use_rejected_in_allowed_uses(blocked_use):
    record = _base_dataset(allowed_uses=[blocked_use])
    errors = record.validate()
    assert any(blocked_use in e for e in errors)


def test_dataset_missing_provenance_fails():
    record = _base_dataset(provenance="")
    errors = record.validate()
    assert any("provenance" in e for e in errors)


def test_dataset_missing_dataset_id_fails():
    record = _base_dataset(dataset_id="")
    errors = record.validate()
    assert any("dataset_id" in e for e in errors)


def test_dataset_overlapping_allowed_and_forbidden_uses_fails():
    record = _base_dataset(allowed_uses=["transition_export"], forbidden_uses=["transition_export"])
    errors = record.validate()
    assert any("overlap" in e for e in errors)


# ── 2. ArtifactRecord validation ────────────────────────────────────────────

def test_seed_artifacts_all_validate_cleanly():
    registry = BenchmarkRegistry.load(_SEED)
    for artifact_id, record in registry.artifacts.items():
        assert record.validate() == [], (artifact_id, record.validate())


def test_valid_committed_artifact_with_existing_path_passes():
    # This file itself is a real, committed, existing repo file.
    record = _base_artifact(record_kind="committed_artifact", path="tests/test_benchmarks_registry.py")
    assert record.validate() == []


def test_committed_artifact_with_nonexistent_path_fails():
    record = _base_artifact(record_kind="committed_artifact", path="tests/does_not_exist_at_all.json")
    errors = record.validate()
    assert any("does not exist" in e and "rule 10" in e for e in errors)


def test_candidate_unstructured_record_passes_without_existing_file():
    record = _base_artifact(
        record_kind="candidate_unstructured",
        path="does/not/exist/at/all.json",
        produced_by="",
    )
    assert record.validate() == []


def test_committed_artifact_requires_produced_by():
    record = _base_artifact(record_kind="committed_artifact", produced_by="")
    errors = record.validate()
    assert any("produced_by" in e and "rule 9" in e for e in errors)


def test_relative_path_is_preserved_verbatim():
    record = _base_artifact(path="tests/test_benchmarks_registry.py")
    assert record.path == "tests/test_benchmarks_registry.py"
    assert record.to_dict()["path"] == "tests/test_benchmarks_registry.py"
    round_tripped = ArtifactRecordV1.from_dict(record.to_dict())
    assert round_tripped.path == "tests/test_benchmarks_registry.py"


def test_absolute_path_without_external_flag_fails():
    record = _base_artifact(record_kind="candidate_unstructured", path="/absolute/path/not/allowed.json")
    errors = record.validate()
    assert any("relative repository path" in e and "rule 10" in e for e in errors)


def test_external_path_skips_existence_check():
    record = _base_artifact(
        record_kind="committed_artifact",
        path="s3://example-bucket/not-a-local-file.json",
        external=True,
    )
    assert record.validate() == []


def test_artifact_id_is_deterministic():
    id1 = compute_artifact_id(
        dataset_id="ds005620", path="a/b.json", artifact_kind="k",
        modality="EEG", source_state="awake", target_state="sedated",
    )
    id2 = compute_artifact_id(
        dataset_id="ds005620", path="a/b.json", artifact_kind="k",
        modality="EEG", source_state="awake", target_state="sedated",
    )
    assert id1 == id2
    id3 = compute_artifact_id(
        dataset_id="ds005620", path="a/b.json", artifact_kind="different_kind",
        modality="EEG", source_state="awake", target_state="sedated",
    )
    assert id3 != id1


def test_dataset_family_artifact_ids_never_collide_across_feature_families():
    registry = BenchmarkRegistry.load(_SEED)
    ds005620_artifacts = registry.list_artifacts(dataset_id="ds005620")
    assert len(ds005620_artifacts) >= 2
    ids = [a.artifact_id for a in ds005620_artifacts]
    assert len(ids) == len(set(ids))


# ── serialization round-trip ─────────────────────────────────────────────

def test_dataset_record_round_trips_through_json():
    record = _base_dataset()
    round_tripped = DatasetRecordV1.from_dict(record.to_dict())
    assert round_tripped.to_dict() == record.to_dict()


def test_artifact_record_round_trips_through_json():
    record = _base_artifact()
    round_tripped = ArtifactRecordV1.from_dict(record.to_dict())
    assert round_tripped.to_dict() == record.to_dict()
