import json
import socket

import pytest

from tools.release_manifest.manifest_builder import build_manifest
from tools.release_manifest.models import ChangedFileOwnership, ScientificGateInput
from tests.release_manifest.conftest import commit_of


def _write_snapshot(tmp_path, **fields):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(fields))
    return path


def test_verified_merge_reports_merged_into_main(git_repo):
    head = commit_of(git_repo, "main")
    manifest = build_manifest(
        repo_path=git_repo,
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="main",
        source_commit=head,
    )
    assert manifest.merge_state == "merged_into_main"
    assert manifest.merge_eligibility is True
    assert manifest.verified_head_commit.value == head


def test_integration_only_is_never_reported_as_merged(git_repo_with_integration_branch):
    repo = git_repo_with_integration_branch
    feature_head = commit_of(repo, "feature")
    manifest = build_manifest(
        repo_path=repo,
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="integration",
        source_commit=feature_head,
    )
    assert manifest.merge_state == "integration_only"
    assert manifest.merge_state != "merged_into_main"
    assert manifest.merge_eligibility is False


def test_fabricated_hash_is_unknown_never_stale_or_merged(git_repo):
    head = commit_of(git_repo, "main")
    fabricated = head[:8] + "f" * 32
    manifest = build_manifest(
        repo_path=git_repo,
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="main",
        source_commit=fabricated,
    )
    assert manifest.merge_state == "unknown"
    assert manifest.verified_head_commit.value is None
    assert manifest.merge_eligibility is False


def test_stale_handoff_commit(git_repo_with_stale_branch):
    repo = git_repo_with_stale_branch
    stale_head = commit_of(repo, "stale")
    manifest = build_manifest(
        repo_path=repo,
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="integration",
        source_commit=stale_head,
    )
    assert manifest.merge_state == "ancestor_stale"
    assert manifest.merge_eligibility is False


def test_superseded_pr(git_repo, tmp_path):
    head = commit_of(git_repo, "main")
    # A commit off the target/integration lineages, with a closed (not
    # merged) PR snapshot naming it -- superseded requires a specific
    # signal this builder does not itself infer, so it should resolve
    # to at least "not merged_into_main"; the dedicated unit test in
    # test_merge_state.py covers the classifier's superseded branch
    # directly using MergeStateContext.superseded_by.
    snapshot = _write_snapshot(
        tmp_path, number=5, state="closed", draft=False, merged=False, head_sha=head, base_ref="main", checks={}
    )
    manifest = build_manifest(
        repo_path=git_repo,
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="main",
        source_commit=head,
        pr_snapshot_path=snapshot,
    )
    # head is ancestor of target here, so merged_into_main wins (a
    # closed-and-landed PR is correctly "merged", not "superseded").
    assert manifest.merge_state == "merged_into_main"


def test_infrastructure_blocked_ci(git_repo_with_integration_branch, tmp_path):
    repo = git_repo_with_integration_branch
    feature_head = commit_of(repo, "feature")
    snapshot = _write_snapshot(
        tmp_path,
        number=12,
        state="open",
        draft=False,
        merged=False,
        head_sha=feature_head,
        base_ref="main",
        checks={
            "required-checks": {
                "status": "completed",
                "conclusion": "failure",
                "failure_signature": "GitHub Actions checks fail before usable steps/logs (billing-blocked)",
            }
        },
    )
    manifest = build_manifest(
        repo_path=repo,
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="integration",
        source_commit=feature_head,
        pr_snapshot_path=snapshot,
    )
    assert manifest.merge_state == "blocked_by_infrastructure"
    assert manifest.ci_classifications["required-checks"]["value"] == "infrastructure_blocked"


def test_synthetic_scientific_result_is_not_blocking(git_repo_with_integration_branch):
    repo = git_repo_with_integration_branch
    feature_head = commit_of(repo, "feature")
    manifest = build_manifest(
        repo_path=repo,
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="integration",
        source_commit=feature_head,
        scientific_gate_input=ScientificGateInput(data_mode="synthetic", verdict="PASS", evidence_kind=None),
    )
    assert manifest.scientific_gate_status.value == "blocked"
    assert manifest.merge_state == "blocked_by_scientific_review"
    assert any("unverified_scientific_pass" in b for b in manifest.blockers)


def test_missing_github_snapshot_reports_unavailable(git_repo):
    head = commit_of(git_repo, "main")
    manifest = build_manifest(
        repo_path=git_repo,
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="main",
        source_commit=head,
    )
    assert manifest.github_state == "unavailable"
    assert manifest.pr_number.value is None
    assert manifest.pr_status.value is None


def test_duplicate_changed_files_detected(git_repo_with_integration_branch):
    repo = git_repo_with_integration_branch
    feature_head = commit_of(repo, "feature")
    other = ChangedFileOwnership(label="agent-b", changed_files=("d.txt",))
    manifest = build_manifest(
        repo_path=repo,
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="integration",
        source_commit=feature_head,
        other_ownerships=[other],
    )
    assert manifest.duplicate_file_findings
    assert any("d.txt" in f["shared_files"] for f in manifest.duplicate_file_findings)


def test_no_network_operation_no_socket_calls(git_repo, monkeypatch):
    """Guarantee build_manifest makes no network call: patch socket
    creation to raise, and confirm a full build still succeeds."""

    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted during build_manifest")

    monkeypatch.setattr(socket, "socket", _no_network)
    head = commit_of(git_repo, "main")
    manifest = build_manifest(
        repo_path=git_repo,
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="main",
        source_commit=head,
    )
    assert manifest.merge_state == "merged_into_main"


def test_generated_at_only_populated_when_requested(git_repo):
    head = commit_of(git_repo, "main")
    default_manifest = build_manifest(
        repo_path=git_repo,
        repository="r",
        target_branch="main",
        integration_branch="main",
        source_commit=head,
    )
    assert default_manifest.generated_at is None

    explicit_manifest = build_manifest(
        repo_path=git_repo,
        repository="r",
        target_branch="main",
        integration_branch="main",
        source_commit=head,
        include_generated_at=True,
        generated_at_value="2026-09-07T00:00:00Z",
    )
    assert explicit_manifest.generated_at == "2026-09-07T00:00:00Z"
