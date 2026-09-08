"""Scientific-gate evaluation: distinguishes a genuinely evidenced
scientific-review block from one caused merely by absent/insufficient
input data (the lesson carried over from tools/release_scientific_audit
and governance/merge_gate -- reused conceptually, not imported).

A "claims exceed evidence" style mismatch (e.g. a PR claiming a PASS
verdict on synthetic data with no bayes_factor/evidence_kind attached)
is reported as a warning-severity finding only -- it must never, by
itself, override a more specific and already-evidenced merge_state
category (a lesson from a real bug in an earlier round of this session:
an optimistic-label check that was allowed "blocking" severity
reclassified unrelated CI failures into the wrong top-level bucket).
"""
from __future__ import annotations

from typing import Optional

from .models import Evidence, ScientificGateInput


def evaluate_scientific_gate(gate_input: Optional[ScientificGateInput]) -> tuple:
    """Return ``(Evidence(status, source), blocking: bool, findings: list[str])``.

    status is one of: "not_applicable", "insufficient_data", "pass",
    "blocked". Only a genuinely evidenced negative verdict on non-synthetic
    (or explicitly claim-bearing) data produces ``blocking=True`` --
    missing input data alone produces "insufficient_data" and
    ``blocking=False`` (routes to merge_state "unknown"/"open_unintegrated"
    territory rather than a false "blocked_by_scientific_review").
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
        if gate_input.data_mode in ("synthetic", "synthetic_demo") and gate_input.evidence_kind != "formal":
            findings.append(
                "claims_exceeding_evidence: PASS verdict recorded on "
                f"data_mode={gate_input.data_mode!r} without formal evidence_kind "
                "(warning only -- does not override merge_state)"
            )
        return Evidence("pass", f"verdict=PASS (data_mode={gate_input.data_mode!r})"), False, findings

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
