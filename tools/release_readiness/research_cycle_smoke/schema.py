"""Schema for research-cycle smoke harness reports."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"
SMOKE_EVIDENCE_CLASS = "research_cycle_smoke_engineering"
CHAIN_STAGES: tuple[str, ...] = (
    "source",
    "plan",
    "hypothesis",
    "experiment",
    "run",
    "artifact",
    "validation",
    "evidence_graph",
    "release_decision",
)

DEFAULT_LIMITATIONS = (
    "Smoke fixtures are synthetic engineering acceptance evidence, not empirical neuroscience.",
    "EVIDENCE_READY_FOR_REVIEW from release-evidence is not scientific PASS.",
    "This harness never emits a Bayes factor and never promotes proxy/synthetic results to causal evidence.",
    "Missing metrics remain unknown (null), never fabricated zero.",
    "No network and no full-dataset download are required for this smoke suite.",
)


class ScenarioId(str, Enum):
    COMPLETE_VALID_ENGINEERING = "complete_valid_engineering"
    INCOMPLETE_SOURCE = "incomplete_source"
    PARTIAL_SUBJECT_SET = "partial_subject_set"
    FAILED_SIMULATION = "failed_simulation"
    TIMEOUT = "timeout"
    MISSING_VALIDATION_REPORT = "missing_validation_report"
    INVALID_PROVENANCE = "invalid_provenance"
    NETWORK_POLICY_VIOLATION = "network_policy_violation"
    SYNTHETIC_ONLY = "synthetic_only"
    PROXY_ONLY = "proxy_only"


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
class StageRecord:
    stage: str
    record_id: str
    status: str
    parent_ids: List[str]
    checksum: str
    visible_issue: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(
            {
                "stage": self.stage,
                "record_id": self.record_id,
                "status": self.status,
                "parent_ids": list(self.parent_ids),
                "checksum": self.checksum,
                "visible_issue": self.visible_issue,
                "payload": self.payload,
            }
        )


@dataclass
class ScenarioResult:
    scenario_id: str
    expected_decision: str
    observed_decision: str
    decision_match: bool
    chain_ok: bool
    incomplete_visible: bool
    synthetic_not_scientific: bool
    missing_not_zeroed: bool
    checksum: str
    release_reason_codes: List[str]
    stages: List[StageRecord]
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(
            {
                "scenario_id": self.scenario_id,
                "expected_decision": self.expected_decision,
                "observed_decision": self.observed_decision,
                "decision_match": self.decision_match,
                "chain_ok": self.chain_ok,
                "incomplete_visible": self.incomplete_visible,
                "synthetic_not_scientific": self.synthetic_not_scientific,
                "missing_not_zeroed": self.missing_not_zeroed,
                "checksum": self.checksum,
                "release_reason_codes": list(self.release_reason_codes),
                "stages": [s.to_dict() for s in self.stages],
                "warnings": list(self.warnings),
                "details": self.details,
            }
        )
