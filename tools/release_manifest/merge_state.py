"""The core 11-state merge classifier.

Maps real git ancestry + an optional PR snapshot + CI classification +
scientific-gate status + duplicate-ownership findings into exactly one
of ``models.MERGE_STATES``.

Priority order (highest first) and why:

1. ``unknown``            -- the claimed commit does not resolve to a real
   git object at all (includes the fabricated-hash case). Nothing else can
   be evaluated safely once the very identity of the commit is unverifiable,
   so this always wins.
2. ``merged_into_main``    -- either (a) real git ancestry shows the commit
   IS the current head of, or an ancestor of, ``target_branch`` (a hard
   fact, independent of any PR snapshot), or (b) the PR snapshot reports
   ``merged=True`` and its ``base_ref`` matches ``target_branch``. A PR merge
   into another base, or one with no verifiable base, is not target ancestry.
   A disagreement between matching PR metadata and local ancestry is recorded
   as a blocker note, but the matching-base snapshot still covers squash merges.
   This is the one deliberate exception to "local merge commit alone is not
   enough": a direct ``is_ancestor`` check against the real target ref is a
   hard fact, not a heuristic commit-message search.
3. ``duplicate``           -- this work's changed-file set overlaps another
   concurrent owner's above the Jaccard/shared-file threshold, and it is
   not (per #2) already merged. Surfacing an ownership collision early
   matters more than any downstream CI/science state.
4. ``blocked_by_scientific_review`` -- the scientific gate reports a
   genuinely evidenced negative verdict (never a merely-insufficient-data
   case, which is not blocking -- see scientific_gate.py).
5. ``blocked_by_ci``       -- worst classified check is ``failing``.
6. ``blocked_by_infrastructure`` -- worst classified check is
   ``infrastructure_blocked`` (strictly below a real ``failing`` verdict --
   an evidenced failure always outranks an infrastructure excuse).
7. ``blocked_by_dependency`` -- caller-supplied unmet dependency list is
   non-empty.
8. ``superseded``          -- the PR snapshot says ``closed`` (and not
   merged) while another, later reference covers the same ground.
9. ``integration_only``    -- real ancestry shows the commit is the head of,
   or an ancestor of, ``integration_branch`` but NOT of ``target_branch``.
10. ``ancestor_stale``     -- the commit resolves to a real object but is
    neither the head of, nor an ancestor of, either ``target_branch`` or
    ``integration_branch`` -- it exists, off the authoritative lines.
11. ``open_unintegrated``  -- a PR snapshot exists and is open, but ancestry
    places it in none of the above buckets.
12. ``unknown`` (fallback) -- none of the above could be determined, most
    often because ``github_state`` is ``unavailable`` and no local ancestry
    signal resolved either way. Absence of data, not evidence of a problem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import CHECK_STATES, MERGE_STATES, RELEASE_STATES, PRSnapshot


@dataclass
class MergeStateContext:
    commit_resolves: bool
    is_current_head_of_target: bool = False
    is_ancestor_of_target: bool = False
    is_current_head_of_integration: bool = False
    is_ancestor_of_integration: bool = False
    pr_snapshot: Optional[PRSnapshot] = None
    worst_ci_state: str = "unavailable"
    scientific_blocking: bool = False
    duplicate_findings: tuple = field(default_factory=tuple)
    dependency_blockers: tuple = field(default_factory=tuple)
    superseded_by: Optional[str] = None
    target_branch: str = "main"


def _branch_ref_name(ref: str | None) -> str | None:
    if not isinstance(ref, str):
        return None
    value = ref.strip()
    if value.startswith("refs/heads/"):
        value = value[len("refs/heads/"):]
    elif value.startswith("refs/remotes/"):
        value = value[len("refs/remotes/"):].split("/", 1)[-1]
    elif value.startswith("origin/"):
        value = value[len("origin/"):]
    return value or None


def classify_merge_state(ctx: MergeStateContext) -> tuple[str, list[str]]:
    """Return ``(merge_state, blockers)``. ``blockers`` is a list of
    human-readable strings explaining every contributing/contradicting
    signal -- never just the winning one, so a reader can see what was
    overridden and why."""
    blockers: list[str] = []

    if ctx.worst_ci_state not in CHECK_STATES:
        raise ValueError(f"unrecognized CI state: {ctx.worst_ci_state!r}")

    if not ctx.commit_resolves:
        blockers.append("verified_head_commit does not resolve to a real git object")
        return "unknown", blockers

    pr = ctx.pr_snapshot
    ancestry_says_merged = ctx.is_current_head_of_target or ctx.is_ancestor_of_target
    target_name = _branch_ref_name(ctx.target_branch)
    pr_base_name = _branch_ref_name(pr.base_ref) if pr is not None else None
    pr_base_matches_target = target_name is not None and pr_base_name == target_name
    pr_says_merged = pr.merged is True and pr_base_matches_target if pr is not None else False

    if pr is not None and pr.merged is True and not pr_base_matches_target:
        blockers.append(
            f"PR snapshot reports merged=True but base_ref {pr.base_ref!r} does not verify "
            f"target_branch {ctx.target_branch!r}; PR merge status alone cannot establish target ancestry"
        )

    if ancestry_says_merged or pr_says_merged:
        if pr is not None and pr.merged is False and ancestry_says_merged:
            blockers.append(
                "contradiction: real git ancestry places this commit on target_branch, "
                "but the PR snapshot's own merged field is False -- ancestry (a hard fact) wins"
            )
        if pr_says_merged and not ancestry_says_merged:
            blockers.append(
                "contradiction: PR snapshot reports merged=True on the target base but local ancestry does not "
                "place this commit on target_branch (e.g. squash-merge rewrote history) -- "
                "the matching PR base snapshot is authoritative for its own merged state"
            )
        return "merged_into_main", blockers

    if ctx.duplicate_findings:
        blockers.append(f"changed-file ownership overlaps: {list(ctx.duplicate_findings)}")
        return "duplicate", blockers

    if ctx.scientific_blocking:
        blockers.append("scientific gate reports an evidenced negative verdict")
        return "blocked_by_scientific_review", blockers

    if ctx.worst_ci_state == "failing":
        blockers.append("worst classified CI check state is failing")
        return "blocked_by_ci", blockers

    if ctx.worst_ci_state == "infrastructure_blocked":
        blockers.append("worst classified CI check state is infrastructure_blocked")
        return "blocked_by_infrastructure", blockers

    if ctx.dependency_blockers:
        blockers.append(f"unmet dependencies: {list(ctx.dependency_blockers)}")
        return "blocked_by_dependency", blockers

    if pr is not None and pr.state == "closed" and pr.merged is False and ctx.superseded_by:
        blockers.append(f"PR closed without merging; superseded by {ctx.superseded_by!r}")
        return "superseded", blockers

    if ctx.is_current_head_of_integration or ctx.is_ancestor_of_integration:
        blockers.append("real git ancestry places this commit on integration_branch only")
        return "integration_only", blockers

    if not (ancestry_says_merged or ctx.is_current_head_of_integration or ctx.is_ancestor_of_integration):
        if pr is None:
            blockers.append(
                "commit resolves to a real object but is off every known lineage "
                "(target_branch, integration_branch) and no PR snapshot was supplied"
            )
            return "ancestor_stale", blockers

    if pr is not None and pr.state == "open":
        blockers.append("PR snapshot is open; no ancestry places it on any tracked branch")
        return "open_unintegrated", blockers

    blockers.append("insufficient evidence to place this commit in any specific bucket")
    return "unknown", blockers


def classify_release_state(
    ctx: MergeStateContext,
    *,
    merge_state: str,
    scientific_gate_value: object,
) -> tuple[str, list[str]]:
    """Classify release eligibility independently from technical integration.

    ``merge_state`` records where a commit sits in git history.  It must not
    be used as a proxy for admissible scientific evidence, CI evidence, or
    operational release readiness.  The manifest builder exposes both fields
    so downstream consumers cannot mistake a landed commit for a releasable
    result.
    """
    if merge_state not in MERGE_STATES:
        raise ValueError(f"unrecognized merge state: {merge_state!r}")
    if ctx.worst_ci_state not in CHECK_STATES:
        raise ValueError(f"unrecognized CI state: {ctx.worst_ci_state!r}")

    blockers: list[str] = []
    if not ctx.commit_resolves:
        blockers.append("release state unknown because the source commit does not resolve")
        return "unknown", blockers

    if ctx.scientific_blocking or scientific_gate_value == "blocked":
        blockers.append("release blocked by the independent scientific gate")
        return "blocked_by_scientific_review", blockers

    if ctx.worst_ci_state == "failing":
        blockers.append("release blocked because the worst CI state is failing")
        return "blocked_by_ci", blockers

    if ctx.worst_ci_state == "infrastructure_blocked":
        blockers.append("release blocked because CI infrastructure is unavailable")
        return "blocked_by_infrastructure", blockers

    if ctx.worst_ci_state != "passing":
        blockers.append(
            f"release requires passing CI; worst CI state is {ctx.worst_ci_state!r}"
        )
        return "inconclusive", blockers

    if ctx.dependency_blockers:
        blockers.append(f"release blocked by unmet dependencies: {list(ctx.dependency_blockers)}")
        return "blocked_by_dependency", blockers

    if merge_state != "merged_into_main":
        blockers.append("release cannot be evaluated as ready until the commit is integrated into target_branch")
        return "not_integrated", blockers

    # The current metadata-only gate has no artifact-backed proof object.  A
    # bare string (including "pass") cannot establish release eligibility.
    blockers.append(
        "release readiness requires independently verified artifact-backed evidence; "
        "a gate status string is insufficient"
    )
    return "inconclusive", blockers


assert set(MERGE_STATES) == {
    "merged_into_main", "integration_only", "open_unintegrated", "ancestor_stale",
    "superseded", "duplicate", "blocked_by_dependency", "blocked_by_ci",
    "blocked_by_infrastructure", "blocked_by_scientific_review", "unknown",
}

assert set(RELEASE_STATES) == {
    "ready_for_release", "not_integrated", "blocked_by_scientific_review",
    "blocked_by_ci", "blocked_by_infrastructure", "blocked_by_dependency",
    "inconclusive", "unknown",
}
