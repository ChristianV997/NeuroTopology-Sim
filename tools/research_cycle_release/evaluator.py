"""Evaluate research-cycle release evidence (operational completeness only)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from tools.research_cycle_release.adapters import adapt_payload, source_payload_checksum
from tools.research_cycle_release.checks import decide_from_checks, run_checks
from tools.research_cycle_release.normalize import normalize_bundle
from tools.research_cycle_release.schema import (
    DEFAULT_LIMITATIONS,
    EVIDENCE_CLASS,
    SCHEMA_VERSION,
    DecisionState,
    ReleaseEvidenceReport,
)


def evaluate_research_cycle_release(
    payload: Dict[str, Any],
    *,
    adapter_hint: Optional[str] = None,
) -> ReleaseEvidenceReport:
    """Evaluate Batch 1 JSON for operational review readiness.

    Never emits scientific PASS or a Bayes factor. Missing values stay unknown.
    """
    if adapter_hint == "generic":
        from tools.research_cycle_release.adapters import adapt_generic_bundle

        bundle_raw, adapter = adapt_generic_bundle(payload)
    elif adapter_hint == "awareness":
        from tools.research_cycle_release.adapters import adapt_awareness_compiler_report

        bundle_raw, adapter = adapt_awareness_compiler_report(payload)
    elif adapter_hint == "registry":
        from tools.research_cycle_release.adapters import adapt_registry_export

        bundle_raw, adapter = adapt_registry_export(payload)
    else:
        bundle_raw, adapter = adapt_payload(payload)

    bundle = normalize_bundle(bundle_raw)
    checks = run_checks(bundle)
    decision, reason_codes, reasons = decide_from_checks(bundle, checks)

    advisories = [
        "Hardware-dependent metrics remain advisory unless comparability is proven.",
        "EVIDENCE_READY_FOR_REVIEW is not scientific PASS.",
    ]
    if bundle.get("comparability_notes"):
        advisories.extend(str(n) for n in bundle["comparability_notes"])

    if decision not in DecisionState:
        raise RuntimeError("invalid decision state")

    return ReleaseEvidenceReport(
        schema_version=SCHEMA_VERSION,
        decision=decision,
        cycle_id=bundle.get("cycle_id"),
        evidence_class=EVIDENCE_CLASS,
        synthetic_flag=bundle.get("synthetic_only"),
        proxy_flag=bundle.get("proxy_only"),
        empirical_flag=bundle.get("empirical_present"),
        reason_codes=reason_codes,
        reasons=reasons,
        checks=checks,
        advisories=advisories,
        limitations=list(DEFAULT_LIMITATIONS),
        source_adapter=adapter,
        source_checksum=source_payload_checksum(payload),
        bundle=bundle,
    )
