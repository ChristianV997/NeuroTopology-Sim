"""Changed-file ownership and duplicate-ownership (Jaccard) detection.

Freshly, independently implemented for this package -- conceptually
similar to tools/integration_reconciliation/duplicate_detection.py but
not imported from it (that package is owned by a sibling branch running
in parallel this round).
"""
from __future__ import annotations

from itertools import combinations
from typing import Mapping, Sequence

from .models import ChangedFileOwnership

DUPLICATE_JACCARD_THRESHOLD = 0.3


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    set_a, set_b = set(a), set(b)
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def find_duplicate_ownership(
    ownerships: Sequence[ChangedFileOwnership],
    threshold: float = DUPLICATE_JACCARD_THRESHOLD,
) -> list[dict]:
    """Pairwise-compare every ownership's changed-file set against every
    other; report any pair whose Jaccard similarity meets ``threshold``
    (and any pair sharing at least one literal file) as a duplicate
    finding. Deterministic order: sorted by the pair's labels."""
    findings: list[dict] = []
    ordered = sorted(ownerships, key=lambda o: o.label)
    for left, right in combinations(ordered, 2):
        shared = sorted(set(left.changed_files) & set(right.changed_files))
        score = jaccard(left.changed_files, right.changed_files)
        if shared or score >= threshold:
            findings.append(
                {
                    "labels": [left.label, right.label],
                    "shared_files": shared,
                    "jaccard": round(score, 4),
                }
            )
    return findings


def ownership_to_dict(ownerships: Sequence[ChangedFileOwnership]) -> dict:
    return {o.label: list(o.changed_files) for o in ownerships}
