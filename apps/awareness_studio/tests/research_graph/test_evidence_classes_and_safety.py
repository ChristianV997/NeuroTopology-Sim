"""Tests for evidence class classification, safety labels, and promotion guardrails."""
from __future__ import annotations

import pytest

from awareness_studio.research_graph import (
    DiagnosticCode,
    DiagnosticSeverity,
    EdgeType,
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


def test_missing_validation_verdict_is_not_promoted_to_pass():
    graph = load_from_dict({
        "validations": [{"validation_id": "val-missing", "hypothesis_id": "hyp-1"}],
    })
    node = graph.get_node("val-missing")
    assert node is not None
    assert node.status == NodeStatus.REVIEW_REQUIRED.value
    assert node.evidence_class == EvidenceClass.UNKNOWN.value
    assert not any(edge.source_id == "val-missing" and edge.edge_type == EdgeType.SUPPORTS.value for edge in graph.edges)


def test_source_with_no_evidence_signal_is_not_silently_empirical():
    """Regression test: load_from_dict used to hardcode evidence_class=EMPIRICAL
    for every source_snapshot node regardless of its actual data, silently
    promoting any literature/data source (e.g. a hypothesis-tier source from
    tools.literature_evidence) to empirical status. A source manifest that
    carries no recognized evidence signal at all must classify as UNKNOWN,
    never as an unearned EMPIRICAL."""
    manifest = {
        "sources": [
            {"source_id": "src-no-signal", "title": "An Unclassified Source"},
        ]
    }
    graph = load_from_dict(manifest)
    node = graph.get_node("src-no-signal")
    assert node is not None
    assert node.evidence_class == EvidenceClass.UNKNOWN.value


def test_source_declaring_synthetic_data_mode_is_classified_synthetic():
    manifest = {
        "sources": [
            {"source_id": "src-synth", "title": "A Synthetic-Data Source", "data_mode": "synthetic"},
        ]
    }
    graph = load_from_dict(manifest)
    node = graph.get_node("src-synth")
    assert node is not None
    assert node.evidence_class == EvidenceClass.SYNTHETIC.value


def test_source_claiming_empirical_without_verification_is_flagged():
    """A source_snapshot with evidence_class=empirical and nothing in its own
    properties corroborating that (no verification_status/peer_review_status/
    review_status/preregistered+held_out_split_locked signal) is an
    unsupported promotion -- flagged, never silently trusted."""
    manifest = {
        "sources": [
            {"source_id": "src-unverified-empirical", "title": "X", "evidence_class": "empirical"},
        ]
    }
    graph = load_from_dict(manifest)
    node = graph.get_node("src-unverified-empirical")
    assert node is not None
    assert node.evidence_class == EvidenceClass.EMPIRICAL.value
    assert node.status == NodeStatus.REVIEW_REQUIRED.value
    violations = [
        d for d in graph.diagnostics if d.code == DiagnosticCode.EMPIRICAL_CLAIM_WITHOUT_VERIFICATION.value
    ]
    assert len(violations) == 1
    assert violations[0].severity == DiagnosticSeverity.ERROR.value
    assert violations[0].affected_ids == ("src-unverified-empirical",)


def test_source_claiming_empirical_with_verification_is_not_flagged():
    manifest = {
        "sources": [
            {
                "source_id": "src-verified-empirical",
                "title": "X",
                "evidence_class": "empirical",
                "verification_status": "verified",
            },
        ]
    }
    graph = load_from_dict(manifest)
    node = graph.get_node("src-verified-empirical")
    assert node is not None
    assert node.status == NodeStatus.ACTIVE.value
    violations = [
        d for d in graph.diagnostics if d.code == DiagnosticCode.EMPIRICAL_CLAIM_WITHOUT_VERIFICATION.value
    ]
    assert violations == []


def test_source_claiming_formal_without_verification_is_flagged():
    manifest = {
        "sources": [
            {"source_id": "src-unverified-formal", "title": "X", "evidence_class": "formal"},
        ]
    }
    graph = load_from_dict(manifest)
    node = graph.get_node("src-unverified-formal")
    assert node is not None
    assert node.status == NodeStatus.REVIEW_REQUIRED.value
    violations = [
        d for d in graph.diagnostics if d.code == DiagnosticCode.EMPIRICAL_CLAIM_WITHOUT_VERIFICATION.value
    ]
    assert len(violations) == 1


def test_source_with_hypothesis_evidence_class_is_never_flagged_as_unsupported_promotion():
    """A source honestly declaring evidence_class=hypothesis (e.g. bridged
    from tools.literature_evidence, which never emits empirical/formal at
    all) must never trip this guardrail -- only an EMPIRICAL/FORMAL claim
    without corroboration does."""
    manifest = {
        "sources": [
            {"source_id": "src-hypothesis", "title": "X", "evidence_class": "hypothesis"},
        ]
    }
    graph = load_from_dict(manifest)
    node = graph.get_node("src-hypothesis")
    assert node is not None
    assert node.evidence_class == EvidenceClass.UNKNOWN.value  # "hypothesis" is not a research_graph EvidenceClass value
    violations = [
        d for d in graph.diagnostics if d.code == DiagnosticCode.EMPIRICAL_CLAIM_WITHOUT_VERIFICATION.value
    ]
    assert violations == []


def test_claim_with_unrecognized_evidence_class_is_not_passed_through_unchecked():
    """Regression test: the claims loading path used to pass whatever
    string a manifest supplied straight through as evidence_class with no
    validation at all (unlike every other section, which already used
    _classify_evidence). A claim declaring a non-research_graph value
    (e.g. "hypothesis", from a bridged literature claim) must classify as
    UNKNOWN, never be accepted verbatim as an unrecognized evidence_class
    string on the node."""
    manifest = {
        "claims": [
            {"claim_id": "clm-unchecked", "source_id": "src-1", "claim_text": "X", "evidence_class": "hypothesis"},
        ]
    }
    graph = load_from_dict(manifest)
    node = graph.get_node("clm-unchecked")
    assert node is not None
    assert node.evidence_class == EvidenceClass.UNKNOWN.value


def test_claim_declaring_recognized_evidence_class_still_classifies_correctly():
    manifest = {
        "claims": [
            {"claim_id": "clm-proxy", "source_id": "src-1", "claim_text": "X", "evidence_class": "proxy"},
        ]
    }
    graph = load_from_dict(manifest)
    node = graph.get_node("clm-proxy")
    assert node is not None
    assert node.evidence_class == EvidenceClass.PROXY.value


def test_source_without_evidence_signal_is_review_required_not_active():
    graph = load_from_dict({
        "sources": [
            {"source_id": "src-bare", "title": "Bare Source", "source_type": "journal_article"},
        ],
    })

    node = graph.get_node("src-bare")
    assert node is not None
    assert node.evidence_class == EvidenceClass.UNKNOWN.value
    assert node.status == NodeStatus.REVIEW_REQUIRED.value


@pytest.mark.parametrize("declared", ["rejected", "falsified", "contradicted", "weakened", "inconclusive"])
def test_negative_source_status_is_kept_without_evidence_signal(declared):
    # Regression: _source_status downgraded every declared status outside disputed/retracted/superseded to
    # review_required. A source declared rejected or falsified then read as merely pending review. main keeps it.
    graph = load_from_dict({
        "sources": [
            {"source_id": "src-negative", "title": "Negative Source", "source_type": "journal_article", "status": declared},
        ],
    })

    node = graph.get_node("src-negative")
    assert node is not None
    assert node.status == declared


@pytest.mark.parametrize("declared", [None, "", "   "])
def test_missing_source_status_is_review_required_not_a_literal_string(declared):
    # Regression: an explicit null status was stringified to the literal "None" and escaped the downgrade.
    graph = load_from_dict({
        "sources": [
            {"source_id": "src-blank", "title": "Blank Status", "source_type": "journal_article", "status": declared},
        ],
    })

    node = graph.get_node("src-blank")
    assert node is not None
    assert node.status == NodeStatus.REVIEW_REQUIRED.value


@pytest.mark.parametrize("declared", ["active", "proposed", "provisional", "supported"])
def test_unverified_positive_source_status_is_downgraded_without_evidence_signal(declared):
    graph = load_from_dict({
        "sources": [
            {"source_id": "src-positive", "title": "Positive Source", "source_type": "journal_article", "status": declared},
        ],
    })

    node = graph.get_node("src-positive")
    assert node is not None
    assert node.status == NodeStatus.REVIEW_REQUIRED.value


def test_unrecognized_source_status_cannot_claim_empirical_verification():
    graph = load_from_dict({
        "sources": [
            {
                "source_id": "src-unrecognized-status",
                "title": "Unrecognized Status Source",
                "data_mode": "empirical",
                "status": "verified",
            },
        ],
    })

    node = graph.get_node("src-unrecognized-status")
    assert node is not None
    assert node.evidence_class == EvidenceClass.EMPIRICAL.value
    assert node.status == NodeStatus.REVIEW_REQUIRED.value


def test_pass_validation_stays_pending_without_independent_adjudication():
    graph = load_from_dict({
        "validations": [
            {
                "validation_id": "val-self-attested-pass",
                "hypothesis_id": "hyp-001",
                "verdict": "PASS",
                "data_mode": "empirical",
                "evidence_class": "formal",
                "preregistered": True,
                "held_out_split_locked": True,
                "provenance_status": "complete",
                "artifact_lineage_complete": True,
                "labels_verified": True,
                "null_models_complete": True,
                "multiplicity_corrected": True,
                "human_review_gate": {"passed": True, "reviewer": "fixture-reviewer"},
            },
            {
                "validation_id": "val-synthetic-pass",
                "hypothesis_id": "hyp-001",
                "verdict": "PASS",
                "data_mode": "synthetic",
                "is_synthetic": True,
            },
        ],
    })

    for validation_id in ("val-self-attested-pass", "val-synthetic-pass"):
        node = graph.get_node(validation_id)
        assert node is not None
        assert node.status == NodeStatus.REVIEW_REQUIRED.value
        assert SafetyLabel.REVIEW_REQUIRED.value in node.safety_labels
        assert not any(
            edge.source_id == validation_id and edge.edge_type == EdgeType.SUPPORTS.value
            for edge in graph.edges
        )

    synthetic = graph.get_node("val-synthetic-pass")
    assert synthetic is not None
    assert synthetic.evidence_class == EvidenceClass.SYNTHETIC.value
    assert SafetyLabel.SYNTHETIC_ONLY.value in synthetic.safety_labels
