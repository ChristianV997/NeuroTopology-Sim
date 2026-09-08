"""Audit check 13: claims that exceed the actual evidence.

Cross-cutting: compares free-text/summary claims (merge-matrix reasons,
the scientific-gate report's own overall_status_label) against the
concrete findings the other checks already produced, and flags a claim
that reads more confidently than the underlying evidence supports.
"""
from __future__ import annotations

from typing import List

from .models import Finding, MergeMatrixEntry, ScientificGateReport

_OPTIMISTIC_MERGE_WORDS: tuple[str, ...] = ("validated", "verified", "confirmed", "passed", "clean")
_CAUTIONARY_STATUS_WORDS: tuple[str, ...] = (
    "inconclusive", "not release-ready", "not release ready", "hold", "blocked", "unresolved",
)


def check_claims_exceeding_evidence(
    merge_matrix: tuple,
    gate_report: ScientificGateReport | None,
    prior_findings: List[Finding],
) -> List[Finding]:
    findings: List[Finding] = []

    blocking_count = sum(1 for finding in prior_findings if finding.severity == "blocking")

    if gate_report is not None and gate_report.overall_status_label:
        label_lower = gate_report.overall_status_label.lower()
        sounds_cautionary = any(word in label_lower for word in _CAUTIONARY_STATUS_WORDS)
        if blocking_count == 0 and sounds_cautionary:
            findings.append(Finding(
                "claims_exceeding_evidence", "warning",
                f"scientific_gate_report.overall_status_label reads {gate_report.overall_status_label!r} "
                "(cautionary) but this audit found zero blocking findings elsewhere -- the label may be "
                "stale or overly conservative relative to current evidence",
                "scientific_gate_report.overall_status_label",
            ))
        if blocking_count > 0 and not sounds_cautionary:
            # This finding never itself decides the release category --
            # it only flags that a human-facing label is out of step with
            # findings that already, independently, produced a blocking
            # decision elsewhere. Kept at 'warning' so it can never
            # override the underlying finding's own category (e.g. a
            # pure CI failure staying BLOCKED_BY_TESTS rather than being
            # reclassified as BLOCKED_BY_SCIENCE just because the label
            # was optimistic).
            findings.append(Finding(
                "claims_exceeding_evidence", "warning",
                f"scientific_gate_report.overall_status_label reads {gate_report.overall_status_label!r} "
                f"but this audit found {blocking_count} blocking finding(s) elsewhere -- the label "
                "understates the actual evidence",
                "scientific_gate_report.overall_status_label",
            ))

    for entry in merge_matrix:
        entry: MergeMatrixEntry
        reason_lower = entry.reason.lower()
        if entry.decision == "Integrated" and any(word in reason_lower for word in _OPTIMISTIC_MERGE_WORDS):
            if blocking_count > 0:
                # Same rationale as above: never overrides the underlying
                # finding's own decision category.
                findings.append(Finding(
                    "claims_exceeding_evidence", "warning",
                    f"merge-matrix entry {entry.pr_or_group!r} is marked Integrated with an optimistic "
                    f"reason ({entry.reason!r}) while this audit found {blocking_count} blocking finding(s) "
                    "elsewhere in the same release",
                    f"merge_matrix[{entry.pr_or_group}].reason",
                ))
    return findings
