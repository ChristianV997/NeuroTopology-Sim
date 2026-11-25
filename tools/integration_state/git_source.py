"""Read-only git plumbing. Every function shells out to a read-only git
subcommand -- no checkout/merge/rebase/push/branch-delete anywhere in
this module. Independently implemented (not imported) from
tools/integration_reconciliation/git_source.py, per this branch's
explicit no-dependency-on-that-package constraint; tested against local
git fixture repos, so no network is needed.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
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

    Deliberately appends ``^{commit}`` rather than calling
    ``rev-parse --verify --quiet <ref>`` directly: git treats a
    well-formed 40-character hex string as a syntactically valid object
    name and reports it "verified" even when NO object with that hash
    exists in the repository at all -- only a short/abbreviated hash
    triggers git's actual object-database lookup. This is exactly the
    real-world failure mode this tool exists to catch (a handoff quoting
    a full-length commit hash that shares another real commit's short
    prefix but was never actually pushed), so this function must not
    inherit that blind spot. ``^{commit}`` forces git to dereference and
    confirm the object genuinely exists and is a commit.
    """
    return _run(repo_path, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]).returncode == 0


def resolve_commit(repo_path: Path, ref: str) -> Optional[str]:
    """Resolve ``ref`` to its full commit sha, or None if it does not
    exist as a real object (see ``ref_exists`` for why ``^{commit}`` is
    required rather than a bare ``rev-parse``)."""
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


def commit_exists_in_history(repo_path: Path, commit: str, tip_ref: str) -> Optional[bool]:
    """True if ``commit`` is reachable from ``tip_ref`` (i.e. actually
    appears in that branch's history) -- used to verify a claim like
    "PR #219 was integrated into this branch" against real history rather
    than trusting the claim."""
    if not ref_exists(repo_path, tip_ref):
        return None
    if not ref_exists(repo_path, commit):
        return False
    return is_ancestor(repo_path, commit, tip_ref)


def find_merge_commit_for_pr_number(repo_path: Path, tip_ref: str, pr_number: int) -> Optional[str]:
    """Search ``tip_ref``'s log for a merge commit whose subject line
    names ``pr_number`` (matching GitHub's own default merge-commit
    subject, e.g. "Merge pull request #219 ..." or "... (#219)"). Returns
    the commit sha if found, else None. This is used only as a
    cross-reference; per this tool's design, the mere existence of such a
    commit is never, by itself, treated as proof the PR's own `merged`
    field is true -- see models.PRSnapshot.merged, which is the
    authoritative source for that question.
    """
    if not ref_exists(repo_path, tip_ref):
        return None
    result = _run(repo_path, ["log", tip_ref, "--format=%H %s", "-n", "5000"])
    if result.returncode != 0:
        return None
    needle_a = f"#{pr_number} "
    needle_b = f"(#{pr_number})"
    needle_c = f"pull request #{pr_number}"
    for line in result.stdout.splitlines():
        if " " not in line:
            continue
        sha, _, subject = line.partition(" ")
        if needle_a in subject or needle_b in subject or needle_c in subject:
            return sha
    return None


@dataclass(frozen=True)
class LocalIntegrationSnapshot:
    main_tip: Optional[str]
    local_worktree_tip: Optional[str]
    merge_base_head_and_main: Optional[str]
    is_head_ancestor_of_main: Optional[bool]
