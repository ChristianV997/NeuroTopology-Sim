"""
Ontology promotion logic (O2).

Determines the max claim scope and promotion state for an ontology evaluation
based on run mode, available artifacts/controls, and human review status.
Hard rule: no path produces an ontology proof state.
"""
from __future__ import annotations

from typing import Optional

from sciencer_d.btc_icft.ontology.schema import (
    ClaimScope,
    OntologyClaim,
    OntologyLayer,
    PromotionState,
)


_REVIEWED_LABEL_ARTIFACT = "features_m_signal_labeled.csv"

_REQUIRED_CONTROLS = (
    "nulls.json",
    "ablations.json",
    "leakage_report.json",
    "artifact_report.json",
)


def _controls_complete(available_controls: set[str]) -> bool:
    return all(c in available_controls for c in _REQUIRED_CONTROLS)


def determine_max_claim_scope(
    run_mode: str,
    available_artifacts: set[str],
    available_controls: set[str],
    *,
    independent_dataset_present: bool = False,
    independent_mechanism_evidence_present: bool = False,
    human_review_completed: bool = False,
) -> str:
    """Return the maximum claim scope permitted by current evidence."""
    if run_mode in ("mock_e2e", "mock-e2e", "dry_run"):
        return ClaimScope.ENGINEERING_RUNTIME

    if _REVIEWED_LABEL_ARTIFACT not in available_artifacts:
        return ClaimScope.ENGINEERING_RUNTIME

    if not _controls_complete(available_controls):
        return ClaimScope.MARKER_ASSOCIATION if "metrics_signal_mt.json" in available_artifacts else ClaimScope.ENGINEERING_RUNTIME

    scope = ClaimScope.TOPOLOGY_RESIDUAL

    if independent_mechanism_evidence_present:
        scope = ClaimScope.MECHANISM_CANDIDATE

    # Theory consistency is allowed alongside topology_residual but is not a
    # higher promotion ceiling; it lives orthogonally and is reported as such.

    # Ontology candidate scope is only reachable when independent dataset and
    # mechanism evidence are both present AND human review has completed.
    if (
        independent_dataset_present
        and independent_mechanism_evidence_present
        and human_review_completed
    ):
        scope = ClaimScope.ONTOLOGY_CANDIDATE

    return scope


def determine_promotion_state(
    run_mode: str,
    available_artifacts: set[str],
    available_controls: set[str],
    *,
    independent_dataset_present: bool = False,
    independent_mechanism_evidence_present: bool = False,
    human_review_completed: bool = False,
) -> str:
    """Determine the overall promotion state for the evaluation."""
    if run_mode in ("mock_e2e", "mock-e2e", "dry_run"):
        return PromotionState.ENGINEERING_VALIDATED

    if _REVIEWED_LABEL_ARTIFACT not in available_artifacts:
        return PromotionState.BLOCKED_PENDING_REAL_EXECUTION

    if not _controls_complete(available_controls):
        return PromotionState.BLOCKED_PENDING_CONTROLS

    if not human_review_completed:
        return PromotionState.BLOCKED_PENDING_REVIEW

    if independent_mechanism_evidence_present and independent_dataset_present:
        return PromotionState.MECHANISM_CANDIDATE

    return PromotionState.EMPIRICAL_CANDIDATE


def build_claim_scope_matrix(
    run_mode: str,
    available_artifacts: set[str],
    available_controls: set[str],
    *,
    independent_dataset_present: bool = False,
    independent_mechanism_evidence_present: bool = False,
    human_review_completed: bool = False,
) -> dict:
    """Produce a matrix of {scope: {allowed, max_state, blockers}}."""
    is_mock = run_mode in ("mock_e2e", "mock-e2e", "dry_run")
    has_labels = _REVIEWED_LABEL_ARTIFACT in available_artifacts
    has_controls = _controls_complete(available_controls)

    matrix: dict = {}

    matrix[ClaimScope.ENGINEERING_RUNTIME] = {
        "allowed": True,
        "max_state": PromotionState.ENGINEERING_VALIDATED,
        "blockers": [],
    }

    blockers: list[str] = []
    if is_mock:
        blockers.append("blocked_pending_real_execution")
    if not has_labels:
        blockers.append("blocked_pending_reviewed_labels")
    matrix[ClaimScope.MARKER_ASSOCIATION] = {
        "allowed": not blockers,
        "max_state": PromotionState.EMPIRICAL_CANDIDATE if not blockers else PromotionState.BLOCKED_PENDING_REAL_EXECUTION,
        "blockers": blockers,
    }

    blockers = []
    if is_mock:
        blockers.append("blocked_pending_real_execution")
    if not has_labels:
        blockers.append("blocked_pending_reviewed_labels")
    if not has_controls:
        blockers.append("blocked_pending_controls")
    matrix[ClaimScope.TOPOLOGY_RESIDUAL] = {
        "allowed": not blockers,
        "max_state": PromotionState.EMPIRICAL_CANDIDATE if not blockers else PromotionState.BLOCKED_PENDING_CONTROLS,
        "blockers": blockers,
    }

    blockers = []
    if is_mock:
        blockers.append("blocked_pending_real_execution")
    if not has_labels:
        blockers.append("blocked_pending_reviewed_labels")
    if not has_controls:
        blockers.append("blocked_pending_controls")
    if not independent_mechanism_evidence_present:
        blockers.append("blocked_pending_independent_mechanism_evidence")
    matrix[ClaimScope.MECHANISM_CANDIDATE] = {
        "allowed": not blockers,
        "max_state": PromotionState.MECHANISM_CANDIDATE if not blockers else PromotionState.BLOCKED_PENDING_REVIEW,
        "blockers": blockers,
    }

    matrix[ClaimScope.THEORY_CONSISTENCY] = {
        "allowed": True,
        "max_state": PromotionState.THEORY_CONSISTENCY_ONLY,
        "blockers": [] if human_review_completed else ["blocked_pending_review"],
    }

    blockers = []
    if is_mock:
        blockers.append("blocked_pending_real_execution")
    if not has_labels:
        blockers.append("blocked_pending_reviewed_labels")
    if not has_controls:
        blockers.append("blocked_pending_controls")
    if not independent_dataset_present:
        blockers.append("blocked_pending_independent_dataset")
    if not independent_mechanism_evidence_present:
        blockers.append("blocked_pending_independent_mechanism_evidence")
    if not human_review_completed:
        blockers.append("blocked_pending_review")
    matrix[ClaimScope.ONTOLOGY_CANDIDATE] = {
        "allowed": False,
        "max_state": PromotionState.ONTOLOGY_QUARANTINED,
        "blockers": blockers,
        "always_quarantined": True,
    }

    return matrix


def build_ontology_promotion_decision(
    dataset_id: str,
    run_mode: str,
    max_claim_scope: str,
    promotion_state: str,
    blockers: list[str],
) -> dict:
    """Bundle the final promotion decision into a JSON-serializable record."""
    return {
        "dataset_id": dataset_id,
        "run_mode": run_mode,
        "max_claim_scope": max_claim_scope,
        "promotion_state": promotion_state,
        "ontology_claim_status": PromotionState.ONTOLOGY_QUARANTINED,
        "empirical_marker_promotion": (
            max_claim_scope in (ClaimScope.MARKER_ASSOCIATION, ClaimScope.TOPOLOGY_RESIDUAL,
                                ClaimScope.MECHANISM_CANDIDATE)
        ),
        "empirical_topology_promotion": (
            max_claim_scope in (ClaimScope.TOPOLOGY_RESIDUAL, ClaimScope.MECHANISM_CANDIDATE)
        ),
        "mechanism_promotion": max_claim_scope == ClaimScope.MECHANISM_CANDIDATE,
        "ontology_promotion": False,
        "metaphysical_promotion": False,
        "blockers": blockers,
    }


def build_layer_claim(
    claim_id: str,
    title: str,
    layer: str,
    scope: str,
    statement: str,
    *,
    allowed: bool,
    promotion_state: str,
    required_evidence: Optional[list[str]] = None,
    required_controls: Optional[list[str]] = None,
    blockers: Optional[list[str]] = None,
) -> OntologyClaim:
    return OntologyClaim(
        claim_id=claim_id,
        title=title,
        layer=layer,
        scope=scope,
        statement=statement,
        allowed=allowed,
        promotion_state=promotion_state,
        required_evidence=list(required_evidence or []),
        required_controls=list(required_controls or []),
        blockers=list(blockers or []),
        warnings=[],
    )
