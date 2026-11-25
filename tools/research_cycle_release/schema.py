"""Decision states and report schema."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"
BUNDLE_SCHEMA = "research_cycle_release_bundle.v1"
EVIDENCE_CLASS = "research_cycle_release_operational"

DEFAULT_LIMITATIONS = (
    "EVIDENCE_READY_FOR_REVIEW means operational completeness for human review, not scientific PASS.",
    "This evaluator never emits a Bayes factor or promotes proxy results to causal evidence.",
    "Missing values remain unknown (null), never fabricated zero.",
    "Hardware-dependent metrics are advisory unless comparability is proven.",
    "Synthetic and proxy research-cycle outputs are engineering evidence, not empirical neuroscience.",
)


class DecisionState(str, Enum):
    EVIDENCE_READY_FOR_REVIEW = "EVIDENCE_READY_FOR_REVIEW"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    PROVENANCE_FAILURE = "PROVENANCE_FAILURE"
    ARTIFACT_FAILURE = "ARTIFACT_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    RESOURCE_FAILURE = "RESOURCE_FAILURE"
    NETWORK_POLICY_FAILURE = "NETWORK_POLICY_FAILURE"
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"
    PROXY_ONLY = "PROXY_ONLY"
    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"
    INFRASTRUCTURE_BLOCKED = "INFRASTRUCTURE_BLOCKED"
    NOT_COMPARABLE = "NOT_COMPARABLE"


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


@dataclass
class CheckResult:
    check_id: str
    passed: Optional[bool]
    detail: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(
            {
                "check_id": self.check_id,
                "passed": self.passed,
                "detail": self.detail,
                "evidence": self.evidence,
            }
        )


@dataclass
class ReleaseEvidenceReport:
    schema_version: str
    decision: DecisionState
    cycle_id: Optional[str]
    evidence_class: str
    synthetic_flag: Optional[bool]
    proxy_flag: Optional[bool]
    empirical_flag: Optional[bool]
    reason_codes: List[str]
    reasons: List[str]
    checks: List[CheckResult]
    advisories: List[str]
    limitations: List[str]
    source_adapter: str
    source_checksum: Optional[str]
    bundle: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(
            {
                "schema_version": self.schema_version,
                "decision": self.decision.value,
                "cycle_id": self.cycle_id,
                "evidence_class": self.evidence_class,
                "synthetic_flag": self.synthetic_flag,
                "proxy_flag": self.proxy_flag,
                "empirical_flag": self.empirical_flag,
                "reason_codes": list(self.reason_codes),
                "reasons": list(self.reasons),
                "checks": [c.to_dict() for c in self.checks],
                "advisories": list(self.advisories),
                "limitations": list(self.limitations),
                "source_adapter": self.source_adapter,
                "source_checksum": self.source_checksum,
                "bundle": self.bundle,
                "scientific_pass_emitted": False,
                "bayes_factor_emitted": False,
                "causal_promotion_emitted": False,
                "note": (
                    "EVIDENCE_READY_FOR_REVIEW is not scientific PASS. "
                    "This tool never emits a Bayes factor."
                ),
            }
        )
