"""Claim evidence-class classification: fail closed, provenance kept.

Regression: the loader must classify claims with the same rules as other records.
A bare ``evidence_class`` string is only trusted through ``_classify_evidence``,
which requires preregistration and a locked held-out split before FORMAL, and
rejects unknown class strings. Synthetic provenance must not be relabelled.
"""
from __future__ import annotations

from awareness_studio.research_graph.loader import load_from_dict
from awareness_studio.research_graph.types import EvidenceClass, NodeStatus


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
