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
   fact, independent of any PR snapshot), or (b) the PR snapshot's own
   ``merged`` field is ``True`` (GitHub's own record is authoritative for
   its own state even absent local ancestry, e.g. a squash-merge that
   rewrites history). A disagreement between the two is never silently
   resolved -- it is recorded as a blocker note, but the release is still
   reported as merged (never as "integration-only" when it plainly landed).
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

from .models import CHECK_STATES, MERGE_STATES, PRSnapshot


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
    pr_says_merged = pr.merged if pr is not None else None

    if ancestry_says_merged or pr_says_merged is True:
        if pr_says_merged is False and ancestry_says_merged:
            blockers.append(
                "contradiction: real git ancestry places this commit on target_branch, "
                "but the PR snapshot's own merged field is False -- ancestry (a hard fact) wins"
            )
        if pr_says_merged is True and not ancestry_says_merged:
            blockers.append(
                "contradiction: PR snapshot reports merged=True but local ancestry does not "
                "place this commit on target_branch (e.g. squash-merge rewrote history) -- "
                "PR snapshot's own record is authoritative for its own merged state"
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

    if pr is not None and pr.state == "closed" and pr_says_merged is not True and ctx.superseded_by:
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


assert set(MERGE_STATES) == {
    "merged_into_main", "integration_only", "open_unintegrated", "ancestor_stale",
    "superseded", "duplicate", "blocked_by_dependency", "blocked_by_ci",
    "blocked_by_infrastructure", "blocked_by_scientific_review", "unknown",
}
