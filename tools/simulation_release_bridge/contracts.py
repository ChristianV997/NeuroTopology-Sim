"""Canonical data models, schemas, and finite JSON serialization for Simulation Release Bridge.

Contracts:
- NeuroTopologySim.SimulationReleaseBridge.v1
- NeuroTopologySim.SimulationReleaseBundle.v1

Guardrails & Invariants:
1. Accept only validated PASS execution records for artifact promotion.
2. Preserve PARTIAL, FAILED, TIMEOUT, BLOCKED, and NOT_IMPLEMENTED states.
3. Keep non-PASS promotion checksums null.
4. Reject fabricated provenance, incomplete manifests, non-finite metrics, output-root escapes, and temporary-only artifacts.
5. If the canonical bounded runner is absent from current main, fail closed and report the missing prerequisite.
6. Never emit scientific PASS or formal Bayes factors.
7. Strictly finite JSON serialization (reject NaN and Infinity).
"""
from __future__ import annotations

import enum
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "NeuroTopologySim.SimulationReleaseBridge.v1"
BUNDLE_SCHEMA_VERSION = "NeuroTopologySim.SimulationReleaseBundle.v1"

CHAIN_STAGES = (
    "input_provenance",
    "configuration",
    "code_revision",
    "seed",
    "execution_outcome",
    "artifact_manifest",
    "validation",
    "evidence_review",
)

# Scientific guardrail constants
SCIENTIFIC_VERDICT_DEFAULT = "NOT_APPLICABLE"
SCIENTIFIC_CLAIM_SCOPE_DEFAULT = (
    "Engineering contract and release bundle review only. "
    "Not empirical evidence, not formal Bayes factor, not a scientific PASS."
)
DEFAULT_SCIENTIFIC_LIMITATIONS = (
    "Operational promotion for release review is not scientific verification.",
    "This adapter never emits a scientific PASS or formal Bayes factor.",
    "Synthetic benchmarks remain confined to synthetic_demo_only.",
    "Proxy metrics remain confined to proxy_only and never substitute for causal evidence.",
    "Missing metrics remain strictly null, never zero-filled or fabricated.",
)


class SimulationReleaseError(ValueError):
    """Raised when release bundle construction or validation fails closed."""


class ExecutionOutcomeState(str, enum.Enum):
    """Execution outcome states matching canonical bounded execution contracts."""
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    BLOCKED = "BLOCKED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_RUN = "NOT_RUN"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


class ReleasePromotionStatus(str, enum.Enum):
    """Artifact promotion readiness decision."""
    PROMOTED = "PROMOTED"
    NOT_PROMOTED = "NOT_PROMOTED"
    BLOCKED = "BLOCKED"


class DataModality(str, enum.Enum):
    """Data modality of the underlying run."""
    EMPIRICAL = "empirical"
    SYNTHETIC = "synthetic"
    PROXY = "proxy"
    UNSPECIFIED = "unspecified"


class EvidenceClass(str, enum.Enum):
    """Evidence category according to repository guardrails."""
    EMPIRICAL_DATASET = "empirical_dataset"
    SYNTHETIC_DEMO_ONLY = "synthetic_demo_only"
    PROXY_ONLY = "proxy_only"
    PERFORMANCE_ONLY = "performance_only"
    COMPUTATIONAL_MODEL = "computational_model"
    UNSPECIFIED = "unspecified"


def finite_value(value: Any, path: str = "$") -> Any:
    """Return JSON-safe value preserving nulls and rejecting NaN/Infinity explicitly."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SimulationReleaseError(f"{path} contains non-finite float: {value}")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [finite_value(item, f"{path}[{idx}]") for idx, item in enumerate(value)]
    if isinstance(value, Mapping):
        return {str(k): finite_value(v, f"{path}.{k}") for k, v in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {k: finite_value(getattr(value, k), f"{path}.{k}") for k in value.__dataclass_fields__}
    return str(value)


def canonical_hash(value: Any) -> str:
    """Calculate deterministic SHA-256 hash over canonical JSON representation."""
    safe_val = finite_value(value)
    payload = json.dumps(
        safe_val,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dumps_finite_json(value: Any, *, indent: int = 2) -> str:
    """Serialize value to JSON with sorted keys, deterministic indentation, and no NaN/Inf."""
    safe_val = finite_value(value)
    return json.dumps(safe_val, sort_keys=True, indent=indent, allow_nan=False) + "\n"


@dataclass
class InputProvenanceSpec:
    """Stage 1: Input provenance specification."""
    dataset_id: str
    source: str
    data_mode: str
    input_references: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class ConfigurationSpec:
    """Stage 2: Execution configuration specification."""
    parameters: dict[str, Any] = field(default_factory=dict)
    argv: list[str] = field(default_factory=list)
    spec_id: str | None = None
    timeout_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class CodeRevisionSpec:
    """Stage 3: Code revision and git provenance."""
    code_revision: str
    repo: str = "NeuroTopology-Sim"
    clean_working_tree: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class SeedSpec:
    """Stage 4: Deterministic random seed specification."""
    seed: int
    deterministic_fixed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class ExecutionOutcomeSpec:
    """Stage 5: Local execution outcome."""
    state: str  # ExecutionOutcomeState value
    exit_code: int | None = None
    elapsed_s: float | None = None
    error_message: str | None = None
    runner_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class ArtifactManifestItem:
    """Single entry in the artifact manifest."""
    relative_path: str
    sha256: str
    size_bytes: int
    role: str = "output"

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class ArtifactManifestSpec:
    """Stage 6: Artifact manifest cataloging outputs."""
    artifacts: list[ArtifactManifestItem] = field(default_factory=list)
    run_directory: str = ""
    duplicate_content: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class ValidationReportSpec:
    """Stage 7: Validation audit report."""
    report_id: str
    passed: bool
    status: str
    checks: dict[str, bool] = field(default_factory=dict)
    finite_json_verified: bool = True
    zero_network_verified: bool = True

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class EvidenceReviewSpec:
    """Stage 8: Evidence review and release gate check."""
    review_id: str
    decision: str
    evidence_class: str
    reason_codes: list[str] = field(default_factory=list)
    operational_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class SimulationReleaseBundle:
    """Unified canonical bundle for simulation release review.

    Guarantees:
    - Complete 8-stage chain representation.
    - Only promoted when execution outcome is strictly PASS and validation passed.
    - Non-PASS checksums are strictly null.
    - Rejects fabricated provenance, output escapes, temporary-only artifacts.
    - Never emits scientific PASS or formal Bayes factors.
    """
    bundle_id: str
    cycle_id: str
    created_at: str
    promotion_status: str  # ReleasePromotionStatus
    promotion_checksum: str | None  # null if non-PASS or not promoted
    chain_complete: bool
    stages: dict[str, Any]  # The 8 chain stages
    data_mode: str
    evidence_class: str
    diagnostics: dict[str, list[str]] = field(
        default_factory=lambda: {
            "missing": [],
            "errors": [],
            "rejected": [],
            "warnings": [],
        }
    )
    scientific_verdict: str = SCIENTIFIC_VERDICT_DEFAULT
    scientific_claim_scope: str = SCIENTIFIC_CLAIM_SCOPE_DEFAULT
    scientific_limitations: list[str] = field(
        default_factory=lambda: list(DEFAULT_SCIENTIFIC_LIMITATIONS)
    )
    schema_version: str = BUNDLE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d = finite_value(self)
        return d

    def to_json(self, *, indent: int = 2) -> str:
        return dumps_finite_json(self.to_dict(), indent=indent)
