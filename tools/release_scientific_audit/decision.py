"""Audit check 15: derive the release label from findings alone.

This module NEVER adjusts a scientific finding to make the release look
better -- it only reads the already-computed Finding list and applies a
fixed, documented priority order. See docs/release/scientific_release_audit.md
for the full rationale.
"""
from __future__ import annotations

from typing import List

from .models import Finding

# Checks whose blocking findings represent a scientific-integrity problem
# (as opposed to a plain engineering/CI problem). Kept as an explicit,
# named set so the priority logic below is auditable at a glance.
SCIENTIFIC_CHECK_NAMES: frozenset[str] = frozenset({
    "synthetic_vs_empirical_provenance",
    "sample_size_and_effective_n",
    "missing_provenance",
    "proxy_vs_formal_evidence",
    "k_gate_semantics",
    "null_control_presence",
    "multiple_comparison_status",
    "wilson_cowan_labeling",
    "topology_namespace_separation",
    "performance_claims",       # a mislabeled perf claim is a scientific-integrity issue, not a CI one
    "finite_numeric_fields",
    "claims_exceeding_evidence",
})

INFRASTRUCTURE_CHECK_NAMES: frozenset[str] = frozenset({
    "unresolved_failures_and_timeouts",   # only its infra/billing-blocked findings count here; see below
    "optional_dependency_availability",
})

SAFETY_CHECK_NAMES: frozenset[str] = frozenset({"dashboard_solver_isolation"})


def _is_infrastructure_only_finding(finding: Finding) -> bool:
    if finding.check != "unresolved_failures_and_timeouts":
        return finding.check in INFRASTRUCTURE_CHECK_NAMES
    text = f"{finding.summary} {finding.evidence_source}".lower()
    return "infrastructure" in text or "billing" in text


def _is_real_test_failure_finding(finding: Finding) -> bool:
    if finding.check != "unresolved_failures_and_timeouts":
        return False
    text = finding.summary.lower()
    return ("test failure" in text or "test timeout" in text or "actually failing" in text) and \
        "infrastructure" not in text and "billing" not in text


def derive_release_decision(findings: List[Finding]) -> tuple[str, tuple[str, ...]]:
    blocking = [f for f in findings if f.severity == "blocking"]
    if not blocking:
        warnings = [f for f in findings if f.severity == "warning"]
        if warnings:
            return "REVIEW_ONLY", ("WARNINGS_PRESENT_NO_BLOCKERS",)
        return "RELEASE_READY", ("ALL_CHECKS_CLEAN",)

    # Findings that exist only because a required input document was
    # absent entirely ("we don't know") are evaluated separately from
    # genuine, evidenced problems ("we know, and it's bad") -- a release
    # with real evidence of a science/test/infra problem is reported as
    # such even if OTHER inputs are also missing; a release with ONLY
    # missing-input findings and no genuine problem anywhere is
    # INCONCLUSIVE, never quietly RELEASE_READY.
    genuine_blocking = [f for f in blocking if not f.insufficient_data]
    insufficient_only = [f for f in blocking if f.insufficient_data]

    if not genuine_blocking:
        return "INCONCLUSIVE", tuple(sorted({f.check.upper() for f in insufficient_only}))

    safety_blockers = [f for f in genuine_blocking if f.check in SAFETY_CHECK_NAMES]
    if safety_blockers:
        return "BLOCKED_BY_SCIENCE", tuple(sorted({"DASHBOARD_SOLVER_ISOLATION_VIOLATION"}))

    scientific_blockers = [f for f in genuine_blocking if f.check in SCIENTIFIC_CHECK_NAMES]
    if scientific_blockers:
        codes = tuple(sorted({f.check.upper() for f in scientific_blockers}))
        return "BLOCKED_BY_SCIENCE", codes

    real_test_failures = [f for f in genuine_blocking if _is_real_test_failure_finding(f)]
    if real_test_failures:
        return "BLOCKED_BY_TESTS", ("REAL_TEST_FAILURES_OR_TIMEOUTS",)

    infra_blockers = [f for f in genuine_blocking if _is_infrastructure_only_finding(f)]
    if infra_blockers:
        return "BLOCKED_BY_INFRASTRUCTURE", ("INFRASTRUCTURE_OR_BILLING_BLOCKED",)

    # Any remaining genuine blocking finding that didn't match a named
    # category above means the audit cannot confidently place the release
    # in any of the more specific buckets.
    return "INCONCLUSIVE", tuple(sorted({f.check.upper() for f in genuine_blocking}))
