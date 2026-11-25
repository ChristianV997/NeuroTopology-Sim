"""Diagnostics unit tests for evidence graph integrity and conflict detection."""
from __future__ import annotations

from awareness_studio.research_graph import (
    DiagnosticCode,
    DiagnosticSeverity,
    EdgeType,
    EvidenceGraphBuilder,
    GraphNode,
    NodeStatus,
    NodeType,
    SafetyLabel,
    load_from_dict,
)


def test_orphan_artifact_detection():
    """Verify that an artifact with no incoming or outgoing edges emits ORPHAN_ARTIFACT."""
    builder = EvidenceGraphBuilder()
    builder.add_node(
        GraphNode(
            node_id="art:detached:results.csv",
            node_type=NodeType.ARTIFACT.value,
            label="Detached Results CSV",
        )
    )
    graph = builder.build()

    orphan_diags = [d for d in graph.diagnostics if d.code == DiagnosticCode.ORPHAN_ARTIFACT.value]
    assert len(orphan_diags) == 1
    assert orphan_diags[0].severity == DiagnosticSeverity.WARNING.value
    assert "art:detached:results.csv" in orphan_diags[0].affected_ids


def test_missing_source_and_dangling_edge():
    """Verify that an edge pointing to a non-existent target or source emits DANGLING_EDGE."""
    builder = EvidenceGraphBuilder()
    builder.add_node(
        GraphNode(
            node_id="hyp-001",
            node_type=NodeType.HYPOTHESIS.value,
            label="Test Hypothesis",
        )
    )
    # Edge with missing target
    builder.link(EdgeType.DERIVED_FROM, "hyp-001", "src-non-existent")
    # Edge with missing source
    builder.link(EdgeType.SUPPORTS, "ev-ghost", "hyp-001")

    graph = builder.build()

    dangling_targets = [d for d in graph.diagnostics if d.code == DiagnosticCode.DANGLING_EDGE_TARGET.value]
    assert len(dangling_targets) == 1
    assert "src-non-existent" in dangling_targets[0].affected_ids
    assert dangling_targets[0].severity == DiagnosticSeverity.ERROR.value

    dangling_sources = [d for d in graph.diagnostics if d.code == DiagnosticCode.DANGLING_EDGE_SOURCE.value]
    assert len(dangling_sources) == 1
    assert "ev-ghost" in dangling_sources[0].affected_ids
    assert dangling_sources[0].severity == DiagnosticSeverity.ERROR.value


def test_duplicate_node_detection():
    """Verify exact duplicate vs content mismatch handling."""
    builder = EvidenceGraphBuilder()
    n1 = GraphNode(node_id="hyp-001", node_type=NodeType.HYPOTHESIS.value, label="Original Hypothesis")
    n1_copy = GraphNode(node_id="hyp-001", node_type=NodeType.HYPOTHESIS.value, label="Original Hypothesis")
    n1_altered = GraphNode(node_id="hyp-001", node_type=NodeType.HYPOTHESIS.value, label="Altered Contradictory Claim")

    # Add exact duplicate
    builder.add_node(n1)
    builder.add_node(n1_copy)
    graph = builder.build()

    exact_dups = [d for d in graph.diagnostics if d.code == DiagnosticCode.DUPLICATE_NODE_EXACT.value]
    assert len(exact_dups) == 1
    assert exact_dups[0].severity == DiagnosticSeverity.INFO.value

    # Add conflicting duplicate
    builder.add_node(n1_altered)
    graph2 = builder.build()

    mismatches = [d for d in graph2.diagnostics if d.code == DiagnosticCode.DUPLICATE_NODE_CONTENT_MISMATCH.value]
    assert len(mismatches) == 1
    assert mismatches[0].severity == DiagnosticSeverity.ERROR.value


def test_conflicting_statuses_detection():
    """Verify detection when contradictory and supporting evidence target the same hypothesis."""
    manifest = {
        "hypotheses": [
            {
                "hypothesis_id": "hyp-contested",
                "precise_claim": "Topological Betti-1 stability is altered under stress.",
            }
        ],
        "evidence": [
            {
                "evidence_id": "ev-support-1",
                "hypothesis_id": "hyp-contested",
                "data_type": "empirical_dataset",
                "is_contradictory": False,
            },
            {
                "evidence_id": "ev-contradict-1",
                "hypothesis_id": "hyp-contested",
                "data_type": "empirical_dataset",
                "is_contradictory": True,
            }
        ]
    }
    graph = load_from_dict(manifest)

    conflicts = [d for d in graph.diagnostics if d.code == DiagnosticCode.CONFLICTING_STATUS.value]
    assert len(conflicts) >= 1
    assert "hyp-contested" in conflicts[0].affected_ids

    # Check that safety labels were automatically attached to the contested hypothesis
    hyp_node = graph.get_node("hyp-contested")
    assert hyp_node is not None
    assert SafetyLabel.INCONCLUSIVE.value in hyp_node.safety_labels
    assert SafetyLabel.REVIEW_REQUIRED.value in hyp_node.safety_labels


def test_failed_validation_linked_to_supports_error():
    """Verify that a FAIL validation linked via 'supports' triggers an ERROR diagnostic."""
    builder = EvidenceGraphBuilder()
    builder.add_node(
        GraphNode(
            node_id="val-failed-check",
            node_type=NodeType.VALIDATION.value,
            label="Null Hypothesis Permutation Test",
            status=NodeStatus.FALSIFIED.value,
            properties={"verdict": "FAIL"},
        )
    )
    builder.add_node(
        GraphNode(
            node_id="hyp-target",
            node_type=NodeType.HYPOTHESIS.value,
            label="Hypothesis Under Test",
        )
    )
    builder.link(EdgeType.SUPPORTS, "val-failed-check", "hyp-target")
    graph = builder.build()

    conflict_errors = [
        d for d in graph.diagnostics
        if d.code == DiagnosticCode.CONFLICTING_STATUS.value and d.severity == DiagnosticSeverity.ERROR.value
    ]
    assert len(conflict_errors) == 1
    assert "non-passing verdict 'FAIL'" in conflict_errors[0].message


def test_superseded_hypothesis_unlinked_warning():
    """Verify that a node marked 'superseded' with no supersedes edge emits SUPERSEDED_UNLINKED."""
    builder = EvidenceGraphBuilder()
    builder.add_node(
        GraphNode(
            node_id="hyp-deprecated",
            node_type=NodeType.HYPOTHESIS.value,
            label="Deprecated Hypothesis",
            status=NodeStatus.SUPERSEDED.value,
        )
    )
    graph = builder.build()

    superseded_diags = [d for d in graph.diagnostics if d.code == DiagnosticCode.SUPERSEDED_UNLINKED.value]
    assert len(superseded_diags) == 1
    assert superseded_diags[0].severity == DiagnosticSeverity.WARNING.value
