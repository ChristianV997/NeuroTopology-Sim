"""Deterministic per-hypothesis cycle-state computation (requirement 3).

``compute_cycle_state`` is a pure function: given one hypothesis and the
(already-normalized) records that reference it, it returns exactly one of
the 14 states in ``guardrails.CYCLE_STATES`` plus the reasons that led
there. Nothing here is stored or asserted by an upstream input -- the
state is always recomputed from the underlying evidence, so an upstream
system cannot simply claim "PAPER_DRAFT_READY" and have it believed.
"""
from __future__ import annotations

from typing import Any


def compute_cycle_state(
    *,
    hypothesis: dict[str, Any],
    claim_ids: list[str],
    claims_by_id: dict[str, dict[str, Any]],
    claim_provenance_violation_ids: set[str],
    experiment: dict[str, Any] | None,
    metric_violation_ids: set[str],
    execution: dict[str, Any] | None,
    dataset_violation_experiment_ids: set[str],
    null_test: dict[str, Any] | None,
    evidence_update_logged: bool,
    theory_violation_claim_ids: set[str],
    reviewer_decision: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    hypothesis_id = hypothesis["hypothesis_id"]

    if not claim_ids:
        return "HUMAN_REVIEW_REQUIRED", [f"hypothesis {hypothesis_id!r} has no linked literature claims; a human must decide whether to proceed without literature grounding"]

    missing_claims = [cid for cid in claim_ids if cid not in claims_by_id]
    if missing_claims:
        return "BLOCKED_BY_PROVENANCE", [f"claim {cid!r} linked from hypothesis {hypothesis_id!r} was not found in literature_evidence" for cid in missing_claims]

    provenance_violations = [cid for cid in claim_ids if cid in claim_provenance_violation_ids]
    if provenance_violations:
        return "BLOCKED_BY_PROVENANCE", [f"claim {cid!r} linked from hypothesis {hypothesis_id!r} failed the claim-provenance gate" for cid in provenance_violations]

    # LITERATURE_READY achieved.
    if not hypothesis["null_prediction"]:
        return "LITERATURE_READY", [f"hypothesis {hypothesis_id!r} has no null_prediction"]

    # HYPOTHESIS_READY achieved.
    if experiment is None:
        return "HYPOTHESIS_READY", [f"no experiment plan references hypothesis {hypothesis_id!r}"]
    if not experiment["falsification_criterion"]:
        return "HYPOTHESIS_READY", [f"experiment {experiment['experiment_id']!r} has no falsification_criterion"]
    if any(vid.startswith(f"{experiment['experiment_id']}:") for vid in metric_violation_ids):
        return "HYPOTHESIS_READY", [f"experiment {experiment['experiment_id']!r} has a metric missing unit/feature_family"]
    if experiment["is_predictive"] and experiment["held_out_split_locked"] is not True:
        return "HYPOTHESIS_READY", [f"predictive experiment {experiment['experiment_id']!r} does not have a locked held-out split"]

    # EXPERIMENT_READY achieved.
    if execution is None:
        return "EXPERIMENT_READY", [f"no execution recorded for experiment {experiment['experiment_id']!r}"]
    if execution["dependency_state"] in ("missing", "blocked"):
        return "BLOCKED_BY_DEPENDENCY", [f"execution {execution['experiment_id']!r} has dependency_state={execution['dependency_state']!r}"]
    if execution["status"] in ("not_started", "running", "unknown"):
        return "EXECUTION_PENDING", [f"execution {execution['experiment_id']!r} status={execution['status']!r}"]
    if execution["status"] == "failed":
        return "BLOCKED_BY_DEPENDENCY", [f"execution {execution['experiment_id']!r} failed"]
    if execution["experiment_id"] in dataset_violation_experiment_ids:
        return "BLOCKED_BY_DATA", [f"execution {execution['experiment_id']!r} failed the dataset-checksum gate"]

    # EXECUTED achieved.
    if null_test is None:
        return "EXECUTED", [f"no null/surrogate validation recorded for experiment {experiment['experiment_id']!r}"]
    if null_test["verdict"] == "TIMEOUT":
        return "VALIDATION_PENDING", [f"null/surrogate test for {experiment['experiment_id']!r} timed out -- a timeout is not a scientific outcome and must be re-run"]
    if null_test["verdict"] == "unknown":
        return "VALIDATION_PENDING", [f"null/surrogate verdict for {experiment['experiment_id']!r} not yet reported"]
    if null_test["verdict"] == "INCONCLUSIVE":
        return "INCONCLUSIVE", [f"null/surrogate test for {experiment['experiment_id']!r} was inconclusive"]

    # verdict is PASS or FAIL.
    if not evidence_update_logged:
        return "EVIDENCE_UPDATE_READY", [f"null/surrogate result for {experiment['experiment_id']!r} is ready to be logged as an evidence update"]

    hypothesis_theory_violation = bool(theory_violation_claim_ids & set(claim_ids))
    if null_test["verdict"] == "FAIL" or hypothesis_theory_violation:
        reasons = []
        if null_test["verdict"] == "FAIL":
            reasons.append(f"null/surrogate test for {experiment['experiment_id']!r} returned FAIL")
        if hypothesis_theory_violation:
            reasons.append("theory_state's contradictory evidence for this hypothesis's claims is unresolved")
        return "THEORY_REVISION_REQUIRED", reasons

    if reviewer_decision is None or reviewer_decision["decision"] == "pending":
        return "HUMAN_REVIEW_REQUIRED", [f"no approved human-review decision recorded for hypothesis {hypothesis_id!r}"]
    if reviewer_decision["decision"] == "rejected":
        return "HUMAN_REVIEW_REQUIRED", [f"reviewer decision for hypothesis {hypothesis_id!r} is rejected and needs resolution"]

    return "PAPER_DRAFT_READY", [f"all gates passed and reviewer decision is {reviewer_decision['decision']!r} for hypothesis {hypothesis_id!r}"]
