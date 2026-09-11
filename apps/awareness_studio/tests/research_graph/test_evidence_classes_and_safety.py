"""Tests for evidence class classification, safety labels, and promotion guardrails."""
from __future__ import annotations

from awareness_studio.research_graph import (
    DiagnosticCode,
    DiagnosticSeverity,
    EvidenceClass,
    EvidenceGraphBuilder,
    GraphNode,
    NodeStatus,
    NodeType,
    SafetyLabel,
    load_from_dict,
)


def test_synthetic_evidence_labeling_and_formal_violation():
    """Verify synthetic evidence receives SYNTHETIC_ONLY and cannot claim formal class."""
    manifest = {
        "evidence": [
            {
                "evidence_id": "ev-sim-001",
                "hypothesis_id": "hyp-001",
                "data_mode": "synthetic",
                "is_synthetic": True,
            }
        ]
    }
    graph = load_from_dict(manifest)
    ev_node = graph.get_node("ev-sim-001")
    assert ev_node is not None
    assert ev_node.evidence_class == EvidenceClass.SYNTHETIC.value
    assert SafetyLabel.SYNTHETIC_ONLY.value in ev_node.safety_labels

    # Violation: synthetic claiming formal
    builder = EvidenceGraphBuilder()
    builder.add_node(
        GraphNode(
            node_id="ev-fraudulent-formal",
            node_type=NodeType.EVIDENCE_RECORD.value,
            label="Fake Formal Evidence",
            evidence_class=EvidenceClass.FORMAL.value,
            properties={"is_synthetic": True},
        )
    )
    graph_viol = builder.build()
    synth_errors = [d for d in graph_viol.diagnostics if d.code == DiagnosticCode.SYNTHETIC_FORMAL_VIOLATION.value]
    assert len(synth_errors) == 1
    assert synth_errors[0].severity == DiagnosticSeverity.ERROR.value


def test_proxy_evidence_labeling_and_formal_violation():
    """Verify proxy metrics receive PROXY_METRIC and cannot claim formal status."""
    manifest = {
        "evidence": [
            {
                "evidence_id": "ev-proxy-001",
                "hypothesis_id": "hyp-001",
                "data_type": "proxy_bayes_factor",
                "is_proxy": True,
            }
        ]
    }
    graph = load_from_dict(manifest)
    ev_node = graph.get_node("ev-proxy-001")
    assert ev_node is not None
    assert ev_node.evidence_class == EvidenceClass.PROXY.value
    assert SafetyLabel.PROXY_METRIC.value in ev_node.safety_labels

    # Violation: proxy claiming formal
    builder = EvidenceGraphBuilder()
    builder.add_node(
        GraphNode(
            node_id="ev-fraud-proxy-formal",
            node_type=NodeType.EVIDENCE_RECORD.value,
            label="Proxy Claiming Formal",
            evidence_class=EvidenceClass.FORMAL.value,
            properties={"is_proxy": True},
        )
    )
    graph_viol = builder.build()
    proxy_errors = [d for d in graph_viol.diagnostics if d.code == DiagnosticCode.PROXY_FORMAL_VIOLATION.value]
    assert len(proxy_errors) == 1
    assert proxy_errors[0].severity == DiagnosticSeverity.ERROR.value


def test_no_claim_promotion_without_human_review():
    """Verify that claiming 'supported' without human review triggers UNSUPPORTED_PROMOTION."""
    builder = EvidenceGraphBuilder()
    # Hypothesis claiming supported without human review
    builder.add_node(
        GraphNode(
            node_id="hyp-unreviewed-promotion",
            node_type=NodeType.HYPOTHESIS.value,
            label="Prematurely Supported Hypothesis",
            status=NodeStatus.SUPPORTED.value,
            properties={"human_review_gate": {"passed": False}},
        )
    )
    graph = builder.build()
    promotion_errors = [
        d for d in graph.diagnostics
        if d.code == DiagnosticCode.UNSUPPORTED_PROMOTION.value
    ]
    assert len(promotion_errors) == 1
    assert promotion_errors[0].severity == DiagnosticSeverity.ERROR.value

    # Check that REVIEW_REQUIRED was attached
    hyp_node = graph.get_node("hyp-unreviewed-promotion")
    assert hyp_node is not None
    assert SafetyLabel.REVIEW_REQUIRED.value in hyp_node.safety_labels

    # Valid human review passes
    builder_valid = EvidenceGraphBuilder()
    builder_valid.add_node(
        GraphNode(
            node_id="hyp-reviewed",
            node_type=NodeType.HYPOTHESIS.value,
            label="Reviewed Hypothesis",
            status=NodeStatus.SUPPORTED.value,
            properties={"human_review_gate": {"passed": True, "reviewer": "Prof. Smith"}},
        )
    )
    graph_valid = builder_valid.build()
    no_errors = [
        d for d in graph_valid.diagnostics
        if d.code == DiagnosticCode.UNSUPPORTED_PROMOTION.value
    ]
    assert len(no_errors) == 0


def test_evidence_class_filtering():
    """Verify that filtering by evidence class isolates requested tiers."""
    manifest = {
        "hypotheses": [{"hypothesis_id": "hyp-001", "precise_claim": "Claim 1"}],
        "evidence": [
            {
                "evidence_id": "ev-synthetic-1",
                "hypothesis_id": "hyp-001",
                "data_mode": "synthetic",
                "is_synthetic": True,
            },
            {
                "evidence_id": "ev-empirical-1",
                "hypothesis_id": "hyp-001",
                "data_mode": "empirical",
                "is_synthetic": False,
            }
        ]
    }
    graph = load_from_dict(manifest)
    assert len(graph.nodes) == 3

    # Filter strictly for empirical
    filtered_graph = graph.filter_by_evidence_class([EvidenceClass.EMPIRICAL])
    assert "ev-empirical-1" in filtered_graph.nodes
    assert "ev-synthetic-1" not in filtered_graph.nodes
    assert "hyp-001" in filtered_graph.nodes  # Hypothesis retained as non-evidence node
