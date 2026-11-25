"""Deterministic graph projection builder for the Awareness Studio evidence graph.

Constructs graph nodes and edges with deterministic ID assignment, duplicate
detection, safety label attachment, and summary computation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from .diagnostics import run_graph_diagnostics
from .models import (
    EvidenceGraph,
    GraphDiagnostic,
    GraphEdge,
    GraphNode,
    GraphSummary,
    _safe_dict,
    compute_content_checksum,
)
from .types import (
    DiagnosticCode,
    DiagnosticSeverity,
    EdgeType,
    EvidenceClass,
    NodeStatus,
    NodeType,
    SafetyLabel,
)


class EvidenceGraphBuilder:
    """Incremental, deterministic builder for the research-cycle evidence graph."""

    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._edge_keys: set[tuple[str, str, str]] = set()
        self._diagnostics: list[GraphDiagnostic] = []
        self._metadata: dict[str, Any] = dict(metadata or {})

    def add_node(self, node: GraphNode) -> GraphNode:
        """Add a GraphNode with duplicate detection and scientific safety labeling."""
        # Ensure default non-negotiable safety guardrails
        for mandatory_lbl in (SafetyLabel.NO_CLINICAL_CLAIM.value, SafetyLabel.NO_ONTOLOGY_PROMOTION.value):
            if mandatory_lbl not in node.safety_labels:
                node.safety_labels.append(mandatory_lbl)

        # Evidence-class specific labels
        if node.evidence_class == EvidenceClass.SYNTHETIC.value:
            if SafetyLabel.SYNTHETIC_ONLY.value not in node.safety_labels:
                node.safety_labels.append(SafetyLabel.SYNTHETIC_ONLY.value)
        elif node.evidence_class == EvidenceClass.PROXY.value:
            if SafetyLabel.PROXY_METRIC.value not in node.safety_labels:
                node.safety_labels.append(SafetyLabel.PROXY_METRIC.value)

        # Status specific labels
        if node.status in (NodeStatus.PROVISIONAL.value, NodeStatus.PROPOSED.value):
            if SafetyLabel.PROVISIONAL.value not in node.safety_labels:
                node.safety_labels.append(SafetyLabel.PROVISIONAL.value)
        elif node.status == NodeStatus.INCONCLUSIVE.value:
            if SafetyLabel.INCONCLUSIVE.value not in node.safety_labels:
                node.safety_labels.append(SafetyLabel.INCONCLUSIVE.value)
        elif node.status == NodeStatus.REVIEW_REQUIRED.value:
            if SafetyLabel.REVIEW_REQUIRED.value not in node.safety_labels:
                node.safety_labels.append(SafetyLabel.REVIEW_REQUIRED.value)

        if node.node_id in self._nodes:
            existing = self._nodes[node.node_id]
            if existing.checksum == node.checksum:
                self._diagnostics.append(
                    GraphDiagnostic(
                        code=DiagnosticCode.DUPLICATE_NODE_EXACT.value,
                        severity=DiagnosticSeverity.INFO.value,
                        message=f"Node '{node.node_id}' added multiple times with identical content.",
                        affected_ids=(node.node_id,),
                    )
                )
                return existing
            else:
                self._diagnostics.append(
                    GraphDiagnostic(
                        code=DiagnosticCode.DUPLICATE_NODE_CONTENT_MISMATCH.value,
                        severity=DiagnosticSeverity.ERROR.value,
                        message=f"Node '{node.node_id}' content mismatch between incoming and existing records.",
                        affected_ids=(node.node_id,),
                        metadata={"existing_checksum": existing.checksum, "incoming_checksum": node.checksum},
                    )
                )
                return existing

        self._nodes[node.node_id] = node
        return node

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """Add a GraphEdge with duplicate edge suppression."""
        edge_key = (edge.edge_type, edge.source_id, edge.target_id)
        if edge_key in self._edge_keys:
            self._diagnostics.append(
                GraphDiagnostic(
                    code=DiagnosticCode.DUPLICATE_EDGE.value,
                    severity=DiagnosticSeverity.INFO.value,
                    message=f"Edge '{edge.edge_id}' ({edge.edge_type}) already exists.",
                    affected_ids=(edge.source_id, edge.target_id, edge.edge_id),
                )
            )
            return edge

        self._edge_keys.add(edge_key)
        self._edges.append(edge)
        return edge

    def link(
        self,
        edge_type: EdgeType | str,
        source_id: str,
        target_id: str,
        label: str = "",
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
        qualifier: str | None = None,
    ) -> GraphEdge:
        """Convenience method to construct and add a GraphEdge."""
        edge = GraphEdge.create(
            edge_type=edge_type,
            source_id=source_id,
            target_id=target_id,
            label=label,
            confidence=confidence,
            metadata=metadata,
            qualifier=qualifier,
        )
        return self.add_edge(edge)

    def build(self, evidence_class_filter: Sequence[str] | None = None) -> EvidenceGraph:
        """Finalize graph, run all diagnostics, compute summary, and return EvidenceGraph."""
        # Initial graph assembly
        base_graph = EvidenceGraph(
            nodes=dict(self._nodes),
            edges=list(self._edges),
            diagnostics=list(self._diagnostics),
            metadata=dict(self._metadata),
        )

        # Run complete diagnostics
        all_diagnostics = run_graph_diagnostics(base_graph)
        base_graph.diagnostics = all_diagnostics

        # Apply evidence class filter if requested
        if evidence_class_filter:
            base_graph = base_graph.filter_by_evidence_class(evidence_class_filter)
            # Re-run diagnostics on filtered projection
            base_graph.diagnostics = run_graph_diagnostics(base_graph)

        # Calculate summary
        summary = self._calculate_summary(base_graph)
        base_graph.summary = summary
        return base_graph

    @staticmethod
    def _calculate_summary(graph: EvidenceGraph) -> GraphSummary:
        nodes_by_type: dict[str, int] = {}
        status_dist: dict[str, int] = {}
        evidence_dist: dict[str, int] = {}
        safety_dist: dict[str, int] = {}
        for node in graph.nodes.values():
            nodes_by_type[node.node_type] = nodes_by_type.get(node.node_type, 0) + 1
            status_dist[node.status] = status_dist.get(node.status, 0) + 1
            evidence_dist[node.evidence_class] = evidence_dist.get(node.evidence_class, 0) + 1
            for lbl in node.safety_labels:
                safety_dist[lbl] = safety_dist.get(lbl, 0) + 1

        edges_by_type: dict[str, int] = {}
        for edge in graph.edges:
            edges_by_type[edge.edge_type] = edges_by_type.get(edge.edge_type, 0) + 1

        diag_counts: dict[str, int] = {}
        has_critical = False
        for diag in graph.diagnostics:
            diag_counts[diag.severity] = diag_counts.get(diag.severity, 0) + 1
            if diag.severity == DiagnosticSeverity.ERROR.value:
                has_critical = True

        # Compute deterministic graph checksum over sorted node and edge canonical dicts
        graph_dict = {
            "nodes": [graph.nodes[k].to_dict() for k in sorted(graph.nodes)],
            "edges": [e.to_dict() for e in sorted(graph.edges, key=lambda x: (x.edge_type, x.source_id, x.target_id, x.edge_id))],
        }
        graph_checksum = hashlib.sha256(
            json.dumps(graph_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        return GraphSummary(
            total_nodes=len(graph.nodes),
            total_edges=len(graph.edges),
            nodes_by_type=dict(sorted(nodes_by_type.items())),
            edges_by_type=dict(sorted(edges_by_type.items())),
            evidence_distribution=dict(sorted(evidence_dist.items())),
            status_distribution=dict(sorted(status_dist.items())),
            safety_label_distribution=dict(sorted(safety_dist.items())),
            diagnostic_counts=dict(sorted(diag_counts.items())),
            has_critical_diagnostics=has_critical,
            graph_checksum=graph_checksum,
        )
