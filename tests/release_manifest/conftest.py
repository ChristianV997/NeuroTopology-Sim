"""Local-only git fixture repo builder for tools.release_manifest tests.
No network call anywhere: every repo here is created via subprocess
``git`` against a throwaway temp directory."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def _commit(repo: Path, filename: str, content: str, message: str) -> str:
    (repo / filename).write_text(content)
    _git(repo, "add", filename)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A repo with linear history on ``main``: c1 -> c2 -> c3 (HEAD)."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "checkout", "-q", "-b", "main")
    _commit(repo, "a.txt", "1", "c1")
    _commit(repo, "b.txt", "2", "c2")
    _commit(repo, "c.txt", "3", "c3")
    return repo


@pytest.fixture
def git_repo_with_integration_branch(git_repo: Path) -> Path:
    """Adds an ``integration`` branch one commit ahead of ``main``, and a
    ``feature`` branch containing that same extra commit (so feature is an
    ancestor of integration but NOT of main -- the integration-only case)."""
    _git(git_repo, "checkout", "-q", "-b", "integration", "main")
    _commit(git_repo, "d.txt", "4", "c4-integration")
    _git(git_repo, "checkout", "-q", "-b", "feature", "integration")
    _git(git_repo, "checkout", "-q", "main")
    return git_repo


@pytest.fixture
def git_repo_with_stale_branch(git_repo: Path) -> Path:
    """Adds a ``stale`` branch that diverges from main's second commit --
    a real object, but off the ``main`` and ``integration`` lineages."""
    _git(git_repo, "branch", "stale-base", "main")
    _git(git_repo, "reset", "-q", "--hard", "HEAD~2")
    _git(git_repo, "checkout", "-q", "-b", "stale")
    _commit(git_repo, "z.txt", "diverge", "c-stale")
    _git(git_repo, "checkout", "-q", "main")
    _git(git_repo, "reset", "-q", "--hard", "stale-base")
    _git(git_repo, "checkout", "-q", "-b", "integration", "main")
    return git_repo


def commit_of(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", ref).stdout.strip()
