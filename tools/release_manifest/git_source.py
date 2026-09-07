"""Read-only git plumbing. Every function shells out to a read-only git
subcommand -- no checkout/merge/rebase/push/branch-delete anywhere.
Independently implemented (no import of any sibling package's git_source),
tested against local git fixture repos, so no network is needed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

_TIMEOUT_S = 30


def _run(repo_path: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True, text=True, timeout=_TIMEOUT_S, check=False,
    )


def ref_exists(repo_path: Path, ref: str) -> bool:
    """True only if ``ref`` resolves to a real, existing commit object.

    Appends ``^{commit}`` rather than calling a bare
    ``rev-parse --verify --quiet <ref>``: git treats any well-formed
    40-character hex string as a syntactically valid object name and
    reports it "verified" even when NO object with that hash exists in
    the repository -- only a short/abbreviated hash triggers git's real
    object-database lookup. A caller-supplied commit hash (e.g. from a
    handoff message) must never be accepted as existing just because it
    looks like a hash; ``^{commit}`` forces git to actually dereference
    and confirm the object is real.
    """
    return _run(repo_path, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]).returncode == 0


def resolve_commit(repo_path: Path, ref: str) -> Optional[str]:
    result = _run(repo_path, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def is_ancestor(repo_path: Path, ancestor_ref: str, descendant_ref: str) -> Optional[bool]:
    if not (ref_exists(repo_path, ancestor_ref) and ref_exists(repo_path, descendant_ref)):
        return None
    return _run(repo_path, ["merge-base", "--is-ancestor", ancestor_ref, descendant_ref]).returncode == 0


def merge_base(repo_path: Path, ref_a: str, ref_b: str) -> Optional[str]:
    if not (ref_exists(repo_path, ref_a) and ref_exists(repo_path, ref_b)):
        return None
    result = _run(repo_path, ["merge-base", ref_a, ref_b])
    return result.stdout.strip() or None if result.returncode == 0 else None


def changed_files(repo_path: Path, base_ref: str, head_ref: str) -> Optional[tuple[str, ...]]:
    """Files changed on ``head_ref`` relative to its merge-base with
    ``base_ref`` (a three-dot diff -- what a PR's "files changed" view
    shows)."""
    if not (ref_exists(repo_path, base_ref) and ref_exists(repo_path, head_ref)):
        return None
    result = _run(repo_path, ["diff", "--name-only", f"{base_ref}...{head_ref}"])
    if result.returncode != 0:
        return None
    return tuple(sorted(line for line in result.stdout.splitlines() if line))


def find_merge_commit_for_pr_number(repo_path: Path, tip_ref: str, pr_number: int) -> Optional[str]:
    """Best-effort search of ``tip_ref``'s log for a merge commit naming
    ``pr_number`` in its subject line. Finding one is evidence the PR's
    code landed on this branch -- never, by itself, evidence that
    GitHub's own 'merged' field for that PR is true."""
    if not ref_exists(repo_path, tip_ref):
        return None
    result = _run(repo_path, ["log", tip_ref, "--format=%H %s", "-n", "5000"])
    if result.returncode != 0:
        return None
    needles = (f"#{pr_number} ", f"(#{pr_number})", f"pull request #{pr_number}")
    for line in result.stdout.splitlines():
        if " " not in line:
            continue
        sha, _, subject = line.partition(" ")
        if any(needle in subject for needle in needles):
            return sha
    return None
