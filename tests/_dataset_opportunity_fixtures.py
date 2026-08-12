"""Shared synthetic-fixture helpers for the dataset_opportunities test suite.
Not a pytest test module itself (no test_ prefix)."""
from __future__ import annotations

from dataset_importers.candidate_record import DatasetCandidateRecordV1


def make_good_candidate(dataset_id: str = "ds000123") -> DatasetCandidateRecordV1:
    return DatasetCandidateRecordV1.make(
        source_catalog="eegdash",
        source_dataset_id=dataset_id,
        display_name="Good Candidate",
        public_url=f"https://openneuro.org/datasets/{dataset_id}",
        license="CC0",
        license_risk="permissive_low",
        access_status="public",
        modalities=["EEG"],
        task_labels=["rest", "trance"],
        condition_labels=["baseline", "altered"],
        subject_count=13,
        available_metadata=["bids"],
        transition_readiness="candidate_transition_possible",
        compatible_adapters=["mne_bids"],
        recommended_next_action="review",
        benchmark_role_recommendation="development_candidate",
        provenance="synthetic fixture, not a real dataset query",
        limitations=["synthetic fixture only"],
        risks=["metadata may be incomplete"],
    )


def make_blocked_candidate(dataset_id: str = "ds000999") -> DatasetCandidateRecordV1:
    return DatasetCandidateRecordV1.make(
        source_catalog="eegdash",
        source_dataset_id=dataset_id,
        display_name="Blocked Candidate",
        license_risk="unknown_high",
        access_status="unknown",
        modalities=["EEG"],
        transition_readiness="blocked_license_or_access",
        recommended_next_action="review",
        benchmark_role_recommendation="blocked",
        provenance="synthetic fixture, not a real dataset query",
        limitations=["synthetic fixture only"],
        risks=["license and access unknown"],
    )


def make_sparse_candidate(dataset_id: str = "ds000555") -> DatasetCandidateRecordV1:
    """No task labels, no condition labels, no contact metadata -- exercises
    low-mapping-feasibility / insufficient-outreach-data scoring paths."""
    return DatasetCandidateRecordV1.make(
        source_catalog="eegdash",
        source_dataset_id=dataset_id,
        display_name="Sparse Candidate",
        license="unknown",
        license_risk="unknown_high",
        access_status="public",
        modalities=["EEG"],
        transition_readiness="blocked_missing_metadata",
        recommended_next_action="review",
        benchmark_role_recommendation="documentation_only",
        provenance="synthetic fixture, not a real dataset query",
        limitations=["synthetic fixture only"],
        risks=["no task or condition labels available"],
    )
