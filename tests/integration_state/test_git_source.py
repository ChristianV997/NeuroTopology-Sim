from __future__ import annotations

from tools.integration_state import git_source


def test_ref_exists_true_and_false(state_fixture_repo):
    assert git_source.ref_exists(state_fixture_repo["repo"], "origin/integration") is True
    assert git_source.ref_exists(state_fixture_repo["repo"], "origin/does-not-exist") is False


def test_resolve_commit_missing_branch_is_none(state_fixture_repo):
    assert git_source.resolve_commit(state_fixture_repo["repo"], "origin/does-not-exist") is None


def test_is_ancestor_true_false_and_none(state_fixture_repo):
    repo = state_fixture_repo["repo"]
    assert git_source.is_ancestor(repo, state_fixture_repo["round1"], state_fixture_repo["round3"]) is True
    assert git_source.is_ancestor(repo, state_fixture_repo["diverged"], state_fixture_repo["round3"]) is False
    assert git_source.is_ancestor(repo, "nope", state_fixture_repo["round3"]) is None


def test_commit_exists_in_history(state_fixture_repo):
    repo = state_fixture_repo["repo"]
    assert git_source.commit_exists_in_history(repo, state_fixture_repo["round1"], "origin/integration") is True
    assert git_source.commit_exists_in_history(repo, state_fixture_repo["diverged"], "origin/integration") is False


def test_find_merge_commit_for_pr_number(state_fixture_repo):
    repo = state_fixture_repo["repo"]
    sha = git_source.find_merge_commit_for_pr_number(repo, "origin/integration", 100)
    assert sha is not None
    assert git_source.find_merge_commit_for_pr_number(repo, "origin/integration", 999) is None


def test_branch_missing_scenario_returns_none_everywhere(state_fixture_repo):
    repo = state_fixture_repo["repo"]
    assert git_source.resolve_commit(repo, "origin/never-existed") is None
    assert git_source.find_merge_commit_for_pr_number(repo, "origin/never-existed", 100) is None
    assert git_source.commit_exists_in_history(repo, state_fixture_repo["round1"], "origin/never-existed") is None
