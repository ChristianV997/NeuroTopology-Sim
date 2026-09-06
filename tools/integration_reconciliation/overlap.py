"""Changed-file overlap across work orders' branches.

Pure set arithmetic over already-gathered `changed_files` tuples (from
git_source.snapshot_branch) -- this module performs no git or network
I/O itself.
"""
from __future__ import annotations

from itertools import combinations
from typing import Optional


def compute_overlaps(
    changed_files_by_work_order: dict[str, Optional[tuple[str, ...]]],
) -> dict[str, list[str]]:
    """Return {"work_order_a|work_order_b": [shared, files, ...]} for every
    pair that shares at least one changed file. Work orders whose
    changed_files is None (branch absent, or the diff could not be
    computed) are skipped -- absence of data is not evidence of "no
    overlap"."""
    overlaps: dict[str, list[str]] = {}
    known = {
        work_order_id: set(files)
        for work_order_id, files in changed_files_by_work_order.items()
        if files is not None
    }
    for (id_a, files_a), (id_b, files_b) in combinations(sorted(known.items()), 2):
        shared = files_a & files_b
        if shared:
            key = f"{id_a}|{id_b}"
            overlaps[key] = sorted(shared)
    return overlaps
