"""Classification of failed / partial / timed-out / interrupted / malformed artifacts."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.release_readiness.batch2_security.schema import (
    REMEDIATION_OWNERS,
    Finding,
    ThreatClass,
)

INCOMPLETE_STATUSES = frozenset(
    {"FAILED", "PARTIAL", "TIMED_OUT", "TIMEOUT", "INTERRUPTED", "MALFORMED", "INCOMPLETE", "BLOCKED"}
)
COMPLETE_STATUSES = frozenset({"COMPLETE", "OK", "SUCCESS"})


def classify_artifact_state(record: Dict[str, Any]) -> str:
    """Return a normalized artifact status string."""
    status = record.get("status") or record.get("state") or record.get("artifact_status")
    if status is None:
        # Malformed when required identity fields are absent.
        if not record.get("run_id") and not record.get("artifact_id"):
            return "MALFORMED"
        return "INCOMPLETE"
    normalized = str(status).upper()
    if normalized in INCOMPLETE_STATUSES or normalized in COMPLETE_STATUSES:
        return normalized
    return "MALFORMED"


def evaluate_artifact_state(record: Dict[str, Any], *, fixture_id: str | None = None) -> List[Finding]:
    """Emit findings when incomplete artifacts claim security/scientific PASS."""
    findings: List[Finding] = []
    status = classify_artifact_state(record)
    if status in INCOMPLETE_STATUSES:
        findings.append(
            Finding(
                threat_class=ThreatClass.ARTIFACT_INCOMPLETE_STATE.value,
                severity="error",
                message=f"artifact in incomplete state: {status}",
                fixture_id=fixture_id,
                remediation_owners=list(
                    REMEDIATION_OWNERS[ThreatClass.ARTIFACT_INCOMPLETE_STATE.value]
                ),
                expected=True,
            )
        )
        if record.get("scientific_pass") is True:
            findings.append(
                Finding(
                    threat_class=ThreatClass.SYNTHETIC_TO_EMPIRICAL.value,
                    severity="critical",
                    message=f"incomplete artifact {status} must not claim scientific_pass",
                    fixture_id=fixture_id,
                    remediation_owners=list(
                        REMEDIATION_OWNERS[ThreatClass.SYNTHETIC_TO_EMPIRICAL.value]
                    ),
                    expected=True,
                )
            )
        if record.get("security_pass") is True:
            findings.append(
                Finding(
                    threat_class=ThreatClass.ARTIFACT_INCOMPLETE_STATE.value,
                    severity="critical",
                    message=f"incomplete artifact {status} must not claim security_pass",
                    fixture_id=fixture_id,
                    remediation_owners=list(
                        REMEDIATION_OWNERS[ThreatClass.ARTIFACT_INCOMPLETE_STATE.value]
                    ),
                    expected=True,
                )
            )
    return findings


def expected_incomplete(fixture_id: str) -> Optional[str]:
    mapping = {
        "artifact_failed": "FAILED",
        "artifact_partial": "PARTIAL",
        "artifact_timed_out": "TIMED_OUT",
        "artifact_interrupted": "INTERRUPTED",
        "artifact_malformed": "MALFORMED",
    }
    return mapping.get(fixture_id)
