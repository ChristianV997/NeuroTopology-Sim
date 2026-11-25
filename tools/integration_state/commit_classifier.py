"""Requirement 9: classify a supplied handoff commit as one of
current_head / ancestor / stale / unknown, relative to the authoritative
head commit -- never by comparing short-prefix text, always by resolving
each to a real git object first.

Definitions (documented here since the four names alone are ambiguous):
  - current_head: the claimed commit IS the authoritative head, exactly.
  - ancestor: the claimed commit resolves to a real object and is a git
    ancestor of the authoritative head -- a genuine, verifiable earlier
    point in the SAME line of history (a real "stale but in-lineage"
    handoff).
  - stale: the claimed commit resolves to a real object, but is NEITHER
    the head NOR an ancestor of it -- it exists somewhere in the
    repository (a diverged branch, an abandoned line, a since-rebased-
    away commit) but is not part of the authoritative line at all.
  - unknown: the claimed commit does not resolve to any real git object
    in this repository -- it cannot be verified, whether because it was
    mistyped, truncated, fabricated, or simply never pushed anywhere
    this checkout can see.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import git_source
from .models import HandoffClaim, HandoffVerification


def classify_commit(repo_path: Path, claimed_commit: str, authoritative_head: str) -> HandoffVerification:
    claim = HandoffClaim(label=claimed_commit, claimed_commit=claimed_commit)
    resolved = git_source.resolve_commit(repo_path, claimed_commit)

    if resolved is None:
        return HandoffVerification(
            claim=claim, classification="unknown", resolved_commit=None,
            evidence=f"{claimed_commit!r} does not resolve to any object in this repository",
        )

    head_resolved = git_source.resolve_commit(repo_path, authoritative_head)
    if head_resolved is not None and resolved == head_resolved:
        return HandoffVerification(
            claim=claim, classification="current_head", resolved_commit=resolved,
            evidence=f"resolves to {resolved}, matching the authoritative head",
        )

    ancestor = git_source.is_ancestor(repo_path, resolved, authoritative_head)
    if ancestor is True:
        return HandoffVerification(
            claim=claim, classification="ancestor", resolved_commit=resolved,
            evidence=f"resolves to {resolved}, a git ancestor of the authoritative head",
        )

    return HandoffVerification(
        claim=claim, classification="stale", resolved_commit=resolved,
        evidence=f"resolves to {resolved}, but is not the authoritative head and not one of its ancestors",
    )


def classify_all(
    repo_path: Path, labeled_claims: dict[str, str], authoritative_head: str
) -> list[HandoffVerification]:
    """``labeled_claims``: {label: claimed_commit}."""
    results: list[HandoffVerification] = []
    for label, claimed_commit in labeled_claims.items():
        verification = classify_commit(repo_path, claimed_commit, authoritative_head)
        results.append(HandoffVerification(
            claim=HandoffClaim(label=label, claimed_commit=claimed_commit),
            classification=verification.classification,
            resolved_commit=verification.resolved_commit,
            evidence=verification.evidence,
        ))
    return results


def detect_contradictory_handoffs(verifications: list[HandoffVerification]) -> tuple[bool, Optional[str]]:
    """Two handoffs are contradictory when more than one distinct,
    *resolvable* commit is each independently claimed to be the current
    head, or when handoffs disagree in a way that cannot both be true
    (e.g. two different real, non-ancestor-related commits both labeled
    "final"). A single genuinely-stale-vs-current progression (older
    handoffs are ancestors of a newer one) is NOT a contradiction -- it
    is the normal, expected shape of a project moving forward."""
    current_head_claims = {v.resolved_commit for v in verifications if v.classification == "current_head"}
    diverged = [v for v in verifications if v.classification == "stale"]

    if len(current_head_claims) > 1:
        return True, f"multiple distinct commits are each claimed to be the current head: {sorted(current_head_claims)}"
    if diverged:
        labels = ", ".join(v.claim.label for v in diverged)
        return True, (
            f"{len(diverged)} handoff(s) resolve to real commits that are neither the authoritative head "
            f"nor an ancestor of it (diverged/off-lineage): {labels}"
        )
    return False, None
