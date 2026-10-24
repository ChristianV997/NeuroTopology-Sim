"""Diagnostic rules and integrity auditing for the Awareness Studio evidence graph.

Audits:
- Orphan artifacts and disconnected entities.
- Dangling edge references (missing sources/targets).
- Conflicting statuses (opposing supports/contradicts edges, verdict mismatches).
- Scientific promotion guardrails (synthetic/proxy claiming formal status, unsupported promotion).
- Superseded node consistency.
"""
from __future__ import annotations

from typing import Sequence

from .models import EvidenceGraph, GraphDiagnostic, GraphNode
from .types import (
    DiagnosticCode,
    DiagnosticSeverity,
    EdgeType,
    EvidenceClass,
    NodeStatus,
    NodeType,
    SafetyLabel,
)


def run_graph_diagnostics(graph: EvidenceGraph) -> list[GraphDiagnostic]:
    """Execute complete suite of integrity and scientific safety diagnostics."""
    diagnostics: list[GraphDiagnostic] = list(graph.diagnostics)

    # 1. Dangling edge references
    existing_node_ids = set(graph.nodes.keys())
    for edge in graph.edges:
        if edge.source_id not in existing_node_ids:
            diagnostics.append(
                GraphDiagnostic(
                    code=DiagnosticCode.DANGLING_EDGE_SOURCE.value,
                    severity=DiagnosticSeverity.ERROR.value,
                    message=f"Edge '{edge.edge_id}' references non-existent source node '{edge.source_id}'.",
                    affected_ids=(edge.source_id, edge.edge_id),
                    metadata={"edge": edge.to_dict()},
                )
            )
        if edge.target_id not in existing_node_ids:
            diagnostics.append(
                GraphDiagnostic(
                    code=DiagnosticCode.DANGLING_EDGE_TARGET.value,
                    severity=DiagnosticSeverity.ERROR.value,
                    message=f"Edge '{edge.edge_id}' references non-existent target node '{edge.target_id}'.",
                    affected_ids=(edge.target_id, edge.edge_id),
                    metadata={"edge": edge.to_dict()},
                )
            )

    # 2. Degree tracking for orphan detection
    in_degree: dict[str, int] = {nid: 0 for nid in existing_node_ids}
    out_degree: dict[str, int] = {nid: 0 for nid in existing_node_ids}

    for edge in graph.edges:
        if edge.source_id in out_degree:
            out_degree[edge.source_id] += 1
        if edge.target_id in in_degree:
            in_degree[edge.target_id] += 1

    for nid, node in graph.nodes.items():
        total_deg = in_degree[nid] + out_degree[nid]
        if total_deg == 0:
            if node.node_type == NodeType.ARTIFACT.value:
                diagnostics.append(
                    GraphDiagnostic(
                        code=DiagnosticCode.ORPHAN_ARTIFACT.value,
                        severity=DiagnosticSeverity.WARNING.value,
                        message=f"Artifact '{nid}' is unreferenced and has no generating run or validating edges.",
                        affected_ids=(nid,),
                    )
                )
            else:
                diagnostics.append(
                    GraphDiagnostic(
                        code=DiagnosticCode.ORPHAN_NODE.value,
                        severity=DiagnosticSeverity.INFO.value,
                        message=f"Node '{nid}' of type '{node.node_type}' is completely isolated (0 edges).",
                        affected_ids=(nid,),
                    )
                )

    # 3. Conflicting status detection (opposing evidentiary edges)
    # Group edges by target_id
    incoming_by_target: dict[str, list] = {}
    for edge in graph.edges:
        incoming_by_target.setdefault(edge.target_id, []).append(edge)

    for target_id, edges in incoming_by_target.items():
        has_supports = any(e.edge_type == EdgeType.SUPPORTS.value for e in edges)
        has_contradicts = any(e.edge_type == EdgeType.CONTRADICTS.value for e in edges)
        if has_supports and has_contradicts:
            diagnostics.append(
                GraphDiagnostic(
                    code=DiagnosticCode.CONFLICTING_STATUS.value,
                    severity=DiagnosticSeverity.WARNING.value,
                    message=f"Target node '{target_id}' has conflicting evidence: both 'supports' and 'contradicts' incoming edges exist.",
                    affected_ids=(target_id,),
                    metadata={"incoming_edge_types": [e.edge_type for e in edges]},
                )
            )
            target_node = graph.nodes.get(target_id)
            if target_node:
                if SafetyLabel.REVIEW_REQUIRED.value not in target_node.safety_labels:
                    target_node.safety_labels.append(SafetyLabel.REVIEW_REQUIRED.value)
                if SafetyLabel.INCONCLUSIVE.value not in target_node.safety_labels:
                    target_node.safety_labels.append(SafetyLabel.INCONCLUSIVE.value)

    # 4. Failed validation linked via 'supports'
    for edge in graph.edges:
        if edge.edge_type == EdgeType.SUPPORTS.value:
            src_node = graph.nodes.get(edge.source_id)
            if src_node and src_node.node_type == NodeType.VALIDATION.value:
                verdict = src_node.properties.get("verdict", "").upper()
                if verdict in ("FAIL", "FAILED", "AMBIGUOUS", "INCONCLUSIVE"):
                    diagnostics.append(
                        GraphDiagnostic(
                            code=DiagnosticCode.CONFLICTING_STATUS.value,
                            severity=DiagnosticSeverity.ERROR.value,
                            message=f"Validation '{src_node.node_id}' with non-passing verdict '{verdict}' is linked via 'supports' edge to '{edge.target_id}'.",
                            affected_ids=(src_node.node_id, edge.target_id, edge.edge_id),
                        )
                    )

    # 5. Scientific safety and claim promotion guardrails
    for nid, node in graph.nodes.items():
        # Check evidence class violations
        if node.node_type == NodeType.EVIDENCE_RECORD.value:
            is_synth = node.properties.get("is_synthetic") is True or node.evidence_class == EvidenceClass.SYNTHETIC.value
            is_proxy = node.properties.get("is_proxy") is True or node.evidence_class == EvidenceClass.PROXY.value

            if is_synth and node.evidence_class == EvidenceClass.FORMAL.value:
                diagnostics.append(
                    GraphDiagnostic(
                        code=DiagnosticCode.SYNTHETIC_FORMAL_VIOLATION.value,
                        severity=DiagnosticSeverity.ERROR.value,
                        message=f"Evidence '{nid}' is synthetic but claims formal evidence class.",
                        affected_ids=(nid,),
                    )
                )
            if is_proxy and node.evidence_class == EvidenceClass.FORMAL.value:
                diagnostics.append(
                    GraphDiagnostic(
                        code=DiagnosticCode.PROXY_FORMAL_VIOLATION.value,
                        severity=DiagnosticSeverity.ERROR.value,
                        message=f"Evidence '{nid}' is a proxy metric but claims formal evidence class.",
                        affected_ids=(nid,),
                    )
                )

        # Check sources AND claims for an unverified empirical/formal claim.
        # A literature/data source, or a claim derived from one, is at most
        # hypothesis-generating input unless something in its own properties
        # actually corroborates it (an independent verification/peer-review
        # signal, or the same preregistered+held-out-locked bar
        # EVIDENCE_RECORD formal claims must clear). Absent that,
        # EMPIRICAL/FORMAL is an unsupported promotion, not a fact -- flag
        # it rather than silently trusting whatever evidence_class a
        # manifest declared. This covers CLAIM nodes as well as
        # SOURCE_SNAPSHOT ones deliberately: a claim's evidence_class comes
        # from the same manifest-declared, unverified-by-construction path,
        # and nothing else in this function checked a CLAIM node's
        # evidence_class at all before this.
        if node.node_type in (NodeType.SOURCE_SNAPSHOT.value, NodeType.CLAIM.value) and node.evidence_class in (
            EvidenceClass.EMPIRICAL.value,
            EvidenceClass.FORMAL.value,
        ):
            props = node.properties
            verified = (
                props.get("verification_status") == "verified"
                or props.get("peer_review_status") == "peer_reviewed"
                or props.get("review_status") == "reviewed_accepted"
                or (props.get("preregistered") is True and props.get("held_out_split_locked") is True)
            )
            if not verified:
                diagnostics.append(
                    GraphDiagnostic(
                        code=DiagnosticCode.EMPIRICAL_CLAIM_WITHOUT_VERIFICATION.value,
                        severity=DiagnosticSeverity.ERROR.value,
                        message=(
                            f"Node '{nid}' ({node.node_type}) claims evidence_class={node.evidence_class!r} "
                            "with no independent verification/peer-review signal in its properties."
                        ),
                        affected_ids=(nid,),
                    )
                )

        # Check unsupported promotion on hypotheses/claims
        if node.node_type in (NodeType.HYPOTHESIS.value, NodeType.CLAIM.value):
            if node.status in (NodeStatus.SUPPORTED.value, "confirmed", "fact"):
                # Must have passed human review gate
                gate = node.properties.get("human_review_gate") or node.properties.get("human_review")
                gate_passed = False
                reviewer = None
                if isinstance(gate, dict):
                    gate_passed = gate.get("passed") is True
                    reviewer = gate.get("reviewer")
                elif node.properties.get("human_review_passed") is True:
                    gate_passed = True
                    reviewer = node.properties.get("human_reviewer")

                if not gate_passed or not isinstance(reviewer, str) or not reviewer.strip():
                    diagnostics.append(
                        GraphDiagnostic(
                            code=DiagnosticCode.UNSUPPORTED_PROMOTION.value,
                            severity=DiagnosticSeverity.ERROR.value,
                            message=f"Node '{nid}' is marked '{node.status}' without signed human review gate.",
                            affected_ids=(nid,),
                        )
                    )
                    # Automatically tag with REVIEW_REQUIRED
                    if SafetyLabel.REVIEW_REQUIRED.value not in node.safety_labels:
                        node.safety_labels.append(SafetyLabel.REVIEW_REQUIRED.value)

        # 6. Superseded node consistency
        if node.status == NodeStatus.SUPERSEDED.value:
            has_supersedes_edge = any(
                e.edge_type in (EdgeType.SUPERSEDES.value, EdgeType.REVISES.value)
                and (e.source_id == nid or e.target_id == nid)
                for e in graph.edges
            )
            if not has_supersedes_edge:
                diagnostics.append(
                    GraphDiagnostic(
                        code=DiagnosticCode.SUPERSEDED_UNLINKED.value,
                        severity=DiagnosticSeverity.WARNING.value,
                        message=f"Node '{nid}' is marked superseded but has no supersedes or revises edge linking it.",
                        affected_ids=(nid,),
                    )
                )

    # Sort diagnostics deterministically
    return sorted(
        diagnostics,
        key=lambda d: (d.severity, d.code, tuple(sorted(d.affected_ids)), d.message),
    )
