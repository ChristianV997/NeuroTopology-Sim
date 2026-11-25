"""Orchestration: run every audit check over an AuditInput and derive the
release decision. Read-only, network-free, deterministic."""
from __future__ import annotations

from . import claims_checks, dashboard_isolation, decision, engineering_checks, evidence_checks, provenance_checks, topology_checks
from .models import AuditInput, AuditReport, Finding

REPORT_SCHEMA = "NTS.ReleaseScientificAuditReport.v1"


def run_audit(audit_input: AuditInput) -> AuditReport:
    findings: list[Finding] = []

    findings.extend(provenance_checks.check_synthetic_vs_empirical_provenance(audit_input.provenance_records))
    findings.extend(provenance_checks.check_sample_size_and_effective_n(audit_input.provenance_records))
    findings.extend(provenance_checks.check_missing_provenance(audit_input.provenance_records))

    findings.extend(evidence_checks.check_proxy_vs_formal_evidence(
        audit_input.falsification_payloads, audit_input.scientific_gate_report))
    findings.extend(evidence_checks.check_k_gate_semantics(
        audit_input.falsification_payloads, audit_input.scientific_gate_report))
    findings.extend(evidence_checks.check_null_control_presence(
        audit_input.falsification_payloads, audit_input.scientific_gate_report))
    findings.extend(evidence_checks.check_multiple_comparison_status(audit_input.scientific_gate_report))
    findings.extend(evidence_checks.check_wilson_cowan_labeling(audit_input.scientific_gate_report))
    findings.extend(evidence_checks.check_finite_numeric_fields(audit_input.falsification_payloads))

    findings.extend(topology_checks.check_topology_namespace_separation(audit_input.topology_summaries))

    findings.extend(dashboard_isolation.check_dashboard_solver_isolation(
        audit_input.dashboard_src_path, audit_input.dashboard_isolation_claim))

    findings.extend(engineering_checks.check_performance_claims(audit_input.performance_claims))
    findings.extend(engineering_checks.check_optional_dependency_availability(audit_input.capability_snapshot))
    findings.extend(engineering_checks.check_unresolved_failures_and_timeouts(
        audit_input.test_summary, audit_input.ci_status))

    findings.extend(claims_checks.check_claims_exceeding_evidence(
        audit_input.merge_matrix, audit_input.scientific_gate_report, findings))

    release_decision, reason_codes = decision.derive_release_decision(findings)

    return AuditReport(
        schema=REPORT_SCHEMA, findings=findings,
        release_decision=release_decision, decision_reason_codes=reason_codes,
    )
