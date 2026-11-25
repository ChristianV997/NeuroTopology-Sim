"""Build a deterministic, local Git repository for reconciliation tests.

The fixture never adds a real remote and never contacts a network. Remote-
tracking refs are local copies under ``refs/remotes/origin`` so callers can
exercise the same read-only ref names used by reconciliation.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StackedFixture:
    repo: Path
    refs: dict[str, str]
    commits: dict[str, str]


def _git(repo: Path, *args: str) -> str:
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "reconciliation-fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "reconciliation-fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_AUTHOR_DATE": "2020-01-01T00:00:00+0000",
            "GIT_COMMITTER_DATE": "2020-01-01T00:00:00+0000",
        }
    )
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout.strip()


def _commit_file(repo: Path, path: str, content: str, message: str) -> str:
    destination = repo / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _remote_ref(repo: Path, branch: str) -> str:
    return _git(repo, "rev-parse", f"refs/remotes/origin/{branch}")


def build_stacked_fixture(root: Path) -> StackedFixture:
    """Create the complete fixture beneath ``root`` and return its real refs."""
    repo = root / "stacked-reconciliation-repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "reconciliation-fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    commits: dict[str, str] = {}

    commits["base"] = _commit_file(repo, "README.md", "base\n", "base commit")
    commits["main"] = commits["base"]

    _git(repo, "checkout", "-q", "-b", "parent-feature")
    _commit_file(repo, "shared.txt", "parent\n", "parent feature")
    commits["parent-feature"] = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "-b", "stacked-child")
    _commit_file(repo, "stacked.txt", "child\n", "stacked child")
    commits["stacked-child"] = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "unrelated")
    _commit_file(repo, "unrelated.txt", "unrelated\n", "unrelated work")
    commits["unrelated"] = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "superseded")
    _commit_file(repo, "superseded.txt", "old\n", "superseded work")
    commits["superseded"] = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "replacement")
    _commit_file(repo, "replacement.txt", "new\n", "replacement work")
    commits["replacement"] = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "conflicting")
    _commit_file(repo, "shared.txt", "conflict\n", "conflicting work")
    commits["conflicting"] = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "duplicate-work")
    _commit_file(repo, "duplicate.txt", "same\n", "duplicate work")
    commits["duplicate-work"] = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "duplicate-work-twin")
    _commit_file(repo, "duplicate.txt", "same\n", "duplicate work twin")
    commits["duplicate-work-twin"] = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")

    branches = tuple(name for name in commits if name != "base")
    for branch in branches:
        _git(repo, "update-ref", f"refs/remotes/origin/{branch}", f"refs/heads/{branch}")
    refs = {branch: f"origin/{branch}" for branch in branches}
    refs["base"] = refs["main"]
    refs["missing"] = "origin/missing-reference"
    refs["fabricated"] = "f" * 40

    return StackedFixture(repo=repo, refs=refs, commits=commits)


def repeated_fixture_fingerprint(fixture: StackedFixture) -> tuple[tuple[str, str], ...]:
    """Return a stable, sorted fingerprint of the fixture's real branch tips."""
    return tuple(
        sorted(
            (name, _remote_ref(fixture.repo, name))
            for name in fixture.commits
            if name != "base"
        )
    )
