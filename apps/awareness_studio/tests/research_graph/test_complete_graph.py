"""Unit and integration tests for complete evidence graph projection."""
from __future__ import annotations

import json
from pathlib import Path

from awareness_studio.research_graph import (
    EdgeType,
    EvidenceClass,
    EvidenceGraphBuilder,
    NodeType,
    load_from_dict,
    to_awareness_summary,
    to_json,
    to_markdown,
)


def test_complete_graph_construction(complete_manifest_data: dict):
    """Verify that a complete manifest produces all 9 node types and linkages."""
    graph = load_from_dict(complete_manifest_data)

    # 1. Assert all 9 node types exist in the projection
    node_types_present = {n.node_type for n in graph.nodes.values()}
    for expected_type in NodeType:
        assert expected_type.value in node_types_present, f"Missing expected node type: {expected_type.value}"

    # 2. Check specific canonical entities
    src = graph.get_node("src-2024-001")
    assert src is not None
    assert src.node_type == NodeType.SOURCE_SNAPSHOT.value
    assert "NO_CLINICAL_CLAIM" in src.safety_labels
    assert "NO_ONTOLOGY_PROMOTION" in src.safety_labels

    clm = graph.get_node("clm-topo-01")
    assert clm is not None
    assert clm.node_type == NodeType.CLAIM.value

    hyp = graph.get_node("hyp-triadic-01")
    assert hyp is not None
    assert hyp.node_type == NodeType.HYPOTHESIS.value
    assert hyp.properties.get("feature_family") == "triadic_hypergraph"

    exp = graph.get_node("exp-triadic-01")
    assert exp is not None
    assert exp.node_type == NodeType.EXPERIMENT.value

    run = graph.get_node("run-triadic-001")
    assert run is not None
    assert run.node_type == NodeType.RUN.value

    # Check generated artifacts
    art_summary = graph.get_node("art:run-triadic-001:summary.json")
    assert art_summary is not None
    assert art_summary.node_type == NodeType.ARTIFACT.value

    val = graph.get_node("val-falsification-01")
    assert val is not None
    assert val.node_type == NodeType.VALIDATION.value

    rev = graph.get_node("rev-2026-01")
    assert rev is not None
    assert rev.node_type == NodeType.THEORY_REVISION.value

    ev = graph.get_node("ev-emp-01")
    assert ev is not None
    assert ev.node_type == NodeType.EVIDENCE_RECORD.value
    assert ev.evidence_class == EvidenceClass.EMPIRICAL.value


def test_all_10_edge_types_supported():
    """Verify that all 10 edge types can be instantiated and linked cleanly."""
    builder = EvidenceGraphBuilder()

    # Add minimum required nodes
    builder.add_node(builder.build().get_node("n1") or graph_node("n1", NodeType.SOURCE_SNAPSHOT))
    builder.add_node(graph_node("n2", NodeType.CLAIM))
    builder.add_node(graph_node("n3", NodeType.HYPOTHESIS))
    builder.add_node(graph_node("n4", NodeType.EXPERIMENT))
    builder.add_node(graph_node("n5", NodeType.RUN))
    builder.add_node(graph_node("n6", NodeType.ARTIFACT))
    builder.add_node(graph_node("n7", NodeType.VALIDATION))
    builder.add_node(graph_node("n8", NodeType.THEORY_REVISION))

    # Link all 10 edge types
    builder.link(EdgeType.SUPPORTS, "n7", "n3", label="supports_hyp")
    builder.link(EdgeType.CONTRADICTS, "n7", "n2", label="contradicts_claim")
    builder.link(EdgeType.TESTS, "n4", "n3", label="tests_hyp")
    builder.link(EdgeType.GENERATED_BY, "n6", "n5", label="generated_by_run")
    builder.link(EdgeType.DERIVED_FROM, "n2", "n1", label="derived_from_src")
    builder.link(EdgeType.VALIDATES, "n7", "n5", label="validates_run")
    builder.link(EdgeType.REVISES, "n8", "n3", label="revises_hyp")
    builder.link(EdgeType.SUPERSEDES, "n8", "n3", label="supersedes_hyp")
    builder.link(EdgeType.BLOCKED_BY, "n3", "n4", label="blocked_by_exp")
    builder.link(EdgeType.REFERENCES, "n1", "n2", label="references_clm")

    graph = builder.build()
    edge_types_present = {e.edge_type for e in graph.edges}
    for expected_edge in EdgeType:
        assert expected_edge.value in edge_types_present, f"Missing edge type: {expected_edge.value}"


def test_serialization_and_markdown(complete_manifest_data: dict):
    """Verify JSON export, Markdown reporting, and Awareness Studio summary."""
    graph = load_from_dict(complete_manifest_data)

    # 1. Canonical JSON
    json_str = to_json(graph)
    parsed = json.loads(json_str)
    assert "nodes" in parsed
    assert "edges" in parsed
    assert "summary" in parsed
    assert parsed["summary"]["total_nodes"] > 0
    assert parsed["summary"]["graph_checksum"]

    # 2. Markdown report
    md_str = to_markdown(graph)
    assert "# Awareness Studio Evidence Graph Projection" in md_str
    assert "## Scientific Safety & Epistemic Boundaries" in md_str
    assert "## Node Distribution by Type" in md_str
    assert "## Entity Relationship Diagram" in md_str

    # 3. Awareness Studio summary
    summary_dict = to_awareness_summary(graph)
    assert summary_dict["ready_for_ingestion"] is True
    assert summary_dict["total_nodes"] == len(graph.nodes)
    assert summary_dict["total_edges"] == len(graph.edges)
    assert "scientific_guardrails" in summary_dict


def graph_node(node_id: str, node_type: NodeType):
    from awareness_studio.research_graph import GraphNode
    return GraphNode(node_id=node_id, node_type=node_type, label=f"Label {node_id}")
