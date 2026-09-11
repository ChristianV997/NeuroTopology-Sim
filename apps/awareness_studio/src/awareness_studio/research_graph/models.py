"""Data models for the Awareness Studio evidence graph projection.

Provides typed, content-addressed dataclasses for nodes, edges, diagnostics,
summaries, and the complete projection graph. Enforces RFC-8259 compliance
(finite floats, recursive serialization).
"""
from __future__ import annotations

import enum
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from .types import (
    DiagnosticCode,
    DiagnosticSeverity,
    EdgeType,
    EvidenceClass,
    NodeStatus,
    NodeType,
    SafetyLabel,
)


def _safe_dict(val: Any) -> Any:
    """Enforce strict RFC-8259 JSON compliance (finite floats, enum coercion)."""
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, (int, str, bool)) or val is None:
        return val
    if isinstance(val, enum.Enum):
        return val.value
    if isinstance(val, Mapping):
        return {str(k): _safe_dict(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set, frozenset)):
        return [_safe_dict(v) for v in val]
    return str(val)


def compute_content_checksum(data: Mapping[str, Any], exclude_fields: Sequence[str] = ("checksum",)) -> str:
    """Compute deterministic SHA-256 digest of dictionary payload."""
    clean_dict = {str(k): _safe_dict(v) for k, v in data.items() if k not in exclude_fields}
    canonical = json.dumps(clean_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class GraphNode:
    """A discrete scientific entity in the research-cycle evidence graph."""
    node_id: str
    node_type: str
    label: str
    status: str = NodeStatus.ACTIVE.value
    evidence_class: str = EvidenceClass.UNKNOWN.value
    safety_labels: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    source_id: str | None = None
    checksum: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.node_type, enum.Enum):
            self.node_type = self.node_type.value
        if isinstance(self.status, enum.Enum):
            self.status = self.status.value
        if isinstance(self.evidence_class, enum.Enum):
            self.evidence_class = self.evidence_class.value
        self.safety_labels = [
            lbl.value if isinstance(lbl, enum.Enum) else str(lbl)
            for lbl in self.safety_labels
        ]
        if not self.checksum:
            self.checksum = compute_content_checksum({
                "node_id": self.node_id,
                "node_type": self.node_type,
                "label": self.label,
                "properties": self.properties,
                "evidence_class": self.evidence_class,
            })

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "node_id": self.node_id,
            "node_type": self.node_type,
            "label": self.label,
            "status": self.status,
            "evidence_class": self.evidence_class,
            "safety_labels": sorted(set(self.safety_labels)),
            "properties": self.properties,
            "source_id": self.source_id,
            "checksum": self.checksum,
            "tags": sorted(set(self.tags)),
        })


@dataclass(frozen=True)
class GraphEdge:
    """A directed epistemic or causal relation between two nodes."""
    edge_id: str
    edge_type: str
    source_id: str
    target_id: str
    label: str = ""
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        edge_type: EdgeType | str,
        source_id: str,
        target_id: str,
        label: str = "",
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
        qualifier: str | None = None,
    ) -> GraphEdge:
        type_str = edge_type.value if isinstance(edge_type, enum.Enum) else str(edge_type)
        edge_id = f"edge:{type_str}:{source_id}->{target_id}"
        if qualifier:
            edge_id += f":{qualifier}"
        return cls(
            edge_id=edge_id,
            edge_type=type_str,
            source_id=source_id,
            target_id=target_id,
            label=label or type_str,
            confidence=confidence,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "edge_id": self.edge_id,
            "edge_type": self.edge_type,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "label": self.label,
            "confidence": self.confidence,
            "metadata": self.metadata,
        })


@dataclass(frozen=True)
class GraphDiagnostic:
    """Diagnostic notice for graph inconsistencies, orphans, or safety violations."""
    code: str
    severity: str
    message: str
    affected_ids: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "affected_ids": list(self.affected_ids),
            "metadata": self.metadata,
        })


@dataclass
class GraphSummary:
    """Statistical and scientific safety summary of the evidence graph."""
    total_nodes: int = 0
    total_edges: int = 0
    nodes_by_type: dict[str, int] = field(default_factory=dict)
    edges_by_type: dict[str, int] = field(default_factory=dict)
    evidence_distribution: dict[str, int] = field(default_factory=dict)
    status_distribution: dict[str, int] = field(default_factory=dict)
    safety_label_distribution: dict[str, int] = field(default_factory=dict)
    diagnostic_counts: dict[str, int] = field(default_factory=dict)
    has_critical_diagnostics: bool = False
    graph_checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass
class EvidenceGraph:
    """Complete read-only projection of research-cycle nodes, edges, and diagnostics."""
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    diagnostics: list[GraphDiagnostic] = field(default_factory=list)
    summary: GraphSummary = field(default_factory=GraphSummary)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def get_edges_from(self, source_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.source_id == source_id]

    def get_edges_to(self, target_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.target_id == target_id]

    def get_edges_between(self, source_id: str, target_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.source_id == source_id and e.target_id == target_id]

    def filter_by_evidence_class(self, allowed_classes: Sequence[EvidenceClass | str]) -> EvidenceGraph:
        """Return a projected subgraph containing only nodes matching the specified evidence classes."""
        allowed = {cls.value if isinstance(cls, enum.Enum) else str(cls) for cls in allowed_classes}
        # Non-evidence nodes (like claims, hypotheses, experiments) remain if connected to allowed evidence,
        # or we include nodes whose evidence_class is in allowed OR is non-evidence.
        # Strict mode: keep nodes where evidence_class in allowed or non-evidence nodes,
        # but prune synthetic evidence nodes when filtering for empirical/formal.
        filtered_nodes = {
            nid: node for nid, node in self.nodes.items()
            if node.evidence_class in allowed or node.evidence_class == EvidenceClass.UNKNOWN.value
        }
        filtered_edges = [
            edge for edge in self.edges
            if edge.source_id in filtered_nodes and edge.target_id in filtered_nodes
        ]
        new_graph = EvidenceGraph(
            nodes=filtered_nodes,
            edges=filtered_edges,
            diagnostics=list(self.diagnostics),
            metadata=dict(self.metadata),
        )
        new_graph.metadata["filtered_by_evidence_class"] = sorted(allowed)
        return new_graph

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "metadata": self.metadata,
            "summary": self.summary.to_dict(),
            "nodes": [self.nodes[k].to_dict() for k in sorted(self.nodes)],
            "edges": [e.to_dict() for e in sorted(self.edges, key=lambda x: (x.edge_type, x.source_id, x.target_id, x.edge_id))],
            "diagnostics": [d.to_dict() for d in sorted(self.diagnostics, key=lambda x: (x.severity, x.code, str(x.affected_ids)))],
        })
