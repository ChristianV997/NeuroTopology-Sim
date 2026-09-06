"""Duplicate and superseded work-order detection.

Both checks operate purely on already-gathered facts (changed-file sets
and git ancestry) -- no new I/O.
"""
from __future__ import annotations

from itertools import combinations
from typing import Optional


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def detect_possible_duplicates(
    changed_files_by_work_order: dict[str, Optional[tuple[str, ...]]],
    stacked_pairs: frozenset[tuple[str, str]] = frozenset(),
    threshold: float = 0.6,
) -> list[dict]:
    """Flag work-order pairs whose changed-file sets overlap heavily
    (Jaccard similarity >= threshold) as possible duplicates -- two
    branches independently doing overlapping work. Pairs already known to
    be in a stack relationship (one built directly on the other) are
    excluded, since a stacked PR's small diff naturally has zero overlap
    with its base and is not a duplicate by construction; this parameter
    exists for a caller that instead wants to compare *effective* (base
    branch-relative) diffs and still knows about the stack."""
    known = {
        work_order_id: frozenset(files)
        for work_order_id, files in changed_files_by_work_order.items()
        if files is not None
    }
    findings: list[dict] = []
    for (id_a, files_a), (id_b, files_b) in combinations(sorted(known.items()), 2):
        if (id_a, id_b) in stacked_pairs or (id_b, id_a) in stacked_pairs:
            continue
        similarity = _jaccard(files_a, files_b)
        if similarity >= threshold:
            findings.append({
                "work_order_a": id_a, "work_order_b": id_b,
                "jaccard_similarity": round(similarity, 3),
                "shared_files": sorted(files_a & files_b),
            })
    return findings


def detect_superseded(
    ancestry_by_pair: dict[tuple[str, str], Optional[bool]],
) -> list[dict]:
    """``ancestry_by_pair``: {(work_order_a, work_order_b): is_a_ancestor_of_b}
    for pairs the caller has already computed via git_source.is_ancestor
    on the two branches directly (not against the shared target). When
    True, work_order_a's entire history is contained in work_order_b's --
    its own branch is superseded by the other, newer branch."""
    findings: list[dict] = []
    for (work_order_a, work_order_b), is_ancestor in sorted(ancestry_by_pair.items()):
        if is_ancestor:
            findings.append({
                "superseded_work_order": work_order_a,
                "superseded_by_work_order": work_order_b,
                "evidence": f"{work_order_a}'s branch is a git ancestor of {work_order_b}'s branch",
            })
    return findings
