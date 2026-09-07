"""Local git fixture repos for integration_state tests -- real, tiny,
local-only repos built via subprocess `git`, no network, no real remote.
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
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=env)


def _commit(repo: Path, filename: str, content: str, message: str) -> str:
    (repo / filename).write_text(content, encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def state_fixture_repo(tmp_path: Path):
    """Shape:

    - `main`: root commit, then later gains one more commit independently
      (simulating main advancing after the integration branch forked).
    - `integration`: forked from main's root commit, three sequential
      "handoff" commits (round1, round2, round3=current tip), the first
      two named to simulate the mission's 3b36cb5/be277ecd-style
      progression; round2 and round3 each include a synthetic
      "Merge pull request #NNN ..." commit so PR-history verification has
      something real to find.
    - `diverged`: a fourth branch that shares only the root commit with
      `integration` -- a real, resolvable commit that is neither an
      ancestor of `integration`'s tip nor equal to it (the "stale"
      classification case).

    Returns a dict of {label: full_sha} for round1/round2/round3/diverged/
    main_root/main_tip, plus the repo Path itself, so tests don't need to
    re-derive shas.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")

    main_root = _commit(repo, "README.md", "root\n", "root commit")

    _git(repo, "checkout", "-q", "-b", "integration")
    round1 = _commit(repo, "a.py", "a=1\n", "round1: initial integration state")
    _commit(repo, "merge_pr_100.py", "pr100=True\n", "Merge pull request #100 from org/feature-a")
    round2 = _commit(repo, "b.py", "b=1\n", "round2: second handoff")
    _commit(repo, "merge_pr_200.py", "pr200=True\n", "Merge pull request #200 from org/feature-b")
    round3 = _commit(repo, "c.py", "c=1\n", "round3: current handoff (authoritative head)")

    _git(repo, "checkout", "-q", "main")
    main_tip = _commit(repo, "main_only.py", "main_advanced=True\n", "main: independent later commit")

    _git(repo, "checkout", "-q", "-b", "diverged", main_root)
    diverged = _commit(repo, "d.py", "d=1\n", "diverged: unrelated branch off the same root")

    for branch in ("main", "integration", "diverged"):
        _git(repo, "update-ref", f"refs/remotes/origin/{branch}", f"refs/heads/{branch}")

    _git(repo, "checkout", "-q", "main")

    return {
        "repo": repo, "main_root": main_root, "main_tip": main_tip,
        "round1": round1, "round2": round2, "round3": round3, "diverged": diverged,
    }
