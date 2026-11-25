"""Scientific-gate evaluation: distinguishes a genuinely evidenced
scientific-review block from one caused merely by absent/insufficient
input data (the lesson carried over from tools/release_scientific_audit
and governance/merge_gate -- reused conceptually, not imported).

A caller-supplied PASS is not scientific evidence.  This module receives
release metadata and a pre-fetched snapshot; it does not independently
verify the data, labels, provenance, likelihood construction, nulls, or
controls.  It therefore fails closed for every supplied PASS rather than
allowing a literal verdict to promote an unverified result.
"""
from __future__ import annotations

from typing import Optional

from .models import Evidence, ScientificGateInput


def evaluate_scientific_gate(gate_input: Optional[ScientificGateInput]) -> tuple:
    """Return ``(Evidence(status, source), blocking: bool, findings: list[str])``.

    status is one of: "not_applicable", "insufficient_data", "pass",
    "blocked".  ``pass`` is never emitted from this metadata-only boundary:
    a literal PASS is not independently verified evidence.
    """
    findings: list[str] = []

    if gate_input is None:
        return (
            Evidence("insufficient_data", "no scientific gate input supplied"),
            False,
            findings,
        )

    if gate_input.verdict is None:
        return (
            Evidence("insufficient_data", "no verdict recorded in scientific gate input"),
            False,
            findings,
        )

    if gate_input.verdict == "PASS":
        findings.append(
            "unverified_scientific_pass: caller-supplied PASS cannot be promoted "
            "without an independently validated evidence artifact"
        )
        return (
            Evidence("blocked", "caller-supplied PASS is not independently verifiable"),
            True,
            findings,
        )

    if gate_input.verdict in ("NOT_SUPPORTED", "ERROR"):
        return (
            Evidence("blocked", f"verdict={gate_input.verdict!r} (data_mode={gate_input.data_mode!r})"),
            True,
            findings,
        )

    if gate_input.verdict == "INCONCLUSIVE":
        return (
            Evidence("insufficient_data", f"verdict=INCONCLUSIVE (data_mode={gate_input.data_mode!r})"),
            False,
            findings,
        )

    return Evidence("insufficient_data", f"unrecognized verdict={gate_input.verdict!r}"), False, findings
