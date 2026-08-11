"""dataset_acquisition.executor.run_bids_handoff: local verified/acquired
manifests can call adapters.mne_bids's metadata scan; output stays
conservative and never emits a TransitionRecordV1.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dataset_acquisition.executor import ExecutorError, execute_acquisition_plan, run_bids_handoff
from dataset_acquisition.planner import make_acquisition_plan
from dataset_importers.candidate_record import DatasetCandidateRecordV1

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _candidate(**overrides) -> DatasetCandidateRecordV1:
    kwargs = dict(
        source_catalog="synthetic_fixture",
        source_dataset_id=overrides.pop("source_dataset_id", "ds-handoff-1"),
        display_name="Handoff fixture dataset",
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


@pytest.fixture()
def local_bids_root(request):
    name = f"handoff-fixture-{request.node.name}"
    root = _REPO_ROOT / "outputs" / "datasets" / name
    if root.exists():
        shutil.rmtree(root)
    (root / "sub-01" / "eeg").mkdir(parents=True, exist_ok=True)
    (root / "dataset_description.json").write_text('{"Name": "Handoff Test Fixture"}', encoding="utf-8")
    (root / "participants.tsv").write_text("participant_id\nsub-01\n", encoding="utf-8")
    (root / "sub-01" / "eeg" / "sub-01_task-rest_events.tsv").write_text(
        "onset\tduration\ttrial_type\n0\t1\trest\n", encoding="utf-8"
    )
    yield f"outputs/datasets/{name}"
    shutil.rmtree(root, ignore_errors=True)


def test_local_verified_manifest_can_call_bids_metadata_scan(local_bids_root):
    candidate = _candidate(source_dataset_id="ds-handoff-verify")
    plan = make_acquisition_plan(candidate, target_root=local_bids_root, requested_action="verify_existing_local")
    manifest = execute_acquisition_plan(plan, execute=True)
    assert manifest.execution_status == "verified_existing"

    result = run_bids_handoff(manifest, target_root=local_bids_root)
    assert result["dataset_record"]["dataset_id"]
    assert result["bids_metadata_summary"]["n_subjects"] == 1


def test_local_acquired_manifest_can_call_bids_metadata_scan(local_bids_root):
    candidate = _candidate(source_dataset_id="ds-handoff-scan")
    plan = make_acquisition_plan(candidate, target_root=local_bids_root, requested_action="scan_existing_local")
    manifest = execute_acquisition_plan(plan, execute=True)
    assert manifest.execution_status == "acquired"

    result = run_bids_handoff(manifest, target_root=local_bids_root)
    assert result["dataset_record"]["dataset_id"]


def test_output_dataset_record_remains_conservative(local_bids_root):
    candidate = _candidate(source_dataset_id="ds-handoff-conservative")
    plan = make_acquisition_plan(candidate, target_root=local_bids_root, requested_action="verify_existing_local")
    manifest = execute_acquisition_plan(plan, execute=True)
    result = run_bids_handoff(manifest, target_root=local_bids_root)

    ds = result["dataset_record"]
    assert ds["current_role"] == "exploration"
    assert ds["contamination_status"] == "unseen"
    assert "transition_export" not in ds["allowed_uses"]
    assert ds["evidence_level_ceiling"] == "L0_computational_artifact"


def test_output_artifact_records_are_external_and_conservative(local_bids_root):
    candidate = _candidate(source_dataset_id="ds-handoff-artifacts")
    plan = make_acquisition_plan(candidate, target_root=local_bids_root, requested_action="scan_existing_local")
    manifest = execute_acquisition_plan(plan, execute=True)
    result = run_bids_handoff(manifest, target_root=local_bids_root)

    assert result["artifact_records"]
    for art in result["artifact_records"]:
        assert art["current_role"] == "exploration"
        assert "transition_export" not in art["allowed_uses"]


def test_no_transition_record_emitted_without_derived_feature_mapping(local_bids_root):
    """The handoff result must never contain anything TransitionRecordV1-
    shaped -- no derived-feature mapping was ever supplied at this stage."""
    candidate = _candidate(source_dataset_id="ds-handoff-notransition")
    plan = make_acquisition_plan(candidate, target_root=local_bids_root, requested_action="verify_existing_local")
    manifest = execute_acquisition_plan(plan, execute=True)
    result = run_bids_handoff(manifest, target_root=local_bids_root)

    assert set(result.keys()) == {"bids_metadata_summary", "dataset_record", "artifact_records"}
    for art in result["artifact_records"]:
        assert art.get("artifact_kind") != "transition_record"


def test_handoff_rejected_for_planned_only_manifest():
    candidate = _candidate(source_dataset_id="ds-handoff-blocked")
    plan = make_acquisition_plan(candidate, target_root="outputs/datasets/handoff-notreal", requested_action="metadata_only")
    manifest = execute_acquisition_plan(plan, execute=False)
    assert manifest.execution_status == "planned_only"
    with pytest.raises(ExecutorError):
        run_bids_handoff(manifest, target_root=plan.target_root)


def test_handoff_rejected_for_failed_manifest():
    candidate = _candidate(source_dataset_id="ds-handoff-failed")
    plan = make_acquisition_plan(
        candidate, target_root="outputs/datasets/does-not-exist-handoff", requested_action="scan_existing_local"
    )
    manifest = execute_acquisition_plan(plan, execute=True)
    assert manifest.execution_status == "failed"
    with pytest.raises(ExecutorError):
        run_bids_handoff(manifest, target_root=plan.target_root)
