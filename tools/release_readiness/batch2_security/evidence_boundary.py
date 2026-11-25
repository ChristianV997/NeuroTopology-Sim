"""Evidence-boundary checks: provenance, checksums, commit identity, promotion."""
from __future__ import annotations

from typing import Any, Dict, List

from tools.release_readiness.batch2_security.schema import (
    REMEDIATION_OWNERS,
    Finding,
    ThreatClass,
)


def _owners(threat: ThreatClass) -> List[str]:
    return list(REMEDIATION_OWNERS[threat.value])


def evaluate_evidence_record(record: Dict[str, Any], *, fixture_id: str | None = None) -> List[Finding]:
    """Inspect a synthetic evidence/provenance record for boundary violations.

    This is harness-local policy (does not modify production claim-gate code).
    """
    findings: List[Finding] = []
    provenance = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
    evidence_class = str(record.get("evidence_class") or provenance.get("evidence_class") or "")
    synthetic = bool(record.get("synthetic", provenance.get("synthetic", False)))
    presented_as = str(record.get("presented_as") or record.get("claim_mode") or "")

    checksum = provenance.get("checksum") or provenance.get("sha256") or record.get("checksum")
    if not checksum:
        findings.append(
            Finding(
                threat_class=ThreatClass.MISSING_CHECKSUM.value,
                severity="error",
                message="missing checksum / sha256 in provenance",
                fixture_id=fixture_id,
                remediation_owners=_owners(ThreatClass.MISSING_CHECKSUM),
            )
        )

    commit = (
        provenance.get("git_commit")
        or provenance.get("commit")
        or provenance.get("commit_sha")
        or record.get("git_commit")
    )
    if not commit:
        findings.append(
            Finding(
                threat_class=ThreatClass.MISSING_COMMIT_IDENTITY.value,
                severity="error",
                message="missing git commit identity in provenance",
                fixture_id=fixture_id,
                remediation_owners=_owners(ThreatClass.MISSING_COMMIT_IDENTITY),
            )
        )

    if provenance.get("fabricated") is True or record.get("fabricated_provenance") is True:
        findings.append(
            Finding(
                threat_class=ThreatClass.FABRICATED_PROVENANCE.value,
                severity="critical",
                message="fabricated provenance flag is set",
                fixture_id=fixture_id,
                remediation_owners=_owners(ThreatClass.FABRICATED_PROVENANCE),
            )
        )

    # Synthetic / dry-run / fixture evidence must never be presented as empirical.
    empirical_markers = {"empirical", "real_data", "live_cohort", "scientific_pass"}
    if synthetic or evidence_class in {"synthetic", "fixture", "dry_run", "engineering"}:
        if presented_as.lower() in empirical_markers or record.get("scientific_pass") is True:
            findings.append(
                Finding(
                    threat_class=ThreatClass.SYNTHETIC_TO_EMPIRICAL.value,
                    severity="critical",
                    message="synthetic/engineering evidence presented as empirical/scientific PASS",
                    fixture_id=fixture_id,
                    remediation_owners=_owners(ThreatClass.SYNTHETIC_TO_EMPIRICAL),
                )
            )

    if record.get("scientific_pass") is True and evidence_class == EVIDENCE_SECURITY_HINT:
        findings.append(
            Finding(
                threat_class=ThreatClass.SYNTHETIC_TO_EMPIRICAL.value,
                severity="critical",
                message="security harness evidence must never set scientific_pass=True",
                fixture_id=fixture_id,
                remediation_owners=_owners(ThreatClass.SYNTHETIC_TO_EMPIRICAL),
            )
        )

    return findings


# Local constant to avoid circular import of schema.EVIDENCE_CLASS in hot paths.
EVIDENCE_SECURITY_HINT = "batch2_security_engineering"
