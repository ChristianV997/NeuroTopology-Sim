"""Read-only validation of reconciliation fixture references and ancestry."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable

from . import git_source

_FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run local Git plumbing only; never fetches or contacts a remote."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def audit_reference(repo: Path, reference: str, *, require_branch: bool = False) -> dict:
    """Classify one branch/ref/commit without accepting fabricated hashes."""
    if _FULL_SHA.fullmatch(reference):
        result = _run(repo, "cat-file", "-e", f"{reference}^{{commit}}")
        exists = result.returncode == 0
        return {
            "reference": reference,
            "kind": "commit",
            "exists": exists,
            "commit": reference if exists else None,
            "classification": "valid_commit" if exists else "missing_reference",
            "evidence": "real commit object" if exists else "no commit object resolved",
        }

    if require_branch:
        branch_ref = reference if reference.startswith("refs/") else f"refs/remotes/{reference}"
        result = _run(repo, "show-ref", "--verify", "--quiet", branch_ref)
        if result.returncode != 0:
            return {
                "reference": reference,
                "kind": "branch",
                "exists": False,
                "commit": None,
                "classification": "missing_reference",
                "evidence": "required branch ref is absent",
            }

    result = _run(repo, "rev-parse", "--verify", f"{reference}^{{commit}}")
    commit = result.stdout.strip() or None
    exists = result.returncode == 0 and commit is not None
    return {
        "reference": reference,
        "kind": "branch" if require_branch else "ref",
        "exists": exists,
        "commit": commit,
        "classification": "valid_branch" if require_branch and exists else (
            "valid_ref" if exists else "missing_reference"
        ),
        "evidence": "resolved to a real commit object" if exists else "ref is absent",
    }

def audit_references(
    repo: Path,
    references: Iterable[str],
    *,
    required_branches: Iterable[str] = (),
) -> list[dict]:
    """Audit refs deterministically, preserving explicit missing blockers."""
    branch_set = frozenset(required_branches)
    return [
        audit_reference(repo, reference, require_branch=reference in branch_set)
        for reference in sorted(set(references))
    ]


def audit_ancestry(
    repo: Path,
    ancestor_ref: str,
    descendant_ref: str,
    *,
    textual_pr_claim: bool | None = None,
) -> dict:
    """Separate Git ancestry from a textual PR claim or local merge message."""
    ancestry = git_source.is_ancestor(repo, ancestor_ref, descendant_ref)
    return {
        "ancestor_ref": ancestor_ref,
        "descendant_ref": descendant_ref,
        "ancestry_valid": ancestry is True,
        "ancestry": ancestry,
        "textual_pr_claim": textual_pr_claim,
        "pr_merge_verified": False,
        "evidence": (
            "Git ancestry only; provider PR metadata is required to verify a merged PR"
        ),
    }
