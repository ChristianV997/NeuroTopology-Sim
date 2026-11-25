"""git_source: exercised entirely against local git fixture repos (no
network, no real remote)."""
from __future__ import annotations

from tools.integration_reconciliation import git_source


def test_ref_exists_true_for_real_branch(git_fixture_repo):
    assert git_source.ref_exists(git_fixture_repo, "origin/feature-a") is True


def test_ref_exists_false_for_missing_branch(git_fixture_repo):
    assert git_source.ref_exists(git_fixture_repo, "origin/does-not-exist") is False


def test_resolve_commit_returns_none_for_missing_ref(git_fixture_repo):
    assert git_source.resolve_commit(git_fixture_repo, "origin/nope") is None


def test_resolve_commit_returns_a_sha_for_real_ref(git_fixture_repo):
    sha = git_source.resolve_commit(git_fixture_repo, "origin/feature-a")
    assert sha is not None
    assert len(sha) == 40


def test_merge_base_returns_none_when_a_ref_is_missing(git_fixture_repo):
    assert git_source.merge_base(git_fixture_repo, "origin/main", "origin/nope") is None


def test_merge_base_is_shared_ancestor(git_fixture_repo):
    base_a = git_source.merge_base(git_fixture_repo, "origin/main", "origin/feature-a")
    base_b = git_source.merge_base(git_fixture_repo, "origin/main", "origin/feature-b")
    feature_a_tip = git_source.resolve_commit(git_fixture_repo, "origin/feature-a")
    assert base_a is not None
    # feature-a and feature-b both branched directly off the same root
    # commit, before main gained the later already-merged/with-artifact
    # history -- their merge-base with main must be that shared root, not
    # either branch's own tip.
    assert base_a == base_b
    assert base_a != feature_a_tip


def test_is_ancestor_true_for_already_merged_branch(git_fixture_repo):
    assert git_source.is_ancestor(git_fixture_repo, "origin/already-merged", "origin/main") is True


def test_is_ancestor_false_for_unmerged_branch(git_fixture_repo):
    assert git_source.is_ancestor(git_fixture_repo, "origin/feature-a", "origin/main") is False


def test_is_ancestor_none_for_missing_ref(git_fixture_repo):
    assert git_source.is_ancestor(git_fixture_repo, "origin/nope", "origin/main") is None


def test_commits_ahead_is_one_for_a_single_commit_branch(git_fixture_repo):
    assert git_source.commits_ahead(git_fixture_repo, "origin/main", "origin/feature-a") == 1


def test_commits_ahead_none_for_missing_branch(git_fixture_repo):
    assert git_source.commits_ahead(git_fixture_repo, "origin/main", "origin/nope") is None


def test_changed_files_lists_the_touched_paths(git_fixture_repo):
    files = git_source.changed_files(git_fixture_repo, "origin/main", "origin/feature-a")
    assert files == ("shared/a.py",)


def test_changed_files_overlap_between_feature_a_and_feature_b(git_fixture_repo):
    files_a = set(git_source.changed_files(git_fixture_repo, "origin/main", "origin/feature-a"))
    files_b = set(git_source.changed_files(git_fixture_repo, "origin/main", "origin/feature-b"))
    assert files_a & files_b == {"shared/a.py"}


def test_changed_files_none_for_missing_branch(git_fixture_repo):
    assert git_source.changed_files(git_fixture_repo, "origin/main", "origin/nope") is None


def test_snapshot_branch_absent(git_fixture_repo):
    snap = git_source.snapshot_branch(git_fixture_repo, "origin/nope", "origin/main")
    assert snap.exists is False
    assert snap.commit_sha is None
    assert snap.changed_files is None


def test_snapshot_branch_present_and_unmerged(git_fixture_repo):
    snap = git_source.snapshot_branch(git_fixture_repo, "origin/feature-a", "origin/main")
    assert snap.exists is True
    assert snap.commit_sha is not None
    assert snap.is_ancestor_of_target is False
    assert snap.commits_ahead_of_merge_base == 1
    assert snap.changed_files == ("shared/a.py",)


def test_snapshot_branch_present_and_already_merged(git_fixture_repo):
    snap = git_source.snapshot_branch(git_fixture_repo, "origin/already-merged", "origin/main")
    assert snap.exists is True
    assert snap.is_ancestor_of_target is True
