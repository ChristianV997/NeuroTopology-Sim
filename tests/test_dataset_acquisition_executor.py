"""dataset_acquisition.executor: dry-run-first execution, scan/verify local,
and the fail-closed gates around execute_download. No network calls in
this test suite -- v1 only ever touches the local filesystem, and only for
scan_existing_local/verify_existing_local.
"""
from __future__ import annotations

import pytest

from dataset_acquisition.executor import ExecutorError, execute_acquisition_plan
from dataset_acquisition.planner import make_acquisition_plan
from dataset_importers.candidate_record import DatasetCandidateRecordV1


def _candidate(**overrides) -> DatasetCandidateRecordV1:
    kwargs = dict(
        source_catalog="synthetic_fixture",
        source_dataset_id=overrides.pop("source_dataset_id", "ds-exec-1"),
        display_name="Executor fixture dataset",
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


def _local_bids_root(tmp_path_factory, name: str) -> str:
    """Creates a tiny local BIDS-like fixture under outputs/ (the only
    allowed, gitignored target_root prefix) and returns its repo-relative
    path. Cleaned up by the caller test."""
    import shutil
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    root = repo_root / "outputs" / "datasets" / name
    if root.exists():
        shutil.rmtree(root)
    (root / "sub-01" / "eeg").mkdir(parents=True, exist_ok=True)
    (root / "dataset_description.json").write_text('{"Name": "Executor Test Fixture"}', encoding="utf-8")
    (root / "participants.tsv").write_text("participant_id\nsub-01\n", encoding="utf-8")
    (root / "sub-01" / "eeg" / "sub-01_task-rest_events.tsv").write_text(
        "onset\tduration\ttrial_type\n0\t1\trest\n", encoding="utf-8"
    )
    return f"outputs/datasets/{name}"


@pytest.fixture()
def local_bids_root(request):
    import shutil
    from pathlib import Path

    name = f"exec-fixture-{request.node.name}"
    rel = _local_bids_root(None, name)
    yield rel
    repo_root = Path(__file__).resolve().parents[1]
    shutil.rmtree(repo_root / rel, ignore_errors=True)


def test_dry_run_produces_planned_only_manifest_and_no_files():
    candidate = _candidate(source_dataset_id="ds-dryrun")
    plan = make_acquisition_plan(candidate, target_root="outputs/datasets/dryrun-nonexistent", requested_action="metadata_only")
    manifest = execute_acquisition_plan(plan, execute=False)
    assert manifest.execution_status == "planned_only"
    assert manifest.acquired_paths == []
    assert manifest.validate() == []

    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    assert not (repo_root / "outputs" / "datasets" / "dryrun-nonexistent").exists()


def test_execute_without_flags_fails_for_execute_download():
    candidate = _candidate(source_dataset_id="ds-noflags", metadata={"estimated_size_bytes": 1000})
    plan = make_acquisition_plan(
        candidate,
        target_root="outputs/datasets/noflags",
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=500_000_000,
        allow_network=True,
        allow_raw_data=True,
        explicit_execute_confirmed=True,
    )
    # Plan itself is clean/unblocked, but the executor's own flags disagree.
    with pytest.raises(ExecutorError):
        execute_acquisition_plan(plan, execute=True, allow_network=False, allow_raw_data=False)


def test_execute_with_only_network_fails():
    candidate = _candidate(source_dataset_id="ds-onlynet", metadata={"estimated_size_bytes": 1000})
    plan = make_acquisition_plan(
        candidate,
        target_root="outputs/datasets/onlynet",
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=500_000_000,
        allow_network=True,
        allow_raw_data=True,
        explicit_execute_confirmed=True,
    )
    with pytest.raises(ExecutorError, match="allow_raw_data"):
        execute_acquisition_plan(plan, execute=True, allow_network=True, allow_raw_data=False)


def test_execute_with_only_raw_data_fails():
    candidate = _candidate(source_dataset_id="ds-onlyraw", metadata={"estimated_size_bytes": 1000})
    plan = make_acquisition_plan(
        candidate,
        target_root="outputs/datasets/onlyraw",
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=500_000_000,
        allow_network=True,
        allow_raw_data=True,
        explicit_execute_confirmed=True,
    )
    with pytest.raises(ExecutorError, match="allow_network"):
        execute_acquisition_plan(plan, execute=True, allow_network=False, allow_raw_data=True)


def test_blocked_plan_produces_blocked_manifest_not_exception():
    candidate = _candidate(source_dataset_id="ds-blocked", access_status="restricted", benchmark_role_recommendation="blocked")
    plan = make_acquisition_plan(
        candidate,
        target_root="outputs/datasets/blockedexec",
        requested_action="execute_download",
        disk_limit_bytes=500_000_000,
        allow_network=True,
        allow_raw_data=True,
    )
    manifest = execute_acquisition_plan(plan, execute=True, allow_network=True, allow_raw_data=True)
    assert manifest.execution_status == "blocked"
    assert manifest.errors


def test_scan_existing_local_works_on_fixture(local_bids_root):
    candidate = _candidate(source_dataset_id="ds-scan")
    plan = make_acquisition_plan(candidate, target_root=local_bids_root, requested_action="scan_existing_local")
    manifest = execute_acquisition_plan(plan, execute=True)
    assert manifest.execution_status == "acquired"
    assert manifest.acquired_file_count == 3
    assert manifest.acquired_size_bytes > 0
    assert manifest.checksums
    assert manifest.validate() == []


def test_verify_existing_local_works_on_fixture(local_bids_root):
    candidate = _candidate(source_dataset_id="ds-verify")
    plan = make_acquisition_plan(candidate, target_root=local_bids_root, requested_action="verify_existing_local")
    manifest = execute_acquisition_plan(plan, execute=True)
    assert manifest.execution_status == "verified_existing"
    assert manifest.acquired_file_count == 3


def test_scan_existing_local_fails_on_missing_root():
    candidate = _candidate(source_dataset_id="ds-missing-root")
    plan = make_acquisition_plan(candidate, target_root="outputs/datasets/does-not-exist-at-all", requested_action="scan_existing_local")
    manifest = execute_acquisition_plan(plan, execute=True)
    assert manifest.execution_status == "failed"
    assert manifest.errors


def test_checksums_deterministic_across_runs(local_bids_root):
    candidate = _candidate(source_dataset_id="ds-checksum")
    plan = make_acquisition_plan(candidate, target_root=local_bids_root, requested_action="scan_existing_local")
    manifest1 = execute_acquisition_plan(plan, execute=True)
    manifest2 = execute_acquisition_plan(plan, execute=True)
    assert manifest1.checksums == manifest2.checksums


def test_no_network_calls_are_ever_made_by_executor_source():
    """Static guard: the executor module's own source must never reference
    a network-fetch API, even optionally."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "dataset_acquisition" / "executor.py").read_text(encoding="utf-8")
    for banned in ("requests.get(", "urllib.request", "http.client", ".get_data(", ".download("):
        assert banned not in source
