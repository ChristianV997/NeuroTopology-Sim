"""Requirement 13: classify each check into exactly one of passing /
failing / pending / skipped / infrastructure_blocked / unavailable.

Independently implemented from any prior session's ci_interpretation
module (this branch owns no dependency on tools/integration_reconciliation)
but follows the same non-negotiable rule: a bare "failure" conclusion
with no supporting evidence is reported as a real failure, never quietly
downgraded to infrastructure_blocked without a matching signature.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_INFRASTRUCTURE_SIGNATURES: tuple[str, ...] = (
    "no space left on device", "enospc", "disk quota exceeded",
    "runner has received a shutdown signal", "the runner has been abandoned",
    "recent account payments have failed", "spending limit", "billing",
)


@dataclass(frozen=True)
class CheckClassification:
    check_name: str
    classification: str
    reason: str


def classify_check(
    check_name: str, *, status: Optional[str] = None, conclusion: Optional[str] = None,
    failure_signature: Optional[str] = None,
) -> CheckClassification:
    if status is None and conclusion is None:
        return CheckClassification(check_name, "unavailable", "no status/conclusion data supplied for this check")

    signature = (failure_signature or "").lower()
    if any(marker in signature for marker in _INFRASTRUCTURE_SIGNATURES) or conclusion == "action_required":
        return CheckClassification(
            check_name, "infrastructure_blocked",
            f"infrastructure/billing signature matched: {failure_signature!r}" if failure_signature
            else "conclusion == 'action_required'",
        )

    if status is not None and status != "completed":
        return CheckClassification(check_name, "pending", f"status == {status!r} (not yet completed)")

    if conclusion == "success":
        return CheckClassification(check_name, "passing", "conclusion == 'success'")
    if conclusion in {"skipped", "neutral"}:
        return CheckClassification(check_name, "skipped", f"conclusion == {conclusion!r}")
    if conclusion in {"failure", "timed_out", "cancelled", "stale"}:
        return CheckClassification(
            check_name, "failing", f"conclusion == {conclusion!r}, no infrastructure signature supplied"
        )

    return CheckClassification(check_name, "unavailable", f"unrecognized status/conclusion: {status!r}/{conclusion!r}")


def classify_all(checks: dict[str, dict]) -> dict[str, CheckClassification]:
    return {
        name: classify_check(
            name, status=fields.get("status"), conclusion=fields.get("conclusion"),
            failure_signature=fields.get("failure_signature"),
        )
        for name, fields in checks.items()
    }


def as_state_map(classifications: dict[str, CheckClassification]) -> dict[str, str]:
    return {name: result.classification for name, result in classifications.items()}
