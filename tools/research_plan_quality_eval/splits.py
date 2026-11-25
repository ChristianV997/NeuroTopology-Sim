"""Group-level split definition.

Plans are split by group (source / project / topic), never by individual
plan, so near-duplicate plans from one project cannot land on both sides of
a split. Role names are the ones already used by
``benchmarks.split_policy.DATASET_ROLES``.
"""
from __future__ import annotations

import unicodedata
from typing import Iterable, Sequence

from .errors import InsufficientEvaluationSetError, ManifestError
from .records import PlanRecord, sha256_hex

DEVELOPMENT = "development"
LOCKED_INTERNAL_VALIDATION = "locked_internal_validation"
SPLIT_ROLES: tuple[str, ...] = (DEVELOPMENT, LOCKED_INTERNAL_VALIDATION)

MIN_PLANS_PER_ROLE = 3
MIN_GROUPS_PER_ROLE = 2


def normalise_group_id(group_id: str) -> str:
    """Spelling variants of one project (case, width, stray spaces) share a key."""
    return " ".join(unicodedata.normalize("NFKC", group_id).casefold().split())


def check_group_integrity(groups_to_split: Iterable[tuple[str, str]]) -> None:
    """Raise if any group id appears under more than one split role."""
    seen: dict[str, str] = {}
    for group_id, split in groups_to_split:
        previous = seen.setdefault(normalise_group_id(group_id), split)
        if previous != split:
            raise ManifestError(
                f"group {group_id!r} is assigned to both {previous!r} and {split!r}"
            )


def assign_group_splits(group_ids: Iterable[str], *, held_out_fraction: float, salt: str) -> dict[str, str]:
    """Deterministically assign whole groups to roles.

    Groups are ordered by a salted SHA-256 of their id, so the same inputs
    always produce the same assignment and changing ``salt`` reshuffles it.
    """
    if not 0.0 < held_out_fraction < 1.0:
        raise ValueError("held_out_fraction must be strictly between 0 and 1")
    groups = sorted(set(group_ids))
    if len(groups) < 2 * MIN_GROUPS_PER_ROLE:
        raise InsufficientEvaluationSetError(
            f"need at least {2 * MIN_GROUPS_PER_ROLE} groups to form both roles, got {len(groups)}"
        )
    ordered = sorted(groups, key=lambda g: sha256_hex(f"{salt}|{g}".encode("utf-8")))
    held_count = min(max(MIN_GROUPS_PER_ROLE, round(len(groups) * held_out_fraction)), len(groups) - MIN_GROUPS_PER_ROLE)
    held = set(ordered[:held_count])
    return {g: (LOCKED_INTERNAL_VALIDATION if g in held else DEVELOPMENT) for g in groups}


def require_sufficient(records: Sequence[PlanRecord]) -> None:
    """Refuse an empty set, a missing role, or a role below the minimum size."""
    if not records:
        raise InsufficientEvaluationSetError("evaluation set is empty")
    for role in SPLIT_ROLES:
        members = [r for r in records if r.split == role]
        groups = {r.group_id for r in members}
        if len(members) < MIN_PLANS_PER_ROLE or len(groups) < MIN_GROUPS_PER_ROLE:
            raise InsufficientEvaluationSetError(
                f"split {role!r} has {len(members)} plans in {len(groups)} groups; "
                f"needs at least {MIN_PLANS_PER_ROLE} plans in {MIN_GROUPS_PER_ROLE} groups"
            )


def split_summary(records: Sequence[PlanRecord]) -> dict[str, object]:
    roles: dict[str, object] = {}
    for role in SPLIT_ROLES:
        members = sorted((r for r in records if r.split == role), key=lambda r: r.fixture_id)
        roles[role] = {
            "plan_count": len(members),
            "group_ids": sorted({r.group_id for r in members}),
            "fixture_ids": [r.fixture_id for r in members],
        }
    return {
        "unit": "group_id (source/project/topic)",
        "method": "explicit group assignment recorded in the fixture manifest",
        "roles": roles,
    }
