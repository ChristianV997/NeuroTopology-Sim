"""Cross-split duplicate detection.

Three signals, each reported with an explicit reason code:

- ``exact_content_match``: identical canonical plan content (plan_id excluded).
- ``normalized_text_match``: identical text after NFKC/casefold/word-char
  normalisation of the free-text fields.
- ``near_duplicate_shingle_jaccard``: word-shingle Jaccard similarity of the
  question and primary endpoint at or above :data:`NEAR_DUPLICATE_THRESHOLD`.

These are lexical duplicate checks. They are not a measurement of criterion
leakage, of semantic paraphrase, or of how much a rubric can be inferred from
a question. The threshold is a constant fixed before any fixture was written.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .records import NORMALIZATION_VERSION, PlanRecord, exact_fingerprint, jaccard, normalized_fingerprint, shingles
from .splits import LOCKED_INTERNAL_VALIDATION

NEAR_DUPLICATE_THRESHOLD = 0.85
SHINGLE_SIZE = 3

REASON_EXACT = "exact_content_match"
REASON_NORMALIZED = "normalized_text_match"
REASON_NEAR = "near_duplicate_shingle_jaccard"


@dataclass(frozen=True)
class PairFinding:
    left: str
    right: str
    left_split: str
    right_split: str
    reasons: tuple[str, ...]
    jaccard: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "left_split": self.left_split,
            "right_split": self.right_split,
            "reasons": list(self.reasons),
            "jaccard": self.jaccard,
        }


@dataclass(frozen=True)
class LeakageReport:
    plan_count: int
    held_out_plan_count: int
    cross_split_findings: tuple[PairFinding, ...]
    within_split_finding_count: int
    held_out_plans_with_cross_split_match: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "signals": [REASON_EXACT, REASON_NORMALIZED, REASON_NEAR],
            "near_duplicate_threshold": NEAR_DUPLICATE_THRESHOLD,
            "shingle_size": SHINGLE_SIZE,
            "normalization_version": NORMALIZATION_VERSION,
            "plan_count": self.plan_count,
            "held_out_plan_count": self.held_out_plan_count,
            "cross_split_finding_count": len(self.cross_split_findings),
            "cross_split_findings": [f.to_dict() for f in self.cross_split_findings],
            "within_split_finding_count": self.within_split_finding_count,
            "held_out_plans_with_cross_split_match": self.held_out_plans_with_cross_split_match,
            "held_out_cross_split_match_fraction": (
                round(self.held_out_plans_with_cross_split_match / self.held_out_plan_count, 4)
                if self.held_out_plan_count
                else None
            ),
            "fraction_label": "held-out plans with a lexical cross-split duplicate; not a criterion-leakage rate",
        }


def _pair_reasons(left_sh: frozenset, right_sh: frozenset,
                  left_exact: str, right_exact: str, left_norm: str, right_norm: str) -> tuple[tuple[str, ...], float]:
    reasons: list[str] = []
    if left_exact == right_exact:
        reasons.append(REASON_EXACT)
    if left_norm == right_norm:
        reasons.append(REASON_NORMALIZED)
    score = jaccard(left_sh, right_sh)
    if score >= NEAR_DUPLICATE_THRESHOLD:
        reasons.append(REASON_NEAR)
    return tuple(reasons), round(score, 4)


def detect_cross_split_leaks(records: Sequence[PlanRecord]) -> LeakageReport:
    ordered = sorted(records, key=lambda r: r.fixture_id)
    exact = {r.fixture_id: exact_fingerprint(r.plan) for r in ordered}
    norm = {r.fixture_id: normalized_fingerprint(r.plan) for r in ordered}
    shingle = {r.fixture_id: shingles(r.plan, SHINGLE_SIZE) for r in ordered}

    cross: list[PairFinding] = []
    within = 0
    for i, left in enumerate(ordered):
        for right in ordered[i + 1:]:
            reasons, score = _pair_reasons(
                shingle[left.fixture_id], shingle[right.fixture_id],
                exact[left.fixture_id], exact[right.fixture_id],
                norm[left.fixture_id], norm[right.fixture_id],
            )
            if not reasons:
                continue
            if left.split == right.split:
                within += 1
                continue
            cross.append(PairFinding(left.fixture_id, right.fixture_id, left.split, right.split, reasons, score))

    held_out_ids = {r.fixture_id for r in ordered if r.split == LOCKED_INTERNAL_VALIDATION}
    flagged_held_out = {
        f.left if f.left in held_out_ids else f.right
        for f in cross
        if f.left in held_out_ids or f.right in held_out_ids
    }
    return LeakageReport(
        plan_count=len(ordered),
        held_out_plan_count=len(held_out_ids),
        cross_split_findings=tuple(cross),
        within_split_finding_count=within,
        held_out_plans_with_cross_split_match=len(flagged_held_out),
    )
