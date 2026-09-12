"""Canonical data models, schemas, and finite JSON serialization for Research Cycle Bridge.

Contracts:
- NeuroTopologySim.ResearchCycleBridge.v1
- NeuroTopologySim.ResearchCycleEvidenceGraph.v1

Guardrails:
- Never infer scientific validity from artifact presence.
- Never promote proxy, synthetic, or benchmark output to formal evidence.
- Preserve nulls instead of zero-filling missing metrics.
- Enforce strict finite JSON serialization (NaN and Infinity rejected).
"""
from __future__ import annotations

import enum
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

BRIDGE_SCHEMA_VERSION = "NeuroTopologySim.ResearchCycleBridge.v1"
EVIDENCE_GRAPH_SCHEMA = "NeuroTopologySim.ResearchCycleEvidenceGraph.v1"


class BridgeContractError(ValueError):
    """Raised when a bridge record or value violates finite schema contracts."""


class BridgeRecordStatus(str, enum.Enum):
    """Lifecycle and extraction status of a linked bridge record."""
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"
    CONFLICTING = "CONFLICTING"
    UNAVAILABLE = "UNAVAILABLE"


class BridgeDataMode(str, enum.Enum):
    """Data modality of the underlying source."""
    EMPIRICAL = "empirical"
    SYNTHETIC = "synthetic"
    PROXY = "proxy"
    UNAVAILABLE = "unavailable"


class BridgeEvidenceClass(str, enum.Enum):
    """Evidence category according to repository guardrails."""
    EMPIRICAL_DATASET = "empirical_dataset"
    SYNTHETIC_DEMO_ONLY = "synthetic_demo_only"
    PROXY_ONLY = "proxy_only"
    PERFORMANCE_ONLY = "performance_only"
    COMPUTATIONAL_MODEL = "computational_model"
    UNSPECIFIED = "unspecified"


def finite_value(value: Any, path: str = "$") -> Any:
    """Return JSON-safe values preserving nulls and rejecting NaN/Infinity."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BridgeContractError(f"{path} contains non-finite value: {value}")
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


def dumps_finite(value: Mapping[str, Any], *, indent: int = 2) -> str:
    """Serialize a mapping to JSON with sorted keys, indented format, and no NaN/Inf."""
    return json.dumps(finite_value(value), sort_keys=True, indent=indent, allow_nan=False) + "\n"


@dataclass
class EvidenceGraphNode:
    """Single node in the research-cycle evidence graph."""
    id: str
    stage: str
    data_mode: str
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class EvidenceGraphEdge:
    """Directed link between stages in the evidence graph."""
    source: str
    target: str
    relationship: str

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class EvidenceGraph:
    """Canonical research-cycle evidence graph."""
    graph_id: str
    nodes: list[EvidenceGraphNode] = field(default_factory=list)
    edges: list[EvidenceGraphEdge] = field(default_factory=list)
    missing_nodes: list[str] = field(default_factory=list)
    partial: bool = False
    scientific_status: str = "not_evidence"
    schema_version: str = EVIDENCE_GRAPH_SCHEMA
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = finite_value(self)
        if not self.checksum:
            d["checksum"] = canonical_hash({k: v for k, v in d.items() if k != "checksum"})
        return d


@dataclass
class ResearchCycleBridgeRecord:
    """Unified deterministic bridge record linking simulation artifacts to research-cycle entities."""
    record_id: str
    cycle_id: str
    dataset_id: str | None
    data_mode: str
    status: str
    evidence_class: str
    synthetic: bool
    proxy: bool
    empirical: bool
    provenance: dict[str, Any]
    source_dataset: dict[str, Any] | None = None
    experiment_plan: dict[str, Any] | None = None
    simulation_run: dict[str, Any] | None = None
    artifact_manifest: dict[str, Any] | None = None
    validation_report: dict[str, Any] | None = None
    evidence_graph: dict[str, Any] | None = None
    release_evidence: dict[str, Any] | None = None
    parent_ids: list[str] = field(default_factory=list)
    parent_checksums: list[str] = field(default_factory=list)
    diagnostics: dict[str, list[str]] = field(
        default_factory=lambda: {
            "missing": [],
            "stale": [],
            "partial": [],
            "failed": [],
            "conflicting": [],
            "errors": [],
        }
    )
    scientific_verdict: str = "NOT_APPLICABLE"
    stage: str = "research_cycle_bridge"
    schema_version: str = BRIDGE_SCHEMA_VERSION
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = finite_value(self)
        if not self.checksum:
            d_for_hash = {k: v for k, v in d.items() if k != "checksum"}
            d["checksum"] = canonical_hash(d_for_hash)
            self.checksum = d["checksum"]
        return d

    def to_json(self, *, indent: int = 2) -> str:
        d = self.to_dict()
        return dumps_finite(d, indent=indent)


def verify_bridge_checksum(record_dict: dict[str, Any]) -> bool:
    """Verify cryptographic SHA-256 integrity of a bridge record dict."""
    reported = record_dict.get("checksum", "")
    if not reported:
        return False
    d_for_hash = {k: v for k, v in record_dict.items() if k != "checksum"}
    expected = canonical_hash(d_for_hash)
    return reported == expected
