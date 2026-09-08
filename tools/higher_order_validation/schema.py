"""Schema for higher-order adversarial validation results."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "1.0"
EVIDENCE_CLASS = "engineering_adversarial_synthetic"


class CaseOutcome(str, Enum):
    """Engineering outcomes only — never a scientific PASS."""

    POSITIVE_CONTROL_HIT = "POSITIVE_CONTROL_HIT"
    NEGATIVE_CONTROL_OK = "NEGATIVE_CONTROL_OK"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    FALSE_NEGATIVE = "FALSE_NEGATIVE"
    WARNING = "WARNING"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


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
class ValidationCaseResult:
    schema_version: str
    case_id: str
    data_generating_process: str
    expected_result: str
    observed_result: str
    outcome: CaseOutcome
    random_seed: int
    source_checksum: str
    evidence_class: str
    synthetic: bool
    metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        return json_safe(payload)


DEFAULT_LIMITATIONS = [
    "Adversarial synthetic validation is engineering evidence, not empirical neuroscience.",
    "Never interpret these outcomes as a scientific PASS or formal Bayes factor.",
    "Synthetic DGPs do not represent biological mechanism confirmation.",
    "Multiple-comparison corrections are unresolved unless explicitly declared.",
]
