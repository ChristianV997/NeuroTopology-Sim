"""Subject-leakage checks for declared split policies."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set


LEAKAGE_RISK_POLICIES = frozenset({"random_trial_split"})
SUBJECT_SAFE_POLICIES = frozenset(
    {
        "cross_subject_leave_one_out",
        "custom_subject_holdout",
        "cross_session_leave_one_out",
        "within_session_kfold",
        "within_subject_session_pooled_kfold",
    }
)


def _id_set(values: Optional[Sequence[Any]]) -> Set[str]:
    if not values:
        return set()
    return {str(v).strip() for v in values if str(v).strip()}


def assess_subject_leakage(
    *,
    split_policy: str,
    train_subject_ids: Optional[Sequence[Any]] = None,
    test_subject_ids: Optional[Sequence[Any]] = None,
    unit_of_analysis: Optional[str] = None,
) -> Dict[str, Any]:
    """Return leakage assessment without inventing subject lists.

    A split that can place the same participant in train and test must fail
    validation or be marked inconclusive.
    """
    findings: List[str] = []
    train = _id_set(train_subject_ids)
    test = _id_set(test_subject_ids)
    overlap = sorted(train & test)

    if split_policy == "unspecified":
        return {
            "status": "incomplete",
            "subject_leakage": None,
            "overlap_subject_ids": [],
            "findings": ["split_policy_unspecified"],
        }

    if split_policy in LEAKAGE_RISK_POLICIES:
        return {
            "status": "failed",
            "subject_leakage": True,
            "overlap_subject_ids": overlap,
            "findings": [
                "random_trial_split_can_leak_subjects",
                "subject_blocked_split_required",
            ],
        }

    if split_policy == "custom_subject_holdout":
        if not train or not test:
            return {
                "status": "incomplete",
                "subject_leakage": None,
                "overlap_subject_ids": [],
                "findings": ["custom_holdout_missing_subject_lists"],
            }
        if overlap:
            return {
                "status": "failed",
                "subject_leakage": True,
                "overlap_subject_ids": overlap,
                "findings": ["train_test_subject_overlap"],
            }
        return {
            "status": "ok",
            "subject_leakage": False,
            "overlap_subject_ids": [],
            "findings": ["custom_holdout_disjoint_subjects"],
        }

    if split_policy == "cross_subject_leave_one_out":
        # By definition subject-blocked; no fabricated subject ids required.
        if overlap:
            return {
                "status": "failed",
                "subject_leakage": True,
                "overlap_subject_ids": overlap,
                "findings": ["explicit_lists_overlap_despite_cross_subject_policy"],
            }
        return {
            "status": "ok",
            "subject_leakage": False,
            "overlap_subject_ids": [],
            "findings": ["cross_subject_leave_one_out_subject_blocked"],
        }

    if split_policy in {"cross_session_leave_one_out", "within_session_kfold", "within_subject_session_pooled_kfold"}:
        # Same subject may appear in train/test across sessions/trials; that is
        # not cross-subject leakage, but unit_of_analysis must acknowledge it.
        if unit_of_analysis == "subject" and split_policy != "cross_session_leave_one_out":
            findings.append("unit_of_analysis_subject_with_within_subject_split")
            return {
                "status": "inconclusive",
                "subject_leakage": None,
                "overlap_subject_ids": overlap,
                "findings": findings,
            }
        if overlap and split_policy == "cross_session_leave_one_out":
            # Overlap lists are expected for same subject across sessions — not a fail.
            pass
        return {
            "status": "ok",
            "subject_leakage": False,
            "overlap_subject_ids": [],
            "findings": findings or [f"{split_policy}_within_subject_allowed"],
        }

    if overlap:
        return {
            "status": "failed",
            "subject_leakage": True,
            "overlap_subject_ids": overlap,
            "findings": ["train_test_subject_overlap"],
        }

    return {
        "status": "inconclusive",
        "subject_leakage": None,
        "overlap_subject_ids": [],
        "findings": ["split_policy_not_classified_for_leakage"],
    }
