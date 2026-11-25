"""Audit checks 10, 11, 12: memory/performance claims, optional
dependency availability, and unresolved failures/timeouts."""
from __future__ import annotations

import math
from typing import List

from .models import CapabilitySnapshot, CIStatusReport, Finding, PerformanceClaim, TestSummary

CI_FAILURE_STATES: frozenset[str] = frozenset({"failing"})
CI_INFRASTRUCTURE_STATES: frozenset[str] = frozenset({"infrastructure_blocked", "billing_blocked"})
CI_INCOMPLETE_STATES: frozenset[str] = frozenset({"pending", "not_run"})


def check_performance_claims(claims: tuple) -> List[Finding]:
    """Check 10: a performance/memory number must be finite, and must
    never be described as scientific evidence -- a benchmark result is
    engineering evidence only."""
    findings: List[Finding] = []
    for claim in claims:
        claim: PerformanceClaim
        if claim.described_as_scientific_evidence:
            findings.append(Finding(
                "performance_claims", "blocking",
                f"{claim.label} ({claim.metric}) is described as scientific evidence -- a performance/"
                "memory benchmark is never itself scientific evidence",
                f"performance_claims[{claim.label}].described_as_scientific_evidence",
            ))
        if claim.value is not None and not math.isfinite(claim.value):
            findings.append(Finding(
                "performance_claims", "blocking",
                f"{claim.label} ({claim.metric}): non-finite value {claim.value}",
                f"performance_claims[{claim.label}].value",
            ))
        elif claim.is_finite is False:
            findings.append(Finding(
                "performance_claims", "blocking",
                f"{claim.label} ({claim.metric}): explicitly flagged non-finite",
                f"performance_claims[{claim.label}].is_finite",
            ))
    return findings


def check_optional_dependency_availability(snapshot: CapabilitySnapshot | None) -> List[Finding]:
    """Check 11: every capability the release claims to exercise must be
    explicitly classified (available/unavailable) -- an unclassified
    required capability is a real gap, not an implicit pass."""
    if snapshot is None:
        return [Finding(
            "optional_dependency_availability", "warning",
            "no capability snapshot supplied", "capability_snapshot (absent)",
        )]
    findings: List[Finding] = []
    for package in snapshot.required_for_release:
        if package not in snapshot.capabilities:
            findings.append(Finding(
                "optional_dependency_availability", "blocking",
                f"{package!r} is required for this release's claims but has no recorded availability classification",
                f"capability_snapshot.capabilities[{package}] (absent)",
            ))
        elif not snapshot.capabilities[package]:
            findings.append(Finding(
                "optional_dependency_availability", "warning",
                f"{package!r} is required for this release's claims and is explicitly unavailable "
                "in the validated environment",
                f"capability_snapshot.capabilities[{package}]",
            ))
        else:
            findings.append(Finding(
                "optional_dependency_availability", "info",
                f"{package!r} available", f"capability_snapshot.capabilities[{package}]",
            ))
    return findings


def check_unresolved_failures_and_timeouts(
    test_summary: TestSummary | None, ci_status: CIStatusReport | None
) -> List[Finding]:
    """Check 12: real (local, isolated-runner) test failures and timeouts
    are reported distinctly from CI-level infrastructure/billing blocks --
    neither is silently absorbed into the other."""
    findings: List[Finding] = []

    if test_summary is None:
        findings.append(Finding(
            "unresolved_failures_and_timeouts", "warning",
            "no test summary supplied", "test_summary (absent)",
        ))
    else:
        if test_summary.failed:
            findings.append(Finding(
                "unresolved_failures_and_timeouts", "blocking",
                f"{test_summary.failed} local test failure(s) recorded "
                f"({len(test_summary.failed_ids)} identified by id)",
                "test_summary.failed", detail=", ".join(test_summary.failed_ids) or None,
            ))
        if test_summary.timed_out:
            findings.append(Finding(
                "unresolved_failures_and_timeouts", "blocking",
                f"{test_summary.timed_out} local test timeout(s) recorded "
                f"({len(test_summary.timed_out_ids)} identified by id) -- a timeout is an unresolved "
                "execution-time blocker, not a skip",
                "test_summary.timed_out", detail=", ".join(test_summary.timed_out_ids) or None,
            ))
        if not test_summary.failed and not test_summary.timed_out:
            findings.append(Finding(
                "unresolved_failures_and_timeouts", "info",
                "no local test failures or timeouts recorded", "test_summary",
            ))

    if ci_status is None:
        findings.append(Finding(
            "unresolved_failures_and_timeouts", "warning",
            "no CI status supplied", "ci_status (absent)",
        ))
    else:
        infra_blocked = [name for name, state in ci_status.checks.items() if state in CI_INFRASTRUCTURE_STATES]
        real_failures = [name for name, state in ci_status.checks.items() if state in CI_FAILURE_STATES]
        incomplete = [name for name, state in ci_status.checks.items() if state in CI_INCOMPLETE_STATES]
        if infra_blocked:
            findings.append(Finding(
                "unresolved_failures_and_timeouts", "blocking",
                f"{len(infra_blocked)} CI check(s) infrastructure/billing-blocked: {', '.join(sorted(infra_blocked))} "
                "-- this is not CI success and not a code-level test failure",
                "ci_status.checks",
            ))
        if real_failures:
            findings.append(Finding(
                "unresolved_failures_and_timeouts", "blocking",
                f"{len(real_failures)} CI check(s) actually failing: {', '.join(sorted(real_failures))}",
                "ci_status.checks",
            ))
        if incomplete:
            findings.append(Finding(
                "unresolved_failures_and_timeouts", "warning",
                f"{len(incomplete)} CI check(s) not yet complete: {', '.join(sorted(incomplete))} -- "
                "an unstarted check is not a pass",
                "ci_status.checks",
            ))
        if not infra_blocked and not real_failures and not incomplete and ci_status.checks:
            findings.append(Finding(
                "unresolved_failures_and_timeouts", "info",
                "all recorded CI checks are passing", "ci_status.checks",
            ))
    return findings
