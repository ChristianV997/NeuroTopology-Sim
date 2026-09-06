"""Read-only git plumbing. Every function here shells out to a git
subcommand that only reads repository state -- no `checkout`, `merge`,
`rebase`, `push`, `branch -d`, or any other mutating verb appears in this
module. Tests exercise this against small local git fixture repositories
(tests/integration_reconciliation/fixtures), so nothing here requires
network access.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_READ_ONLY_TIMEOUT_S = 30


class GitCommandError(RuntimeError):
    """Raised when a git subcommand fails for a reason other than 'this
    ref does not exist', which callers handle explicitly instead."""


def _run_git(repo_path: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        timeout=_READ_ONLY_TIMEOUT_S,
        check=False,
    )


def ref_exists(repo_path: Path, ref: str) -> bool:
    result = _run_git(repo_path, ["rev-parse", "--verify", "--quiet", ref])
    return result.returncode == 0


def resolve_commit(repo_path: Path, ref: str) -> Optional[str]:
    if not ref_exists(repo_path, ref):
        return None
    result = _run_git(repo_path, ["rev-parse", ref])
    return result.stdout.strip() or None


def merge_base(repo_path: Path, ref_a: str, ref_b: str) -> Optional[str]:
    if not (ref_exists(repo_path, ref_a) and ref_exists(repo_path, ref_b)):
        return None
    result = _run_git(repo_path, ["merge-base", ref_a, ref_b])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def is_ancestor(repo_path: Path, ancestor_ref: str, descendant_ref: str) -> Optional[bool]:
    """True if ancestor_ref's history is fully contained in
    descendant_ref's (i.e. ancestor_ref is already merged into
    descendant_ref). None if either ref cannot be resolved."""
    if not (ref_exists(repo_path, ancestor_ref) and ref_exists(repo_path, descendant_ref)):
        return None
    result = _run_git(repo_path, ["merge-base", "--is-ancestor", ancestor_ref, descendant_ref])
    return result.returncode == 0


def commits_ahead(repo_path: Path, base_ref: str, branch_ref: str) -> Optional[int]:
    base = merge_base(repo_path, base_ref, branch_ref)
    if base is None:
        return None
    result = _run_git(repo_path, ["rev-list", "--count", f"{base}..{branch_ref}"])
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def changed_files(repo_path: Path, base_ref: str, branch_ref: str) -> Optional[tuple[str, ...]]:
    """Files changed on branch_ref relative to their merge-base with
    base_ref (a three-dot diff, matching `git diff base...branch`) -- this
    is what a PR's "files changed" tab shows, not a plain two-ref diff."""
    if not (ref_exists(repo_path, base_ref) and ref_exists(repo_path, branch_ref)):
        return None
    result = _run_git(repo_path, ["diff", "--name-only", f"{base_ref}...{branch_ref}"])
    if result.returncode != 0:
        return None
    files = tuple(sorted(line for line in result.stdout.splitlines() if line))
    return files


@dataclass(frozen=True)
class GitBranchSnapshot:
    exists: bool
    commit_sha: Optional[str]
    merge_base_with_target: Optional[str]
    is_ancestor_of_target: Optional[bool]
    commits_ahead_of_merge_base: Optional[int]
    changed_files: Optional[tuple[str, ...]]


def snapshot_branch(repo_path: Path, branch_ref: str, target_ref: str) -> GitBranchSnapshot:
    """One read-only pass gathering every git-derived fact this tool needs
    about a single branch relative to a target (base) ref."""
    exists = ref_exists(repo_path, branch_ref)
    if not exists:
        return GitBranchSnapshot(
            exists=False, commit_sha=None, merge_base_with_target=None,
            is_ancestor_of_target=None, commits_ahead_of_merge_base=None, changed_files=None,
        )
    return GitBranchSnapshot(
        exists=True,
        commit_sha=resolve_commit(repo_path, branch_ref),
        merge_base_with_target=merge_base(repo_path, target_ref, branch_ref),
        is_ancestor_of_target=is_ancestor(repo_path, branch_ref, target_ref),
        commits_ahead_of_merge_base=commits_ahead(repo_path, target_ref, branch_ref),
        changed_files=changed_files(repo_path, target_ref, branch_ref),
    )
