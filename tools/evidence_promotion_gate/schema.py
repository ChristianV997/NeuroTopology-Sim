"""Closed vocabularies and result types for EvidencePromotionGate.v1.

This package is a reporting/promotion gate. It does not confirm science,
emit a scientific PASS, or promote any record to empirical evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

SCHEMA_VERSION = "EvidencePromotionGate.v1"

PROMOTION_DECISIONS: tuple[str, ...] = (
    "HOLD_SYNTHETIC_ONLY",
    "HOLD_PROXY_ONLY",
    "HOLD_LITERATURE_HYPOTHESIS",
    "HOLD_INCOMPLETE_PROVENANCE",
    "HOLD_INCONCLUSIVE",
    "BLOCK_PROMOTION",
    "ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW",
    "ADMISSIBLE_FOR_ENGINEERING_REPORT",
)

# Never includes EMPIRICAL. Descriptive review is not confirmation.
ALLOWED_EVIDENCE_CLASSES: tuple[str, ...] = (
    "engineering_fact",
    "benchmark_result",
    "synthetic_demonstration",
    "descriptive_empirical",
    "proxy_inference",
    "hypothesis",
    "speculation",
    "unsupported_claim",
)

ARTIFACT_KINDS: tuple[str, ...] = (
    "run_record",
    "claim",
    "claim_gate_result",
    "rag_markdown",
    "command_center",
    "airtable_card",
    "research_cycle",
    "literature",
    "unknown",
)

DOWNSTREAM_KINDS: frozenset[str] = frozenset(
    {"rag_markdown", "command_center", "airtable_card", "research_cycle"}
)

SYNTHETIC_TOKENS: frozenset[str] = frozenset(
    {
        "synthetic",
        "synthetic_demo",
        "synthetic_demonstration",
        "fixture",
        "null",
        "surrogate",
        "performance_only",
        "null_control",
        "surrogate_baseline",
    }
)

PROXY_METHOD_TOKENS: frozenset[str] = frozenset(
    {
        "proxy",
        "aic",
        "aicc",
        "bic",
        "rss",
        "aic_ratio",
        "aicc_ratio",
        "bic_ratio",
        "regression_proxy",
        "proxy_bayes_factor",
        "bayes_factor_proxy",
        "information_criterion",
    }
)

FORMAL_METHOD_TOKENS: frozenset[str] = frozenset(
    {
        "formal",
        "formal_bayes_factor",
        "marginal_likelihood",
        "validated_likelihood",
        "formal_marginal_likelihood",
    }
)

LITERATURE_CLAIM_KINDS: frozenset[str] = frozenset({"hypothesis", "review_required"})
LITERATURE_EVIDENCE_CLASSES: frozenset[str] = frozenset(
    {"hypothesis", "theoretical", "review_required", "proxy"}
)

UNSAFE_EVIDENCE_LABELS: frozenset[str] = frozenset(
    {"empirical", "EMPIRICAL", "confirmed", "CONFIRMED"}
)

REASON_CODES: tuple[str, ...] = (
    "INPUT_NOT_OBJECT",
    "MALFORMED_INPUT",
    "EMPTY_INPUT",
    "SYNTHETIC_NOT_EMPIRICAL",
    "SYNTHETIC_DEMO_ONLY",
    "PERFORMANCE_ONLY_NOT_EMPIRICAL",
    "FIXTURE_NOT_EMPIRICAL",
    "NULL_SURROGATE_NOT_EMPIRICAL",
    "PROXY_NOT_FORMAL_BAYESIAN",
    "PROXY_K_NOT_EMPIRICAL",
    "LITERATURE_HYPOTHESIS_NOT_EMPIRICAL",
    "LITERATURE_REVIEW_REQUIRED",
    "MISSING_PROVENANCE",
    "INCOMPLETE_PROVENANCE",
    "INVALID_PROVENANCE",
    "UNKNOWN_N_TESTS",
    "UNKNOWN_MULTIPLICITY",
    "MISSING_NULL_CONTROLS",
    "DOWNSTREAM_UNSAFE_PASS",
    "DOWNSTREAM_UNSAFE_EMPIRICAL",
    "EMPIRICAL_PROMOTION_REFUSED",
    "SCIENTIFIC_PASS_NOT_EMITTED",
    "FORMAL_BAYES_FACTOR_NOT_CONFIRMATION",
    "K_EQUALS_100_NOT_PASS",
    "CLAIM_GATE_SYNTHETIC_ONLY",
    "CLAIM_GATE_REJECTED",
    "CLAIM_GATE_REVIEW",
    "CLAIM_GATE_PROVENANCE_INVALID",
    "CLAIM_GATE_DOWNGRADED",
    "CLAIM_GATE_INCOMPLETE",
    "NETWORK_ACCESS_NOT_APPROVED",
    "NON_FINITE_VALUE",
    "DATASET_LICENSE_EVIDENCE_MISSING",
    "DATASET_LICENSE_EVIDENCE_CONFLICT",
    "DATASET_LICENSE_EVIDENCE_UNRESOLVED",
    "DATASET_COHORT_EVIDENCE_MISSING",
    "DATASET_COHORT_EVIDENCE_CONFLICT",
    "DATASET_COHORT_EVIDENCE_UNRESOLVED",
    "DATASET_COHORT_DISCREPANCY",
)

DECISION_TO_ALLOWED_CLASS: dict[str, str] = {
    "HOLD_SYNTHETIC_ONLY": "synthetic_demonstration",
    "HOLD_PROXY_ONLY": "proxy_inference",
    "HOLD_LITERATURE_HYPOTHESIS": "hypothesis",
    "HOLD_INCOMPLETE_PROVENANCE": "hypothesis",
    "HOLD_INCONCLUSIVE": "hypothesis",
    "BLOCK_PROMOTION": "unsupported_claim",
    "ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW": "descriptive_empirical",
    "ADMISSIBLE_FOR_ENGINEERING_REPORT": "engineering_fact",
}


@dataclass(frozen=True)
class Reason:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "message": self.message}


@dataclass(frozen=True)
class PromotionResult:
    """Stable output contract. scientific_pass is always false."""

    schema_version: str
    case_id: str
    promotion_decision: str
    reason_codes: tuple[str, ...]
    reasons: tuple[Reason, ...]
    declared_evidence_class: str | None
    allowed_evidence_class: str
    synthetic_demo: bool
    scientific_pass: bool
    scientific_eligibility: bool
    formal_bayes_factor: float | None
    declared_formal_bayes_factor: float | None
    claim_gate: Mapping[str, Any] | None
    input_fingerprints: Mapping[str, Any]
    artifact_kinds: tuple[str, ...] = ()
    data_mode: str | None = None
    network_access_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "promotion_decision": self.promotion_decision,
            "reason_codes": list(self.reason_codes),
            "reasons": [reason.to_dict() for reason in self.reasons],
            "declared_evidence_class": self.declared_evidence_class,
            "allowed_evidence_class": self.allowed_evidence_class,
            "synthetic_demo": self.synthetic_demo,
            "scientific_pass": False,
            "scientific_eligibility": self.scientific_eligibility,
            "formal_bayes_factor": self.formal_bayes_factor,
            "declared_formal_bayes_factor": self.declared_formal_bayes_factor,
            "claim_gate": dict(self.claim_gate) if self.claim_gate is not None else None,
            "input_fingerprints": dict(self.input_fingerprints),
            "artifact_kinds": list(self.artifact_kinds),
            "data_mode": self.data_mode,
            "network_access_performed": False,
        }
