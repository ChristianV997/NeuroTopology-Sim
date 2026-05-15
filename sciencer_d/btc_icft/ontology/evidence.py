"""
Evidence requirement matrix (O2).

Encodes per-scope artifact/control/review requirements and computes whether
a candidate scope is satisfied given the available evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from sciencer_d.btc_icft.ontology.schema import CLAIM_SCOPES, ClaimScope, PromotionState


def load_evidence_requirement_matrix(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"evidence requirement matrix not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def validate_evidence_requirement_matrix(matrix: dict) -> list[str]:
    errors: list[str] = []
    rows = matrix.get("rows", [])
    if not isinstance(rows, list) or not rows:
        errors.append("rows list missing or empty")
        return errors

    seen: set[str] = set()
    for idx, r in enumerate(rows):
        scope = r.get("scope", "")
        if not scope:
            errors.append(f"row[{idx}] missing scope")
            continue
        if scope in seen:
            errors.append(f"duplicate scope: {scope}")
        seen.add(scope)
        if scope not in CLAIM_SCOPES:
            errors.append(f"row[{idx}] invalid scope '{scope}'")

        # No row may permit ontology proof promotion
        max_state = r.get("max_promotion_state", "")
        if scope == ClaimScope.ONTOLOGY_CANDIDATE and max_state != PromotionState.ONTOLOGY_QUARANTINED:
            errors.append(
                f"row[{idx}] scope=ontology_candidate must cap promotion at "
                f"'ontology_quarantined', got '{max_state}'"
            )

    return errors


def _row_for_scope(matrix: dict, scope: str) -> dict | None:
    for r in matrix.get("rows", []):
        if r.get("scope") == scope:
            return r
    return None


def evaluate_scope_requirements(
    scope: str,
    available_artifacts: set[str],
    available_controls: set[str],
    run_mode: str,
    human_review_status: str = "not_performed",
    *,
    matrix: dict | None = None,
) -> dict:
    """Evaluate whether the requirements for `scope` are satisfied.

    Returns a dict with: satisfied, blockers, max_promotion_state, scope, matched_row.
    """
    if matrix is None:
        return {
            "satisfied": False,
            "blockers": ["evidence requirement matrix not provided"],
            "max_promotion_state": PromotionState.DRAFT,
            "scope": scope,
            "matched_row": None,
        }

    row = _row_for_scope(matrix, scope)
    if row is None:
        return {
            "satisfied": False,
            "blockers": [f"no matrix row for scope '{scope}'"],
            "max_promotion_state": PromotionState.DRAFT,
            "scope": scope,
            "matched_row": None,
        }

    blockers: list[str] = []

    if row.get("requires_real_execution") and run_mode in ("mock_e2e", "mock-e2e", "dry_run"):
        blockers.append("real execution required; current run is mock or dry-run")

    if row.get("requires_reviewed_labels") and "features_m_signal_labeled.csv" not in available_artifacts:
        blockers.append("reviewed-label artifacts required (features_m_signal_labeled.csv)")

    if row.get("requires_controls"):
        for c in ("nulls.json", "ablations.json", "leakage_report.json", "artifact_report.json"):
            if row.get(_required_key(c)) and c not in available_controls:
                blockers.append(f"missing required control: {c}")

    if row.get("requires_independent_dataset") and "independent_dataset_replication.json" not in available_artifacts:
        blockers.append("independent dataset replication artifact missing")

    if row.get("requires_mechanism_evidence") and "independent_mechanism_evidence_packet.json" not in available_artifacts:
        blockers.append("independent mechanism evidence packet missing")

    if row.get("requires_human_review") and human_review_status != "completed":
        blockers.append("human review required; current status is not 'completed'")

    satisfied = len(blockers) == 0
    max_state = row.get("max_promotion_state", PromotionState.DRAFT)
    return {
        "satisfied": satisfied,
        "blockers": blockers,
        "max_promotion_state": max_state,
        "scope": scope,
        "matched_row": row,
    }


def _required_key(filename: str) -> str:
    mapping = {
        "nulls.json": "requires_nulls",
        "ablations.json": "requires_ablations",
        "leakage_report.json": "requires_leakage_report",
        "artifact_report.json": "requires_artifact_report",
    }
    return mapping.get(filename, "requires_controls")
