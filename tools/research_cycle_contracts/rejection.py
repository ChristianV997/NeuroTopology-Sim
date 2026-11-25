"""Rejection rules and validation policies for research cycle contracts.

Rejection policies:
1. missing_source_provenance: missing or empty provenance/source identity.
2. unsupported_promotion: claiming supported status without human review or evidence.
3. synthetic_empirical_claims: synthetic simulations masquerading as biological/empirical proof.
4. missing_falsification_criteria: hypothesis lacking explicit falsification threshold.
5. missing_null_prediction: hypothesis lacking explicit null outcome prediction.
6. incompatible_feature_families: unrecognized or unauthorized feature family representation.
7. unverified_formal_status: proxy or heuristic metrics claiming formal evidence status.
"""
from __future__ import annotations

from typing import Any

from .models import (
    EvidenceUpdateV1,
    ExperimentLedgerRowV1,
    HypothesisRecordV1,
    RejectionReasonCode,
    SupportedFeatureFamily,
)


class ContractCompatibilityError(Exception):
    """Base exception for research cycle contract compatibility issues."""
    pass


class ContractRejectionError(ContractCompatibilityError):
    """Exception raised when a contract violates non-negotiable verification gates."""

    def __init__(self, reason_code: RejectionReasonCode | str, message: str) -> None:
        self.reason_code = (
            reason_code.value if isinstance(reason_code, RejectionReasonCode) else str(reason_code)
        )
        self.message = message
        super().__init__(f"[{self.reason_code}] {message}")


def validate_hypothesis_contract(hypothesis: HypothesisRecordV1) -> list[str]:
    """Validate a HypothesisRecordV1 against all non-negotiable contract rules.

    Returns a list of validation notices if valid; raises ContractRejectionError if rejected.
    """
    notices: list[str] = []

    # 1. Reject missing source provenance
    prov = hypothesis.provenance
    if not prov or not isinstance(prov, dict):
        raise ContractRejectionError(
            RejectionReasonCode.MISSING_SOURCE_PROVENANCE,
            f"Hypothesis '{hypothesis.hypothesis_id}' missing required provenance block.",
        )
    source_id = prov.get("source_id") or prov.get("creator") or prov.get("origin_source")
    if not source_id:
        raise ContractRejectionError(
            RejectionReasonCode.MISSING_SOURCE_PROVENANCE,
            f"Hypothesis '{hypothesis.hypothesis_id}' provenance lacks identifiable source_id or creator.",
        )
    notices.append("Provenance verified.")

    # 2. Reject missing null prediction
    null_pred = hypothesis.null_prediction
    if not null_pred or not str(null_pred).strip():
        raise ContractRejectionError(
            RejectionReasonCode.MISSING_NULL_PREDICTION,
            f"Hypothesis '{hypothesis.hypothesis_id}' lacks explicit null_prediction.",
        )
    notices.append("Null prediction verified.")

    # 3. Reject missing falsification criteria
    falsif = hypothesis.falsification_criterion
    if not falsif or not str(falsif).strip():
        raise ContractRejectionError(
            RejectionReasonCode.MISSING_FALSIFICATION_CRITERIA,
            f"Hypothesis '{hypothesis.hypothesis_id}' lacks explicit falsification_criterion.",
        )
    notices.append("Falsification criterion verified.")

    # 4. Reject incompatible feature families
    fam = hypothesis.feature_family
    valid_families = {f.value for f in SupportedFeatureFamily}
    if fam not in valid_families:
        raise ContractRejectionError(
            RejectionReasonCode.INCOMPATIBLE_FEATURE_FAMILIES,
            f"Hypothesis '{hypothesis.hypothesis_id}' specifies incompatible feature family '{fam}'. "
            f"Permitted families: {sorted(valid_families)}",
        )
    notices.append(f"Feature family '{fam}' compatible.")

    # 5. Reject unsupported promotion without human review gate
    if hypothesis.status == "supported_as_specified":
        gate = hypothesis.human_review_gate
        if not isinstance(gate, dict) or not gate.get("passed") or not gate.get("reviewer"):
            raise ContractRejectionError(
                RejectionReasonCode.UNSUPPORTED_PROMOTION,
                f"Hypothesis '{hypothesis.hypothesis_id}' claims 'supported_as_specified' but human review gate is unsigned.",
            )
        notices.append("Human review oversight confirmed.")

    return notices


def validate_evidence_contract(
    evidence: EvidenceUpdateV1,
    hypothesis: HypothesisRecordV1 | None = None,
) -> list[str]:
    """Validate an EvidenceUpdateV1 against empirical and epistemic gates.

    Raises ContractRejectionError if rejected.
    """
    notices: list[str] = []

    # 1. Reject missing source provenance
    prov = evidence.provenance
    if not prov or not isinstance(prov, dict):
        raise ContractRejectionError(
            RejectionReasonCode.MISSING_SOURCE_PROVENANCE,
            f"Evidence '{evidence.evidence_id}' missing required provenance block.",
        )
    if not evidence.source_checksum or not evidence.experiment_checksum:
        raise ContractRejectionError(
            RejectionReasonCode.MISSING_SOURCE_PROVENANCE,
            f"Evidence '{evidence.evidence_id}' missing source_checksum or experiment_checksum.",
        )
    notices.append("Evidence provenance and checksums verified.")

    # 2. Reject synthetic empirical claims
    if evidence.is_synthetic:
        if evidence.data_type == "empirical_dataset":
            raise ContractRejectionError(
                RejectionReasonCode.SYNTHETIC_EMPIRICAL_CLAIMS,
                f"Evidence '{evidence.evidence_id}' is synthetic simulation but claims data_type='empirical_dataset'.",
            )
        if hypothesis is not None and hypothesis.epistemic_label not in ("computational_model", "surrogate_baseline"):
            raise ContractRejectionError(
                RejectionReasonCode.SYNTHETIC_EMPIRICAL_CLAIMS,
                f"Evidence '{evidence.evidence_id}' is synthetic simulation but attached to biological/empirical "
                f"hypothesis '{hypothesis.hypothesis_id}' (epistemic_label='{hypothesis.epistemic_label}').",
            )
    notices.append("Synthetic evidence isolation verified.")

    # 3. Reject unverified formal status
    if evidence.data_type == "proxy_bayes_factor":
        raise ContractRejectionError(
            RejectionReasonCode.UNVERIFIED_FORMAL_STATUS,
            f"Evidence '{evidence.evidence_id}' carries proxy_bayes_factor which cannot serve as formal evidence.",
        )
    if evidence.data_type == "empirical_dataset" and not evidence.is_synthetic:
        if not evidence.dataset_ids or not any(str(d).strip() for d in evidence.dataset_ids):
            raise ContractRejectionError(
                RejectionReasonCode.UNVERIFIED_FORMAL_STATUS,
                f"Evidence '{evidence.evidence_id}' claims empirical_dataset status but provides no dataset_ids.",
            )
    notices.append("Formal evidence status verified.")

    return notices


def validate_ledger_row_contract(row: ExperimentLedgerRowV1) -> list[str]:
    """Validate an ExperimentLedgerRowV1 against registry ledger constraints."""
    notices: list[str] = []

    if not row.source_id or not str(row.source_id).strip():
        raise ContractRejectionError(
            RejectionReasonCode.MISSING_SOURCE_PROVENANCE,
            f"Ledger row '{row.row_id}' lacks valid source_id.",
        )

    if not row.falsification_threshold:
        raise ContractRejectionError(
            RejectionReasonCode.MISSING_FALSIFICATION_CRITERIA,
            f"Ledger row '{row.row_id}' lacks falsification_threshold.",
        )

    if not row.null_prediction:
        raise ContractRejectionError(
            RejectionReasonCode.MISSING_NULL_PREDICTION,
            f"Ledger row '{row.row_id}' lacks null_prediction.",
        )

    valid_families = {f.value for f in SupportedFeatureFamily}
    if row.feature_family not in valid_families:
        raise ContractRejectionError(
            RejectionReasonCode.INCOMPATIBLE_FEATURE_FAMILIES,
            f"Ledger row '{row.row_id}' specifies unsupported feature family '{row.feature_family}'.",
        )

    if row.outcome_status == "supported" and not row.reviewer_signoff:
        raise ContractRejectionError(
            RejectionReasonCode.UNSUPPORTED_PROMOTION,
            f"Ledger row '{row.row_id}' records supported outcome without reviewer_signoff.",
        )

    notices.append(f"Ledger row '{row.row_id}' passed contract validation.")
    return notices
