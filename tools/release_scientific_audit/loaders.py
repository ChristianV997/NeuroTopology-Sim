"""Build an AuditInput from a single JSON document (or a dict already in
memory). Pure parsing -- no network, no execution of anything it reads."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .models import (
    AuditInput,
    CapabilitySnapshot,
    CIStatusReport,
    DashboardIsolationInput,
    FalsificationPayload,
    MergeMatrixEntry,
    PerformanceClaim,
    ProvenanceRecord,
    ScientificGateReport,
    TestSummary,
    TopologySummary,
)


def _get(d: dict, key: str, default=None):
    return d.get(key, default) if isinstance(d, dict) else default


def audit_input_from_dict(data: dict[str, Any]) -> AuditInput:
    merge_matrix = tuple(
        MergeMatrixEntry(entry["pr_or_group"], entry["decision"], entry.get("reason", ""))
        for entry in data.get("merge_matrix", [])
    )

    gate_raw = data.get("scientific_gate_report")
    gate_report: Optional[ScientificGateReport] = None
    if gate_raw is not None:
        gate_report = ScientificGateReport(
            k_gate_threshold=_get(gate_raw, "k_gate_threshold"),
            k_gate_is_only_pass_condition=_get(gate_raw, "k_gate_is_only_pass_condition"),
            synthetic_can_pass=_get(gate_raw, "synthetic_can_pass"),
            invalid_or_incomplete_provenance_can_pass=_get(gate_raw, "invalid_or_incomplete_provenance_can_pass"),
            bayes_factor_evidence_kind=_get(gate_raw, "bayes_factor_evidence_kind"),
            classical_baseline_label=_get(gate_raw, "classical_baseline_label"),
            classical_baseline_is_real_wilson_cowan=_get(gate_raw, "classical_baseline_is_real_wilson_cowan"),
            graph_beta1_separated_from_spatial=_get(gate_raw, "graph_beta1_separated_from_spatial"),
            null_control_status=_get(gate_raw, "null_control_status"),
            multiplicity_correction_applied=_get(gate_raw, "multiplicity_correction_applied"),
            multiplicity_relevant=bool(_get(gate_raw, "multiplicity_relevant", False)),
            paired_cohort_readiness=_get(gate_raw, "paired_cohort_readiness"),
            overall_status_label=_get(gate_raw, "overall_status_label"),
        )

    provenance_records = tuple(
        ProvenanceRecord(
            component=record["component"], source_kind=record.get("source_kind"),
            dataset_id=record.get("dataset_id"), seed=record.get("seed"),
            checksum=record.get("checksum"), sample_size=record.get("sample_size"),
            effective_sample_size=record.get("effective_sample_size"),
        )
        for record in data.get("provenance_records", [])
    )

    falsification_payloads = tuple(
        FalsificationPayload(
            component=payload["component"], verdict=payload.get("verdict"),
            bayes_factor=payload.get("bayes_factor"), log_bayes_factor=payload.get("log_bayes_factor"),
            threshold=payload.get("threshold"), evidence_kind=payload.get("evidence_kind"),
            data_mode=payload.get("data_mode"), null_control_present=payload.get("null_control_present"),
            effective_sample_size=payload.get("effective_sample_size"),
            numeric_fields=tuple(payload.get("numeric_fields", [])),
        )
        for payload in data.get("falsification_payloads", [])
    )

    topology_summaries = tuple(
        TopologySummary(namespace=summary["namespace"], fields=summary.get("fields", {}))
        for summary in data.get("topology_summaries", [])
    )

    capability_raw = data.get("capability_snapshot")
    capability_snapshot: Optional[CapabilitySnapshot] = None
    if capability_raw is not None:
        capability_snapshot = CapabilitySnapshot(
            capabilities=capability_raw.get("capabilities", {}),
            required_for_release=tuple(capability_raw.get("required_for_release", [])),
        )

    test_raw = data.get("test_summary")
    test_summary: Optional[TestSummary] = None
    if test_raw is not None:
        test_summary = TestSummary(
            total_files=test_raw.get("total_files"), total_batches=test_raw.get("total_batches"),
            passed=test_raw.get("passed"), failed=test_raw.get("failed"), timed_out=test_raw.get("timed_out"),
            failed_ids=tuple(test_raw.get("failed_ids", [])), timed_out_ids=tuple(test_raw.get("timed_out_ids", [])),
            skipped_ids=tuple(test_raw.get("skipped_ids", [])), skip_reasons=test_raw.get("skip_reasons", {}),
        )

    ci_raw = data.get("ci_status")
    ci_status: Optional[CIStatusReport] = None
    if ci_raw is not None:
        ci_status = CIStatusReport(checks=ci_raw.get("checks", {}))

    performance_claims = tuple(
        PerformanceClaim(
            label=claim["label"], metric=claim["metric"], value=claim.get("value"),
            baseline_value=claim.get("baseline_value"), is_finite=claim.get("is_finite"),
            described_as_scientific_evidence=bool(claim.get("described_as_scientific_evidence", False)),
        )
        for claim in data.get("performance_claims", [])
    )

    dashboard_claim_raw = data.get("dashboard_isolation_claim")
    dashboard_claim: Optional[DashboardIsolationInput] = None
    if dashboard_claim_raw is not None:
        dashboard_claim = DashboardIsolationInput(
            claimed_ok=dashboard_claim_raw.get("claimed_ok"),
            claim_source=dashboard_claim_raw.get("claim_source", ""),
        )

    return AuditInput(
        merge_matrix=merge_matrix, scientific_gate_report=gate_report,
        provenance_records=provenance_records, falsification_payloads=falsification_payloads,
        topology_summaries=topology_summaries, capability_snapshot=capability_snapshot,
        test_summary=test_summary, ci_status=ci_status, performance_claims=performance_claims,
        dashboard_isolation_claim=dashboard_claim, dashboard_src_path=data.get("dashboard_src_path"),
    )


def audit_input_from_file(path: Path) -> AuditInput:
    return audit_input_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
