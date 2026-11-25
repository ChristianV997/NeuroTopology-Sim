from tools.release_manifest import git_source


def test_ref_exists_for_real_commit(git_repo):
    head = git_source.resolve_commit(git_repo, "main")
    assert head is not None
    assert git_source.ref_exists(git_repo, head)


def test_fabricated_hash_sharing_real_prefix_is_not_verified(git_repo):
    """The core bug this package must not repeat: a well-formed 40-char
    hex string that shares a real commit's 8-char prefix but does not
    itself exist must resolve to False/None, never be accepted as real."""
    real = git_source.resolve_commit(git_repo, "main")
    fabricated = real[:8] + "f" * 32
    assert len(fabricated) == 40
    assert git_source.ref_exists(git_repo, fabricated) is False
    assert git_source.resolve_commit(git_repo, fabricated) is None


def test_resolve_commit_for_missing_ref_returns_none(git_repo):
    assert git_source.resolve_commit(git_repo, "does-not-exist") is None


def test_is_ancestor_true_for_earlier_commit_on_same_line(git_repo):
    result = git_source._run(git_repo, ["log", "--format=%H"])
    shas = result.stdout.splitlines()
    assert git_source.is_ancestor(git_repo, shas[-1], shas[0]) is True


def test_is_ancestor_none_when_ref_unresolvable(git_repo):
    head = git_source.resolve_commit(git_repo, "main")
    assert git_source.is_ancestor(git_repo, "nonexistent", head) is None


def test_changed_files_between_branches(git_repo_with_integration_branch):
    repo = git_repo_with_integration_branch
    files = git_source.changed_files(repo, "main", "integration")
    assert files == ("d.txt",)


def test_changed_files_none_when_ref_missing(git_repo):
    assert git_source.changed_files(git_repo, "main", "nonexistent") is None


def test_find_merge_commit_for_pr_number_matches_subject(git_repo):
    (git_repo / "e.txt").write_text("5")
    git_source._run(git_repo, ["add", "e.txt"])
    git_source._run(git_repo, ["commit", "-q", "-m", "Merge pull request #42 from feature"])
    sha = git_source.find_merge_commit_for_pr_number(git_repo, "main", 42)
    assert sha is not None


def test_find_merge_commit_for_pr_number_no_match(git_repo):
    assert git_source.find_merge_commit_for_pr_number(git_repo, "main", 9999) is None
