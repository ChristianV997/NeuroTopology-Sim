"""Typed structures for the reconciliation report.

Every leaf value that can be genuinely unknown is wrapped as an
``Evidence`` pair (value + where it came from) rather than a bare
optional, so the strict-JSON output (requirement 10) can always show
*why* a field is null instead of just that it is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# The six states requirement 7 asks the tool to distinguish, in the order
# they become true for a healthy work order. A later stage being true does
# not imply an earlier one was checked this run -- each is independently
# evidenced.
STAGES: tuple[str, ...] = (
    "reported",
    "branch_present",
    "pr_present",
    "checks_passing",
    "mergeable",
    "merged",
)


@dataclass(frozen=True)
class Evidence:
    """A value together with the exact source that produced it. ``value``
    is ``None`` when the field could not be determined -- ``source`` still
    says why (e.g. "no github snapshot supplied" vs "branch does not
    exist locally")."""

    value: Optional[Any]
    source: str

    def to_dict(self) -> dict:
        return {"value": self.value, "evidence": self.source}


@dataclass(frozen=True)
class WorkOrder:
    """One expected piece of work this reconciliation tracks."""

    work_order_id: str
    description: str
    expected_branch: Optional[str] = None
    reported_pr_number: Optional[int] = None
    reported_status_note: str = ""


@dataclass(frozen=True)
class BranchFacts:
    exists: Evidence
    commit_sha: Evidence
    merge_base_with_target: Evidence
    is_ancestor_of_target: Evidence  # already merged into the target branch
    commits_ahead_of_merge_base: Evidence
    changed_files: Evidence  # Evidence wrapping a tuple[str, ...] or None


@dataclass(frozen=True)
class PRFacts:
    number: Evidence
    state: Evidence
    draft: Evidence
    merged: Evidence
    mergeable_state: Evidence
    head_sha: Evidence
    base_sha: Evidence
    checks: Evidence  # Evidence wrapping dict[str, str] (name -> conclusion) or None
    head_ref: Evidence = field(default_factory=lambda: Evidence(None, "not populated"))
    base_ref: Evidence = field(default_factory=lambda: Evidence(None, "not populated"))
    body_excerpt: Evidence = field(default_factory=lambda: Evidence(None, "not populated"))


@dataclass(frozen=True)
class CurrentStatus:
    """Requirement-2 status fields, each an Evidence pair like everything
    else in this report."""

    lifecycle_state: Evidence   # "draft" | "open" | "closed" | "merged" | None
    checks_status: Evidence    # "passing" | "failing" | "pending" | "not_run" | "mixed" | "infrastructure_blocked" | "billing_blocked" | None
    mergeability: Evidence     # "mergeable" | "conflicting" | "unknown"
    billing_blocked: Evidence  # bool
    superseded: Evidence       # bool
    duplicate: Evidence        # bool
    scientific_review_required: Evidence  # bool

    def to_dict(self) -> dict:
        return {
            "lifecycle_state": self.lifecycle_state.to_dict(),
            "checks_status": self.checks_status.to_dict(),
            "mergeability": self.mergeability.to_dict(),
            "billing_blocked": self.billing_blocked.to_dict(),
            "superseded": self.superseded.to_dict(),
            "duplicate": self.duplicate.to_dict(),
            "scientific_review_required": self.scientific_review_required.to_dict(),
        }


@dataclass(frozen=True)
class StackInfo:
    is_stacked: Evidence
    base_work_order_id: Evidence
    dependents: Evidence  # tuple[str, ...] of work_order_ids stacked on this one

    def to_dict(self) -> dict:
        return {
            "is_stacked": self.is_stacked.to_dict(),
            "base_work_order_id": self.base_work_order_id.to_dict(),
            "dependents": self.dependents.to_dict(),
        }


@dataclass
class ReconciliationEntry:
    work_order: WorkOrder
    branch: BranchFacts
    pr: PRFacts
    stages: dict[str, Evidence] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    current_status: Optional[CurrentStatus] = None
    stack: Optional[StackInfo] = None
    scientific_gate_hints: Optional[dict] = None
    effective_changed_files: Optional[Evidence] = None

    def to_dict(self) -> dict:
        result = {
            "work_order_id": self.work_order.work_order_id,
            "description": self.work_order.description,
            "expected_branch": self.work_order.expected_branch,
            "reported_pr_number": self.work_order.reported_pr_number,
            "reported_status_note": self.work_order.reported_status_note or None,
            "branch": {
                "exists": self.branch.exists.to_dict(),
                "commit_sha": self.branch.commit_sha.to_dict(),
                "merge_base_with_target": self.branch.merge_base_with_target.to_dict(),
                "is_ancestor_of_target": self.branch.is_ancestor_of_target.to_dict(),
                "commits_ahead_of_merge_base": self.branch.commits_ahead_of_merge_base.to_dict(),
                "changed_files": self.branch.changed_files.to_dict(),
            },
            "pr": {
                "number": self.pr.number.to_dict(),
                "state": self.pr.state.to_dict(),
                "draft": self.pr.draft.to_dict(),
                "merged": self.pr.merged.to_dict(),
                "mergeable_state": self.pr.mergeable_state.to_dict(),
                "head_sha": self.pr.head_sha.to_dict(),
                "base_sha": self.pr.base_sha.to_dict(),
                "checks": self.pr.checks.to_dict(),
                "head_ref": self.pr.head_ref.to_dict(),
                "base_ref": self.pr.base_ref.to_dict(),
                "body_excerpt": self.pr.body_excerpt.to_dict(),
            },
            "stages": {name: evidence.to_dict() for name, evidence in self.stages.items()},
            "notes": list(self.notes),
        }
        if self.current_status is not None:
            result["current_status"] = self.current_status.to_dict()
        if self.stack is not None:
            result["stack"] = self.stack.to_dict()
        if self.scientific_gate_hints is not None:
            result["scientific_gate_hints"] = self.scientific_gate_hints
        if self.effective_changed_files is not None:
            result["effective_changed_files"] = self.effective_changed_files.to_dict()
        return result


@dataclass
class ReconciliationReport:
    schema: str
    base_branch: str
    base_commit: Optional[str]
    entries: list[ReconciliationEntry] = field(default_factory=list)
    file_overlaps: dict[str, list[str]] = field(default_factory=dict)
    common_check_failures: list[dict[str, Any]] = field(default_factory=list)
    dashboard_isolation: Optional[dict] = None
    artifact_commit_findings: dict[str, list[str]] = field(default_factory=dict)
    possible_duplicates: list[dict] = field(default_factory=list)
    superseded_work: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "base_branch": self.base_branch,
            "base_commit": self.base_commit,
            "entries": [entry.to_dict() for entry in self.entries],
            "file_overlaps": {key: list(value) for key, value in sorted(self.file_overlaps.items())},
            "common_check_failures": list(self.common_check_failures),
            "possible_duplicates": list(self.possible_duplicates),
            "superseded_work": list(self.superseded_work),
            "dashboard_isolation": self.dashboard_isolation,
            "artifact_commit_findings": {
                key: list(value) for key, value in sorted(self.artifact_commit_findings.items())
            },
        }
