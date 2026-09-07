"""Typed input/output structures for the release audit.

Every input document is optional at the top level -- a missing document
means "we don't know," never "assume clean." Findings say explicitly
which document (or field within it) they're based on, so a reader can
trace every claim in the final report back to real, supplied evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

RELEASE_DECISIONS: frozenset[str] = frozenset({
    "RELEASE_READY",
    "REVIEW_ONLY",
    "INCONCLUSIVE",
    "BLOCKED_BY_TESTS",
    "BLOCKED_BY_SCIENCE",
    "BLOCKED_BY_INFRASTRUCTURE",
})

SEVERITIES: frozenset[str] = frozenset({"info", "warning", "blocking"})


@dataclass(frozen=True)
class Finding:
    """One audit observation. ``severity='blocking'`` findings are the
    only ones that can move the release decision away from RELEASE_READY;
    'warning' findings are surfaced but do not by themselves block;
    'info' findings are provenance/context only."""

    check: str          # which of the 15 audit checks this came from, e.g. "k_gate_semantics"
    severity: str        # "info" | "warning" | "blocking"
    summary: str
    evidence_source: str  # which input document/field this is based on
    detail: Optional[str] = None
    insufficient_data: bool = False  # True: this finding exists because a
    # required input document/field was absent entirely, not because a
    # concrete problem was detected in real data. Kept distinct from
    # severity so the release-decision layer can route "we don't know"
    # (-> INCONCLUSIVE) separately from "we know, and it's bad"
    # (-> BLOCKED_BY_*), without conflating the two under one 'blocking'
    # label.

    def to_dict(self) -> dict:
        return {
            "check": self.check, "severity": self.severity, "summary": self.summary,
            "evidence_source": self.evidence_source, "detail": self.detail,
            "insufficient_data": self.insufficient_data,
        }


# ---------------------------------------------------------------------------
# Input documents (all optional; a caller supplies whatever it has)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MergeMatrixEntry:
    pr_or_group: str
    decision: str          # "Integrated" | "Unmerged" | "Superseded" | "Partially integrated" | ...
    reason: str = ""


@dataclass(frozen=True)
class ScientificGateReport:
    k_gate_threshold: Optional[float] = None            # expected 100.0
    k_gate_is_only_pass_condition: Optional[bool] = None
    synthetic_can_pass: Optional[bool] = None            # must be False
    invalid_or_incomplete_provenance_can_pass: Optional[bool] = None  # must be False
    bayes_factor_evidence_kind: Optional[str] = None     # "proxy" | "formal" | None
    classical_baseline_label: Optional[str] = None       # e.g. "classical_wilson_cowan"
    classical_baseline_is_real_wilson_cowan: Optional[bool] = None
    graph_beta1_separated_from_spatial: Optional[bool] = None
    null_control_status: Optional[str] = None            # "present" | "absent" | "not_applicable" | None
    multiplicity_correction_applied: Optional[bool] = None
    multiplicity_relevant: bool = False                  # whether >1 simultaneous comparison was made
    paired_cohort_readiness: Optional[str] = None         # "NO_DATA"|"INSUFFICIENT_PAIRS"|"VALID_PAIRED_COHORT"|"MALFORMED_COHORT"|None
    overall_status_label: Optional[str] = None            # e.g. "INCONCLUSIVE / NOT RELEASE-READY" (free text, informational)


@dataclass(frozen=True)
class ProvenanceRecord:
    component: str
    source_kind: Optional[str] = None    # "synthetic" | "empirical_local" | "empirical_csv" | None
    dataset_id: Optional[str] = None
    seed: Optional[int] = None
    checksum: Optional[str] = None
    sample_size: Optional[int] = None
    effective_sample_size: Optional[int] = None


@dataclass(frozen=True)
class FalsificationPayload:
    component: str
    verdict: Optional[str] = None        # "PASS" | "NOT_SUPPORTED" | "INCONCLUSIVE" | "ERROR" | None
    bayes_factor: Optional[float] = None
    log_bayes_factor: Optional[float] = None
    threshold: Optional[float] = None
    evidence_kind: Optional[str] = None  # "proxy" | "formal" | None
    data_mode: Optional[str] = None      # "synthetic" | "empirical_local" | ...
    null_control_present: Optional[bool] = None
    effective_sample_size: Optional[int] = None
    numeric_fields: tuple = field(default_factory=tuple)  # for the non-finite-value check


@dataclass(frozen=True)
class TopologySummary:
    namespace: str            # "spatial_topology" | "graph_topology" | "scalar_chirality"
    fields: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TestSummary:
    __test__ = False  # not a pytest test class despite the name

    total_files: Optional[int] = None
    total_batches: Optional[int] = None
    passed: Optional[int] = None
    failed: Optional[int] = None
    timed_out: Optional[int] = None
    failed_ids: tuple = field(default_factory=tuple)
    timed_out_ids: tuple = field(default_factory=tuple)
    skipped_ids: tuple = field(default_factory=tuple)
    skip_reasons: dict = field(default_factory=dict)  # {test_id: reason}


@dataclass(frozen=True)
class CIStatusReport:
    checks: dict = field(default_factory=dict)  # {check_name: "passing"|"failing"|"pending"|"not_run"|"infrastructure_blocked"|"billing_blocked"}


@dataclass(frozen=True)
class CapabilitySnapshot:
    capabilities: dict = field(default_factory=dict)   # {package_name: bool}
    required_for_release: tuple = field(default_factory=tuple)  # packages the release claims to exercise


@dataclass(frozen=True)
class PerformanceClaim:
    label: str
    metric: str          # e.g. "peak_memory_MB", "speedup_ratio"
    value: Optional[float] = None
    baseline_value: Optional[float] = None
    is_finite: Optional[bool] = None
    described_as_scientific_evidence: bool = False  # a perf claim must never be dressed up as one


@dataclass(frozen=True)
class DashboardIsolationInput:
    """Optional externally-supplied claim (e.g. "Dashboard/API solver
    isolation passed") -- this audit independently re-verifies via a
    static scan (dashboard_isolation.py) rather than trusting this field
    alone; both are reported so a divergence between claim and
    verification is itself a finding."""
    claimed_ok: Optional[bool] = None
    claim_source: str = ""


@dataclass(frozen=True)
class AuditInput:
    merge_matrix: tuple = field(default_factory=tuple)               # tuple[MergeMatrixEntry, ...]
    scientific_gate_report: Optional[ScientificGateReport] = None
    provenance_records: tuple = field(default_factory=tuple)          # tuple[ProvenanceRecord, ...]
    falsification_payloads: tuple = field(default_factory=tuple)      # tuple[FalsificationPayload, ...]
    topology_summaries: tuple = field(default_factory=tuple)          # tuple[TopologySummary, ...]
    capability_snapshot: Optional[CapabilitySnapshot] = None
    test_summary: Optional[TestSummary] = None
    ci_status: Optional[CIStatusReport] = None
    performance_claims: tuple = field(default_factory=tuple)          # tuple[PerformanceClaim, ...]
    dashboard_isolation_claim: Optional[DashboardIsolationInput] = None
    dashboard_src_path: Optional[str] = None  # if set, this audit independently scans it


@dataclass
class AuditReport:
    schema: str
    findings: list = field(default_factory=list)   # list[Finding]
    release_decision: str = "INCONCLUSIVE"
    decision_reason_codes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "release_decision": self.release_decision,
            "decision_reason_codes": list(self.decision_reason_codes),
            "findings": [f.to_dict() for f in self.findings],
        }
