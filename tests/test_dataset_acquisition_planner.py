"""dataset_acquisition.planner: make_acquisition_plan / plan_from_candidate_file.
Synthetic fixtures only -- never downloads data.
"""
from __future__ import annotations

import json

import pytest

from dataset_acquisition.planner import (
    PlannerError,
    choose_default_acquisition_mode,
    make_acquisition_plan,
    plan_from_candidate_file,
)
from dataset_acquisition.store import TargetRootError
from dataset_importers.candidate_record import DatasetCandidateRecordV1


def _candidate(**overrides) -> DatasetCandidateRecordV1:
    kwargs = dict(
        source_catalog="synthetic_fixture",
        source_dataset_id=overrides.pop("source_dataset_id", "ds-plan-1"),
        display_name="Planner fixture dataset",
        license="CC0",
        license_risk="permissive_low",
        access_status="public",
        download_required="true",
        modalities=["EEG"],
        condition_labels=["rest", "task"],
        subject_count=10,
        transition_readiness="candidate_transition_possible",
        benchmark_role_recommendation="development_candidate",
        risks=["r"],
        limitations=["l"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return DatasetCandidateRecordV1.make(**kwargs)


def test_choose_default_acquisition_mode():
    assert choose_default_acquisition_mode(_candidate(source_catalog="eegdash", source_dataset_id="d1")) == "eegdash_metadata_query"
    assert choose_default_acquisition_mode(_candidate(source_catalog="moabb", source_dataset_id="d2")) == "moabb_planned_fetch"
    assert choose_default_acquisition_mode(_candidate(source_catalog="synthetic_fixture", source_dataset_id="d3")) == "fixture_only"


def test_creates_metadata_only_plan_from_candidate():
    candidate = _candidate()
    plan = make_acquisition_plan(candidate, target_root="outputs/datasets/plan1", requested_action="metadata_only")
    assert plan.validate() == []
    assert plan.requested_action == "metadata_only"
    assert plan.dry_run is True
    assert plan.blocked_reasons == []
    assert plan.candidate_id == candidate.candidate_id


def test_creates_plan_download_plan_without_executing():
    candidate = _candidate(source_dataset_id="ds-plan-2")
    plan = make_acquisition_plan(
        candidate, target_root="outputs/datasets/plan2", requested_action="plan_download", disk_limit_bytes=500_000_000
    )
    assert plan.validate() == []
    assert plan.dry_run is True
    assert plan.disk_limit_bytes == 500_000_000


def test_creates_blocked_plan_for_restricted_candidate():
    candidate = _candidate(source_dataset_id="ds-restricted", access_status="restricted", benchmark_role_recommendation="blocked")
    plan = make_acquisition_plan(
        candidate,
        target_root="outputs/datasets/restricted",
        requested_action="execute_download",
        disk_limit_bytes=500_000_000,
        allow_network=True,
        allow_raw_data=True,
    )
    assert plan.validate() == []
    assert plan.blocked_reasons
    assert any("access_status" in r or "blocked" in r for r in plan.blocked_reasons)
    assert plan.dry_run is True


def test_creates_blocked_plan_for_unknown_license_if_execute_requested():
    candidate = _candidate(source_dataset_id="ds-unknown-license", license="unknown", license_risk="unknown_high")
    plan = make_acquisition_plan(
        candidate,
        target_root="outputs/datasets/unknownlic",
        requested_action="execute_download",
        disk_limit_bytes=500_000_000,
        allow_network=True,
        allow_raw_data=True,
        explicit_execute_confirmed=True,
    )
    assert plan.validate() == []
    assert any("license_risk" in r for r in plan.blocked_reasons)
    assert plan.dry_run is True


def test_does_not_invent_size():
    candidate = _candidate(source_dataset_id="ds-no-size")
    assert "estimated_size_bytes" not in candidate.metadata
    plan = make_acquisition_plan(candidate, target_root="outputs/datasets/nosize", requested_action="metadata_only")
    assert plan.estimated_size_bytes is None


def test_uses_explicit_size_when_supplied_in_candidate_metadata():
    candidate = _candidate(source_dataset_id="ds-with-size", metadata={"estimated_size_bytes": 12345})
    plan = make_acquisition_plan(candidate, target_root="outputs/datasets/withsize", requested_action="metadata_only")
    assert plan.estimated_size_bytes == 12345


def test_does_not_mark_evidence():
    candidate = _candidate(source_dataset_id="ds-not-evidence")
    plan = make_acquisition_plan(candidate, target_root="outputs/datasets/notevidence", requested_action="metadata_only")
    assert "evidence" not in plan.metadata
    assert not plan.metadata.get("validation_ready")
    assert not plan.metadata.get("final_claim_confirmation")


def test_invalid_candidate_raises_planner_error():
    candidate = _candidate(source_dataset_id="ds-invalid", provenance="")  # fails candidate's own validation
    with pytest.raises(PlannerError):
        make_acquisition_plan(candidate, target_root="outputs/datasets/invalid", requested_action="metadata_only")


def test_unsafe_target_root_raises_before_anything_else():
    candidate = _candidate(source_dataset_id="ds-unsafe-root")
    with pytest.raises(TargetRootError):
        make_acquisition_plan(candidate, target_root="/etc/evil", requested_action="metadata_only")


def test_plan_from_candidate_file(tmp_path):
    candidate = _candidate(source_dataset_id="ds-from-file")
    export = {"schema": "NeuroTopologySim.DatasetCandidateExport.v1", "candidates": [candidate.to_dict()]}
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(export), encoding="utf-8")

    plan = plan_from_candidate_file(path, candidate.candidate_id, target_root="outputs/datasets/fromfile")
    assert plan.candidate_id == candidate.candidate_id
    assert plan.validate() == []


def test_plan_from_candidate_file_missing_id_raises(tmp_path):
    export = {"schema": "NeuroTopologySim.DatasetCandidateExport.v1", "candidates": []}
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(export), encoding="utf-8")
    with pytest.raises(PlannerError):
        plan_from_candidate_file(path, "does-not-exist", target_root="outputs/datasets/x")


def test_execute_download_with_all_flags_and_local_mode_is_unblocked():
    candidate = _candidate(source_dataset_id="ds-clean-exec", metadata={"estimated_size_bytes": 1000})
    plan = make_acquisition_plan(
        candidate,
        target_root="outputs/datasets/cleanexec",
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=500_000_000,
        allow_network=True,
        allow_raw_data=True,
        explicit_execute_confirmed=True,
    )
    assert plan.validate() == []
    assert plan.blocked_reasons == []
    assert plan.dry_run is False
