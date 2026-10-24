"""Claim evidence-class classification: fail closed, provenance kept.

Regression: the loader must classify claims with the same rules as other records.
A bare ``evidence_class`` string is only trusted through ``_classify_evidence``,
which requires preregistration and a locked held-out split before FORMAL, and
rejects unknown class strings. Synthetic provenance must not be relabelled.
"""
from __future__ import annotations

from awareness_studio.research_graph.loader import load_from_dict, load_from_jsonl
from awareness_studio.research_graph.types import DiagnosticCode, EvidenceClass, NodeStatus


def _claim_node(claim: dict):
    graph = load_from_dict({"claims": [claim]})
    return graph.nodes[claim["claim_id"]]


def test_unpreregistered_formal_claim_is_not_formal():
    node = _claim_node(
        {"claim_id": "c-formal", "claim_text": "formal without preregistration",
         "evidence_class": "formal"}
    )
    assert node.evidence_class != EvidenceClass.FORMAL.value
    assert node.evidence_class == EvidenceClass.EMPIRICAL.value


def test_unknown_claim_evidence_class_string_is_not_passed_through():
    node = _claim_node(
        {"claim_id": "c-invalid", "claim_text": "invalid class", "evidence_class": "trusted"}
    )
    assert node.evidence_class == EvidenceClass.UNKNOWN.value


def test_synthetic_claim_keeps_synthetic_label():
    node = _claim_node(
        {"claim_id": "c-synth", "claim_text": "synthetic fixture", "is_synthetic": True}
    )
    assert node.evidence_class == EvidenceClass.SYNTHETIC.value


def test_validation_pass_is_pending_review_not_supported():
    graph = load_from_dict(
        {
            "claims": [{"claim_id": "c-x", "claim_text": "x"}],
            "validations": [{"validation_id": "v-pass", "verdict": "PASS", "target_id": "c-x"}],
        }
    )
    assert graph.nodes["v-pass"].status == NodeStatus.REVIEW_REQUIRED.value


def test_direct_source_snapshot_node_uses_source_gate():
    graph = load_from_dict({
        "nodes": [{
            "node_id": "src-direct",
            "node_type": "source_snapshot",
            "status": "active",
            "evidence_class": "unknown",
        }],
    })

    node = graph.nodes["src-direct"]
    assert node.evidence_class == EvidenceClass.UNKNOWN.value
    assert node.status == NodeStatus.REVIEW_REQUIRED.value


def test_direct_source_snapshot_without_status_does_not_default_active():
    graph = load_from_dict({
        "nodes": [{"node_id": "src-direct-default", "node_type": "source_snapshot"}],
    })

    assert graph.nodes["src-direct-default"].status == NodeStatus.REVIEW_REQUIRED.value


def test_string_false_preregistration_flags_do_not_promote_source():
    graph = load_from_dict({
        "sources": [{
            "source_id": "src-string-false",
            "title": "String false flags",
            "source_type": "journal_article",
            "status": "active",
            "evidence_class": "formal",
            "preregistered": "false",
            "held_out_split_locked": "false",
        }],
    })

    node = graph.nodes["src-string-false"]
    assert node.evidence_class == EvidenceClass.EMPIRICAL.value
    assert node.status == NodeStatus.REVIEW_REQUIRED.value
    assert any(
        diagnostic.code == DiagnosticCode.EMPIRICAL_CLAIM_WITHOUT_VERIFICATION.value
        for diagnostic in graph.diagnostics
    )


def test_direct_validation_node_pass_remains_pending():
    graph = load_from_dict({
        "nodes": [{
            "node_id": "val-direct-pass",
            "node_type": "validation",
            "status": "supported",
            "evidence_class": "formal",
            "properties": {"verdict": "PASS"},
        }],
    })

    node = graph.nodes["val-direct-pass"]
    assert node.status == NodeStatus.REVIEW_REQUIRED.value
    assert not any(
        edge.source_id == "val-direct-pass" and edge.edge_type == "supports"
        for edge in graph.edges
    )


def test_direct_source_snapshot_string_false_is_not_verified():
    graph = load_from_dict({
        "nodes": [{
            "node_id": "src-direct-false",
            "node_type": "source_snapshot",
            "status": "active",
            "evidence_class": "formal",
            "preregistered": "false",
            "held_out_split_locked": "false",
        }],
    })

    node = graph.nodes["src-direct-false"]
    assert node.evidence_class == EvidenceClass.EMPIRICAL.value
    assert node.status == NodeStatus.REVIEW_REQUIRED.value
    assert any(
        diagnostic.code == DiagnosticCode.EMPIRICAL_CLAIM_WITHOUT_VERIFICATION.value
        for diagnostic in graph.diagnostics
    )


def test_string_false_is_formal_flag_does_not_promote():
    graph = load_from_dict({
        "sources": [{
            "source_id": "src-formal-flag-false",
            "title": "String false formal flag",
            "status": "active",
            "is_formal": "false",
            "preregistered": True,
            "held_out_split_locked": True,
        }],
    })

    node = graph.nodes["src-formal-flag-false"]
    assert node.evidence_class == EvidenceClass.UNKNOWN.value
    assert node.status == NodeStatus.REVIEW_REQUIRED.value


def test_jsonl_source_snapshot_uses_source_gate():
    graph = load_from_jsonl(
        '{"node_id":"src-jsonl","node_type":"source_snapshot",'
        '"evidence_class":"unknown","status":"active"}'
    )

    assert graph.nodes["src-jsonl"].status == NodeStatus.REVIEW_REQUIRED.value
