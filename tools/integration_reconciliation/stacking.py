"""Stacked-PR awareness.

A PR is "stacked" when its declared base branch is another open branch's
head, not the ultimate target (e.g. `main`) -- so its GitHub diff already
excludes the base PR's own commits, but a naive "diff branch against
main" would double-count them. This module only reasons over PR
head/base metadata (from a GitHub snapshot) plus git ancestry; it never
edits or fetches anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import git_source


@dataclass(frozen=True)
class StackRelationship:
    work_order_id: str
    head_ref: str
    base_ref: str
    is_stacked: bool  # base_ref is not the ultimate target ref
    base_work_order_id: Optional[str]  # which known work order's branch this is stacked on, if any
    dependents: tuple[str, ...]  # work_order_ids whose base_ref == this one's head_ref


def _short_name(ref: str) -> str:
    """Strip a leading 'origin/' so PR base/head refs (which never carry
    it) compare equal to git-side refs (which, in this tool, always do)."""
    return ref[len("origin/"):] if ref.startswith("origin/") else ref


def build_stack_relationships(
    work_order_branches: dict[str, str],  # work_order_id -> branch name (no "origin/" prefix)
    pr_base_by_work_order: dict[str, Optional[str]],  # work_order_id -> its PR's base_ref, or None if unknown
    target_branch: str,  # e.g. "main"
) -> dict[str, StackRelationship]:
    """Pure function over already-gathered data -- no I/O."""
    target = _short_name(target_branch)
    branch_to_work_order = {branch: work_order_id for work_order_id, branch in work_order_branches.items()}

    relationships: dict[str, StackRelationship] = {}
    dependents_of: dict[str, list[str]] = {work_order_id: [] for work_order_id in work_order_branches}

    for work_order_id, branch in work_order_branches.items():
        base_ref = pr_base_by_work_order.get(work_order_id)
        base_short = _short_name(base_ref) if base_ref else None
        is_stacked = base_short is not None and base_short != target
        base_work_order_id = branch_to_work_order.get(base_short) if is_stacked else None
        if base_work_order_id is not None:
            dependents_of.setdefault(base_work_order_id, []).append(work_order_id)
        relationships[work_order_id] = StackRelationship(
            work_order_id=work_order_id, head_ref=branch, base_ref=base_short or target,
            is_stacked=is_stacked, base_work_order_id=base_work_order_id, dependents=(),
        )

    # Second pass: fill in dependents now that every relationship exists.
    for work_order_id, relationship in list(relationships.items()):
        relationships[work_order_id] = StackRelationship(
            work_order_id=relationship.work_order_id, head_ref=relationship.head_ref,
            base_ref=relationship.base_ref, is_stacked=relationship.is_stacked,
            base_work_order_id=relationship.base_work_order_id,
            dependents=tuple(sorted(dependents_of.get(work_order_id, []))),
        )
    return relationships


def effective_diff_ref_pair(
    relationship: StackRelationship, target_branch: str
) -> tuple[str, str]:
    """The (base_ref, head_ref) pair to diff for this work order's OWN,
    non-double-counted changes: its declared PR base when stacked, or the
    ultimate target when not."""
    if relationship.is_stacked:
        return f"origin/{relationship.base_ref}", f"origin/{relationship.head_ref}"
    return target_branch, f"origin/{relationship.head_ref}"


def effective_changed_files(
    repo_path: Path, relationship: StackRelationship, target_branch: str
) -> Optional[tuple[str, ...]]:
    base_ref, head_ref = effective_diff_ref_pair(relationship, target_branch)
    return git_source.changed_files(repo_path, base_ref, head_ref)
