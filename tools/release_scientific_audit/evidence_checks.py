"""Audit checks 2, 3, 4, 6, 7: proxy-vs-formal evidence, K>100 gate
semantics, null-control presence, multiple-comparison status, and
Wilson-Cowan model labeling."""
from __future__ import annotations

import math
from typing import List

from .models import FalsificationPayload, Finding, ScientificGateReport

_EXPECTED_K_THRESHOLD = 100.0


def check_finite_numeric_fields(payloads: tuple) -> List[Finding]:
    """A non-finite (NaN/inf) value anywhere in a falsification payload's
    reported numeric fields means the packaged report itself is broken --
    this is caught here rather than left for a human to notice a stray
    'NaN' in a report."""
    findings: List[Finding] = []
    for payload in payloads:
        payload: FalsificationPayload
        non_finite = [value for value in payload.numeric_fields if not math.isfinite(value)]
        if non_finite:
            findings.append(Finding(
                "finite_numeric_fields", "blocking",
                f"{payload.component}: {len(non_finite)} non-finite numeric field value(s) reported",
                f"falsification_payloads[{payload.component}].numeric_fields",
            ))
    return findings


def check_proxy_vs_formal_evidence(
    payloads: tuple, gate_report: ScientificGateReport | None
) -> List[Finding]:
    """Check 2: a PASS verdict resting on proxy (RSS/AICc/BIC-derived)
    evidence must never be reported or treated as formal marginal-
    likelihood evidence."""
    findings: List[Finding] = []
    for payload in payloads:
        payload: FalsificationPayload
        if payload.evidence_kind is None:
            findings.append(Finding(
                "proxy_vs_formal_evidence", "warning",
                f"{payload.component}: no evidence_kind declared for its Bayes-factor-style statistic",
                f"falsification_payloads[{payload.component}].evidence_kind",
            ))
            continue
        if payload.evidence_kind == "proxy" and payload.verdict == "PASS":
            findings.append(Finding(
                "proxy_vs_formal_evidence", "blocking",
                f"{payload.component}: verdict=PASS resting on proxy evidence -- proxy evidence "
                "cannot itself constitute a release-grade empirical PASS claim",
                f"falsification_payloads[{payload.component}]",
            ))
        else:
            findings.append(Finding(
                "proxy_vs_formal_evidence", "info",
                f"{payload.component}: evidence_kind={payload.evidence_kind!r}, verdict={payload.verdict!r}",
                f"falsification_payloads[{payload.component}]",
            ))
    if gate_report is not None and gate_report.bayes_factor_evidence_kind == "proxy":
        findings.append(Finding(
            "proxy_vs_formal_evidence", "info",
            "scientific-gate report declares the Bayes-factor statistic as proxy evidence",
            "scientific_gate_report.bayes_factor_evidence_kind",
        ))
    return findings


def check_k_gate_semantics(
    payloads: tuple, gate_report: ScientificGateReport | None
) -> List[Finding]:
    """Check 3: K > 100 must remain the *only* empirical PASS condition,
    at exactly threshold 100.0 -- not a lowered, raised, or per-payload
    threshold, and never satisfied by a non-finite or missing bayes_factor."""
    findings: List[Finding] = []
    if gate_report is not None:
        if gate_report.k_gate_threshold is not None and gate_report.k_gate_threshold != _EXPECTED_K_THRESHOLD:
            findings.append(Finding(
                "k_gate_semantics", "blocking",
                f"declared K-gate threshold is {gate_report.k_gate_threshold}, not the expected {_EXPECTED_K_THRESHOLD}",
                "scientific_gate_report.k_gate_threshold",
            ))
        if gate_report.k_gate_is_only_pass_condition is False:
            findings.append(Finding(
                "k_gate_semantics", "blocking",
                "scientific-gate report states K>100 is NOT the only empirical PASS condition",
                "scientific_gate_report.k_gate_is_only_pass_condition",
            ))
        if gate_report.synthetic_can_pass is True:
            findings.append(Finding(
                "k_gate_semantics", "blocking",
                "scientific-gate report states synthetic data CAN produce PASS",
                "scientific_gate_report.synthetic_can_pass",
            ))
        if gate_report.invalid_or_incomplete_provenance_can_pass is True:
            findings.append(Finding(
                "k_gate_semantics", "blocking",
                "scientific-gate report states invalid/incomplete-provenance data CAN produce PASS",
                "scientific_gate_report.invalid_or_incomplete_provenance_can_pass",
            ))
    for payload in payloads:
        payload: FalsificationPayload
        if payload.verdict != "PASS":
            continue
        if payload.bayes_factor is None:
            findings.append(Finding(
                "k_gate_semantics", "blocking",
                f"{payload.component}: verdict=PASS with no bayes_factor recorded at all",
                f"falsification_payloads[{payload.component}].bayes_factor",
            ))
            continue
        import math
        if not math.isfinite(payload.bayes_factor):
            findings.append(Finding(
                "k_gate_semantics", "blocking",
                f"{payload.component}: verdict=PASS with a non-finite bayes_factor ({payload.bayes_factor})",
                f"falsification_payloads[{payload.component}].bayes_factor",
            ))
        elif payload.bayes_factor <= _EXPECTED_K_THRESHOLD:
            findings.append(Finding(
                "k_gate_semantics", "blocking",
                f"{payload.component}: verdict=PASS but bayes_factor={payload.bayes_factor} does not "
                f"exceed the required threshold of {_EXPECTED_K_THRESHOLD}",
                f"falsification_payloads[{payload.component}]",
            ))
        if payload.data_mode in {"synthetic", "synthetic_demo"}:
            findings.append(Finding(
                "k_gate_semantics", "blocking",
                f"{payload.component}: verdict=PASS on data_mode={payload.data_mode!r} -- synthetic data "
                "must never satisfy the empirical PASS gate",
                f"falsification_payloads[{payload.component}].data_mode",
            ))
    return findings


def check_null_control_presence(
    payloads: tuple, gate_report: ScientificGateReport | None
) -> List[Finding]:
    """Check 4: a PASS or otherwise significant-sounding verdict without a
    recorded null control is a real gap, not a clean result."""
    findings: List[Finding] = []
    for payload in payloads:
        payload: FalsificationPayload
        if payload.verdict == "PASS" and payload.null_control_present is not True:
            findings.append(Finding(
                "null_control_presence", "blocking",
                f"{payload.component}: verdict=PASS with null_control_present={payload.null_control_present!r}",
                f"falsification_payloads[{payload.component}].null_control_present",
            ))
    if gate_report is not None and gate_report.null_control_status == "absent":
        findings.append(Finding(
            "null_control_presence", "warning",
            "scientific-gate report declares null-control status as 'absent'",
            "scientific_gate_report.null_control_status",
        ))
    return findings


def check_multiple_comparison_status(gate_report: ScientificGateReport | None) -> List[Finding]:
    """Check 6: when more than one simultaneous comparison was made,
    multiplicity correction must be explicitly recorded as applied."""
    if gate_report is None:
        return [Finding(
            "multiple_comparison_status", "warning",
            "no scientific-gate report supplied -- multiplicity status unknown",
            "scientific_gate_report (absent)",
        )]
    if not gate_report.multiplicity_relevant:
        return [Finding(
            "multiple_comparison_status", "info",
            "multiplicity correction not applicable (single comparison)",
            "scientific_gate_report.multiplicity_relevant",
        )]
    if gate_report.multiplicity_correction_applied is not True:
        return [Finding(
            "multiple_comparison_status", "blocking",
            "multiple simultaneous comparisons were made but multiplicity_correction_applied is not True",
            "scientific_gate_report.multiplicity_correction_applied",
        )]
    return [Finding(
        "multiple_comparison_status", "info",
        "multiplicity correction applied for a multi-comparison run",
        "scientific_gate_report.multiplicity_correction_applied",
    )]


def check_wilson_cowan_labeling(gate_report: ScientificGateReport | None) -> List[Finding]:
    """Check 7: a baseline literally labeled 'classical_wilson_cowan' (or
    similar) must not be silently presented as the real Wilson-Cowan
    neural-mass model unless independently confirmed to implement it."""
    if gate_report is None or gate_report.classical_baseline_label is None:
        return [Finding(
            "wilson_cowan_labeling", "warning",
            "no classical-baseline label information supplied",
            "scientific_gate_report.classical_baseline_label (absent)",
        )]
    label = gate_report.classical_baseline_label
    if "wilson" in label.lower() and "cowan" in label.lower():
        if gate_report.classical_baseline_is_real_wilson_cowan is True:
            return [Finding(
                "wilson_cowan_labeling", "info",
                f"baseline {label!r} confirmed to implement the real Wilson-Cowan model",
                "scientific_gate_report.classical_baseline_is_real_wilson_cowan",
            )]
        return [Finding(
            "wilson_cowan_labeling", "blocking",
            f"baseline is labeled {label!r} (implying the Wilson-Cowan neural-mass model) but is not "
            "confirmed to actually implement it -- any claim naming Wilson-Cowan must be downgraded",
            "scientific_gate_report.classical_baseline_is_real_wilson_cowan",
        )]
    return [Finding(
        "wilson_cowan_labeling", "info",
        f"classical baseline labeled {label!r} (no Wilson-Cowan naming risk)",
        "scientific_gate_report.classical_baseline_label",
    )]
