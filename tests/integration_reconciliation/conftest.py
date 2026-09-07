"""Local git fixture repositories for integration_reconciliation tests.

Everything here builds real, tiny, local-only git repos under `tmp_path`
via subprocess `git` calls (init/commit/branch/checkout) -- no network,
no remote, no origin. This is what lets git_source/reconcile tests run
with zero network access.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
    })
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True, env=env,
    )
    return result


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("root\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "root commit")


@pytest.fixture
def git_fixture_repo(tmp_path: Path) -> Path:
    """A repo shaped like the real reconciliation scenario:

    - `main`: the base branch.
    - `origin/feature-a` (simulated via a real local branch, since this
      tool only ever reads refs by name -- a plain local branch and a
      remote-tracking branch are indistinguishable to `git rev-parse`):
      one commit ahead of `main`, touching `shared/a.py`.
    - `origin/feature-b`: one commit ahead of `main`, touching
      `shared/a.py` (the same file, for overlap testing) and
      `feature_b_only.py`.
    - `origin/already-merged`: fast-forwarded into `main` (so
      is_ancestor_of_target is True for it).
    - `origin/with-artifact`: adds a file that looks like a generated
      artifact (`artifacts/RunRecord.json`).
    """
    repo = tmp_path / "repo"
    _init_repo(repo)

    # feature-a
    _git(repo, "checkout", "-q", "-b", "feature-a")
    (repo / "shared").mkdir(exist_ok=True)
    (repo / "shared" / "a.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", "shared/a.py")
    _git(repo, "commit", "-q", "-m", "feature-a: add shared/a.py")

    # stacked-on-feature-a: a dependent PR whose own diff is separate from
    # feature-a, while its raw diff against main intentionally includes both.
    _git(repo, "checkout", "-q", "-b", "stacked-on-feature-a")
    (repo / "stacked_only.py").write_text("stacked = True\n", encoding="utf-8")
    _git(repo, "add", "stacked_only.py")
    _git(repo, "commit", "-q", "-m", "stacked-on-feature-a: add stacked_only.py")
    _git(repo, "checkout", "-q", "main")

    # feature-b (also touches shared/a.py, for overlap testing)
    _git(repo, "checkout", "-q", "-b", "feature-b")
    (repo / "shared").mkdir(exist_ok=True)
    (repo / "shared" / "a.py").write_text("value = 2\n", encoding="utf-8")
    _git(repo, "add", "shared/a.py")
    (repo / "feature_b_only.py").write_text("only_b = True\n", encoding="utf-8")
    _git(repo, "add", "feature_b_only.py")
    _git(repo, "commit", "-q", "-m", "feature-b: add shared/a.py and feature_b_only.py")
    _git(repo, "checkout", "-q", "main")

    # already-merged: a branch whose single commit is then merged into main
    _git(repo, "checkout", "-q", "-b", "already-merged")
    (repo / "merged_file.py").write_text("merged = True\n", encoding="utf-8")
    _git(repo, "add", "merged_file.py")
    _git(repo, "commit", "-q", "-m", "already-merged: add merged_file.py")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge already-merged", "already-merged")

    # with-artifact: looks like a generated RunRecord.json got committed
    _git(repo, "checkout", "-q", "-b", "with-artifact")
    (repo / "artifacts").mkdir(exist_ok=True)
    (repo / "artifacts" / "RunRecord.json").write_text('{"run_id": "x"}\n', encoding="utf-8")
    _git(repo, "add", "artifacts/RunRecord.json")
    _git(repo, "commit", "-q", "-m", "with-artifact: accidentally commit a RunRecord.json")
    _git(repo, "checkout", "-q", "main")

    # Simulate "origin/*" remote-tracking refs the tool actually looks up,
    # without a real remote: a plain ref copy under refs/remotes/origin/.
    for branch in (
        "main", "feature-a", "stacked-on-feature-a", "feature-b",
        "already-merged", "with-artifact",
    ):
        _git(repo, "update-ref", f"refs/remotes/origin/{branch}", f"refs/heads/{branch}")

    return repo
