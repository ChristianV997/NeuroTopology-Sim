"""Typed structures for the integration-state lock report."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

COMMIT_CLASSIFICATIONS: frozenset[str] = frozenset({
    "current_head", "ancestor", "stale", "unknown",
})

CHECK_STATES: frozenset[str] = frozenset({
    "passing", "failing", "pending", "skipped", "infrastructure_blocked", "unavailable",
})

PR_LIFECYCLE_STATES: frozenset[str] = frozenset({"draft", "open", "closed", "merged", "unknown"})


@dataclass(frozen=True)
class Evidence:
    """A value together with the exact source that produced it. Absence
    of information is always an explicit null + a reason, never a
    fabricated default."""

    value: Optional[Any]
    source: str

    def to_dict(self) -> dict:
        return {"value": self.value, "evidence": self.source}


@dataclass(frozen=True)
class HandoffClaim:
    """One previously-reported 'final commit' claim to verify, e.g. from
    a prior merger handoff message."""

    label: str
    claimed_commit: str


@dataclass(frozen=True)
class HandoffVerification:
    claim: HandoffClaim
    classification: str            # one of COMMIT_CLASSIFICATIONS
    resolved_commit: Optional[str]  # the real, full commit sha if it exists at all, else None
    evidence: str

    def to_dict(self) -> dict:
        return {
            "label": self.claim.label,
            "claimed_commit": self.claim.claimed_commit,
            "classification": self.classification,
            "resolved_commit": self.resolved_commit,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class PRSnapshot:
    """GitHub-side facts about one PR, read from a supplied JSON
    snapshot -- never fetched by this package itself."""

    number: Optional[int] = None
    state: Optional[str] = None          # "open" | "closed" | None
    draft: Optional[bool] = None
    merged: Optional[bool] = None
    head_ref: Optional[str] = None
    head_sha: Optional[str] = None
    base_ref: Optional[str] = None
    base_sha: Optional[str] = None
    checks: dict = field(default_factory=dict)   # {check_name: {"status":..., "conclusion":..., "failure_signature":...}}
    body_final_commit_claim: Optional[str] = None  # a "Final commit: <sha>" style claim parsed out of the PR body, if any
    integrated_pr_numbers: tuple = field(default_factory=tuple)  # PR numbers this PR's own body claims to have integrated


@dataclass
class StateLockReport:
    schema: str
    target_repo_path: str
    authoritative_head: Evidence
    main_tip: Evidence
    local_worktree_tip: Evidence
    merge_base_head_and_main: Evidence
    is_head_ancestor_of_main: Evidence
    pr_number: Evidence
    pr_state: Evidence
    pr_draft: Evidence
    pr_merged: Evidence
    pr_lifecycle: Evidence
    handoff_verifications: list = field(default_factory=list)   # list[HandoffVerification]
    contradictory_handoffs: bool = False
    contradiction_detail: Optional[str] = None
    integrated_pr_history_findings: list = field(default_factory=list)  # list[dict]
    check_classifications: dict = field(default_factory=dict)   # {check_name: CHECK_STATES member}
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "target_repo_path": self.target_repo_path,
            "authoritative_head": self.authoritative_head.to_dict(),
            "main_tip": self.main_tip.to_dict(),
            "local_worktree_tip": self.local_worktree_tip.to_dict(),
            "merge_base_head_and_main": self.merge_base_head_and_main.to_dict(),
            "is_head_ancestor_of_main": self.is_head_ancestor_of_main.to_dict(),
            "pr_number": self.pr_number.to_dict(),
            "pr_state": self.pr_state.to_dict(),
            "pr_draft": self.pr_draft.to_dict(),
            "pr_merged": self.pr_merged.to_dict(),
            "pr_lifecycle": self.pr_lifecycle.to_dict(),
            "handoff_verifications": [h.to_dict() for h in self.handoff_verifications],
            "contradictory_handoffs": self.contradictory_handoffs,
            "contradiction_detail": self.contradiction_detail,
            "integrated_pr_history_findings": list(self.integrated_pr_history_findings),
            "check_classifications": dict(sorted(self.check_classifications.items())),
            "notes": list(self.notes),
        }
