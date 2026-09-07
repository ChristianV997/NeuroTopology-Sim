"""Regression coverage for bounded read-only Git snapshot collection."""
from __future__ import annotations

from pathlib import Path

from tools.integration_reconciliation import git_source


class _Result:
    def __init__(self, returncode: int = 0, stdout: str = ""):
        self.returncode = returncode
        self.stdout = stdout


def test_snapshot_branch_resolves_each_ref_once(monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake_run_git(repo_path: Path, args: list[str]) -> _Result:
        del repo_path
        calls.append(tuple(args))
        if args[:3] == ["rev-parse", "--verify", "--quiet"]:
            return _Result(stdout="commit\n")
        if args[:1] == ["rev-parse"]:
            return _Result(stdout="commit\n")
        if args[:1] == ["merge-base"] and "--is-ancestor" not in args:
            return _Result(stdout="base\n")
        if args[:2] == ["merge-base", "--is-ancestor"]:
            return _Result()
        if args[:1] == ["rev-list"]:
            return _Result(stdout="1\n")
        if args[:1] == ["diff"]:
            return _Result(stdout="changed.py\n")
        raise AssertionError(args)

    monkeypatch.setattr(git_source, "_run_git", fake_run_git)
    snapshot = git_source.snapshot_branch(Path("fixture"), "origin/feature", "origin/main")

    assert snapshot.exists is True
    assert snapshot.commit_sha == "commit"
    assert snapshot.merge_base_with_target == "base"
    assert snapshot.commits_ahead_of_merge_base == 1
    assert snapshot.changed_files == ("changed.py",)
    assert len(calls) == 6
    assert calls.count(("rev-parse", "--verify", "--quiet", "origin/feature")) == 1
    assert calls.count(("rev-parse", "--verify", "--quiet", "origin/main")) == 1
