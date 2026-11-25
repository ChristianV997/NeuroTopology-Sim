"""Fixture-only RAG pack for promotion-gate reports. No live retrieval."""

from __future__ import annotations

from typing import Any, Mapping


def build_pack(report: Mapping[str, Any]) -> dict[str, Any]:
    documents = []
    for item in report.get("results") or []:
        documents.append(
            {
                "id": item.get("case_id"),
                "safe": True,
                "promotion_decision": item.get("promotion_decision"),
                "allowed_evidence_class": item.get("allowed_evidence_class"),
                "synthetic_demo": item.get("synthetic_demo"),
                "scientific_pass": False,
                "text": (
                    f"Case {item.get('case_id')} is held at {item.get('promotion_decision')}. "
                    "This is a promotion gate, not scientific confirmation."
                ),
            }
        )
    return {
        "schema_version": "EvidencePromotionGate.RAGPack.v1",
        "scientific_pass": False,
        "forbidden_answer_patterns": [
            "proves consciousness",
            "clinical treatment",
            "Q proves",
            "empirical confirmation",
            "TOE validated",
        ],
        "public_answer_guidelines": (
            "No proof, diagnosis, treatment, ontology promotion, or empirical "
            "confirmation claims. Synthetic and proxy records stay non-empirical."
        ),
        "documents": documents,
        "query_examples": [
            {
                "query": "Did this gate confirm the hypothesis empirically?",
                "answer": "No. The promotion gate never emits scientific PASS or empirical confirmation.",
            },
            {
                "query": "Can a synthetic RunRecord become EMPIRICAL in RAG?",
                "answer": "No. Synthetic, fixture, null, surrogate, and performance_only records are held or blocked.",
            },
        ],
    }
