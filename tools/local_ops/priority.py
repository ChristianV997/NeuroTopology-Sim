"""
Priority scoring for local ops actions (P26).

Deterministic. No empirical claims. No randomness.

Scoring:
    score = impact * urgency * confidence - risk_penalty

Priority bucketing:
    score >= 80 → P0
    score >= 40 → P1
    score >= 15 → P2
    else        → P3

stdlib only.
"""
from __future__ import annotations


_RISK_PENALTY = {
    "touches_runtime_semantics": 2,
    "real_data_required": 3,
    "human_review_required": 1,
}


def _risk_penalty(action) -> int:
    pen = 0
    if getattr(action, "touches_runtime_semantics", False):
        pen += _RISK_PENALTY["touches_runtime_semantics"]
    if getattr(action, "real_data_required", False):
        pen += _RISK_PENALTY["real_data_required"]
    if getattr(action, "human_review_required", False):
        pen += _RISK_PENALTY["human_review_required"]
    return pen


def _bucket_priority(score: float) -> str:
    if score >= 80:
        return "P0"
    if score >= 40:
        return "P1"
    if score >= 15:
        return "P2"
    return "P3"


def score_action(action) -> tuple[str, float, str]:
    """Return (priority, score, rationale)."""
    impact = int(getattr(action, "impact", 3))
    urgency = int(getattr(action, "urgency", 3))
    confidence = int(getattr(action, "confidence", 3))

    base = impact * urgency * confidence
    risk = _risk_penalty(action)
    score = float(base - risk)

    explicit = getattr(action, "priority", "")
    computed = _bucket_priority(score)

    rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    if explicit in rank and rank[explicit] < rank.get(computed, 9):
        final = explicit
    else:
        final = computed

    rationale = (
        f"impact={impact}, urgency={urgency}, confidence={confidence}, "
        f"risk_penalty={risk}, score={score:.1f}, explicit_hint={explicit}, "
        f"computed={computed}, final={final}"
    )

    return final, score, rationale
