"""ReleaseCandidateManifest.v1 schema and supporting types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = "ReleaseCandidateManifest.v1"

MERGE_STATES: frozenset[str] = frozenset({
    "merged_into_main",
    "integration_only",
    "open_unintegrated",
    "ancestor_stale",
    "superseded",
    "duplicate",
    "blocked_by_dependency",
    "blocked_by_ci",
    "blocked_by_infrastructure",
    "blocked_by_scientific_review",
    "unknown",
})

CHECK_STATES: frozenset[str] = frozenset({
    "passing", "failing", "pending", "skipped", "infrastructure_blocked", "unavailable",
})

COMMIT_CLASSIFICATIONS: frozenset[str] = frozenset({"current_head", "ancestor", "stale", "unknown"})

GITHUB_STATE_VALUES: frozenset[str] = frozenset({"available", "unavailable"})


@dataclass(frozen=True)
class Evidence:
    """A value together with the exact source that produced it -- never
    a fabricated default; absence is always an explicit null + a
    reason."""

    value: Optional[Any]
    source: str

    def to_dict(self) -> dict:
        return {"value": self.value, "evidence": self.source}


@dataclass(frozen=True)
class PRSnapshot:
    """GitHub-side facts, read from an optional pre-fetched JSON
    snapshot -- never fetched by this package itself."""

    number: Optional[int] = None
    state: Optional[str] = None
    draft: Optional[bool] = None
    merged: Optional[bool] = None
    head_sha: Optional[str] = None
    base_ref: Optional[str] = None
    checks: dict = field(default_factory=dict)
    body: Optional[str] = None


@dataclass(frozen=True)
class ScientificGateInput:
    data_mode: Optional[str] = None      # "synthetic" | "synthetic_demo" | "empirical_local" | ...
    verdict: Optional[str] = None        # "PASS" | "NOT_SUPPORTED" | "INCONCLUSIVE" | "ERROR" | None
    bayes_factor: Optional[float] = None
    evidence_kind: Optional[str] = None  # "proxy" | "formal" | None


@dataclass(frozen=True)
class ChangedFileOwnership:
    """One work order's changed-file set, for duplicate-ownership
    detection across parallel branches."""

    label: str
    changed_files: tuple = field(default_factory=tuple)


@dataclass
class ReleaseCandidateManifest:
    schema: str = SCHEMA_VERSION
    repository: str = ""
    target_branch: str = ""
    integration_branch: str = ""
    source_commit: Optional[str] = None
    verified_head_commit: Evidence = field(default_factory=lambda: Evidence(None, "not computed"))
    pr_number: Evidence = field(default_factory=lambda: Evidence(None, "not computed"))
    pr_status: Evidence = field(default_factory=lambda: Evidence(None, "not computed"))
    draft_status: Evidence = field(default_factory=lambda: Evidence(None, "not computed"))
    branch_ancestry: dict = field(default_factory=dict)
    changed_file_ownership: dict = field(default_factory=dict)   # {label: [files...]}
    duplicate_file_findings: list = field(default_factory=list)
    ci_classifications: dict = field(default_factory=dict)
    test_summary: Optional[dict] = None
    governance_status: Evidence = field(default_factory=lambda: Evidence(None, "not computed"))
    scientific_gate_status: Evidence = field(default_factory=lambda: Evidence(None, "not computed"))
    dashboard_isolation_status: Evidence = field(default_factory=lambda: Evidence(None, "not computed"))
    memory_timeout_status: Evidence = field(default_factory=lambda: Evidence(None, "not computed"))
    merge_state: str = "unknown"
    merge_eligibility: bool = False
    blockers: list = field(default_factory=list)
    github_state: str = "unavailable"
    provenance: dict = field(default_factory=dict)
    generated_at: Optional[str] = None   # only populated when explicitly requested

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "repository": self.repository,
            "target_branch": self.target_branch,
            "integration_branch": self.integration_branch,
            "source_commit": self.source_commit,
            "verified_head_commit": self.verified_head_commit.to_dict(),
            "pr_number": self.pr_number.to_dict(),
            "pr_status": self.pr_status.to_dict(),
            "draft_status": self.draft_status.to_dict(),
            "branch_ancestry": self.branch_ancestry,
            "changed_file_ownership": self.changed_file_ownership,
            "duplicate_file_findings": self.duplicate_file_findings,
            "ci_classifications": dict(sorted(self.ci_classifications.items())),
            "test_summary": self.test_summary,
            "governance_status": self.governance_status.to_dict(),
            "scientific_gate_status": self.scientific_gate_status.to_dict(),
            "dashboard_isolation_status": self.dashboard_isolation_status.to_dict(),
            "memory_timeout_status": self.memory_timeout_status.to_dict(),
            "merge_state": self.merge_state,
            "merge_eligibility": self.merge_eligibility,
            "blockers": list(self.blockers),
            "github_state": self.github_state,
            "provenance": self.provenance,
            "generated_at": self.generated_at,
        }
