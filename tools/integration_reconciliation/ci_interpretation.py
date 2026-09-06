"""Interpret a check's raw GitHub status/conclusion into a classification
that distinguishes an actual test failure from an infrastructure problem,
a billing block, or a job that simply hasn't run yet.

GitHub's own vocabulary (`status`: queued/in_progress/completed;
`conclusion`: success/failure/neutral/cancelled/timed_out/action_required/
stale/skipped, null while not completed) already distinguishes "not run
yet" from "ran and failed" -- this module's only real addition is
recognizing specific, evidenced failure signatures (a log excerpt or an
operator-supplied note) that mean "this never really tested the code"
rather than fabricating a guess from the conclusion code alone. A
classification is only ever "infrastructure_blocked" or "billing_blocked"
when a snapshot entry actually says so via `failure_signature`/
`conclusion=="action_required"` -- absent that evidence, an unqualified
failure conclusion is reported as "failing", not silently downgraded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CLASSIFICATIONS: frozenset[str] = frozenset({
    "passing", "failing", "pending", "not_run", "infrastructure_blocked", "billing_blocked", "unknown",
})

# Case-insensitive substrings that, if present in a check's supplied
# `failure_signature` (a short evidence excerpt the snapshot may attach --
# e.g. from get_job_logs), mean the run never got to exercise the code at
# all. Each is a literal message this session observed in real job logs
# for this repository (see docs/integration_reconciliation/README.md),
# not a speculative guess.
_INFRASTRUCTURE_SIGNATURES: tuple[str, ...] = (
    "no space left on device",
    "enospc",
    "disk quota exceeded",
    "runner has received a shutdown signal",
    "the runner has been abandoned",
    "failed to download action",
)

_BILLING_SIGNATURES: tuple[str, ...] = (
    "recent account payments have failed",
    "spending limit",
    "billing",
)


@dataclass(frozen=True)
class CheckClassification:
    check_name: str
    classification: str
    reason: str


def classify_check(
    check_name: str,
    *,
    status: Optional[str] = None,
    conclusion: Optional[str] = None,
    failure_signature: Optional[str] = None,
) -> CheckClassification:
    if status is None and conclusion is None:
        return CheckClassification(check_name, "not_run", "no status/conclusion reported for this check")

    signature = (failure_signature or "").lower()
    if any(marker in signature for marker in _BILLING_SIGNATURES):
        return CheckClassification(check_name, "billing_blocked", f"failure_signature matched a billing marker: {failure_signature!r}")
    if conclusion == "action_required":
        return CheckClassification(check_name, "billing_blocked", "conclusion == 'action_required' (GitHub's own signal for a blocked run, e.g. billing/approval)")
    if any(marker in signature for marker in _INFRASTRUCTURE_SIGNATURES):
        return CheckClassification(check_name, "infrastructure_blocked", f"failure_signature matched an infrastructure marker: {failure_signature!r}")

    if status is not None and status != "completed":
        return CheckClassification(check_name, "pending", f"status == {status!r} (not yet completed)")

    if conclusion == "success":
        return CheckClassification(check_name, "passing", "conclusion == 'success'")
    if conclusion in {"neutral", "skipped"}:
        return CheckClassification(check_name, "passing", f"conclusion == {conclusion!r} (non-blocking)")
    if conclusion in {"failure", "timed_out", "cancelled", "stale"}:
        return CheckClassification(check_name, "failing", f"conclusion == {conclusion!r}, no infrastructure/billing signature supplied")

    return CheckClassification(check_name, "unknown", f"unrecognized status/conclusion pair: status={status!r} conclusion={conclusion!r}")


def classify_all(checks: dict[str, dict[str, Optional[str]]]) -> dict[str, CheckClassification]:
    """``checks``: {check_name: {"status":..., "conclusion":..., "failure_signature":...}}."""
    return {
        name: classify_check(
            name,
            status=fields.get("status"),
            conclusion=fields.get("conclusion"),
            failure_signature=fields.get("failure_signature"),
        )
        for name, fields in checks.items()
    }


def summarize(classifications: dict[str, CheckClassification]) -> dict[str, list[str]]:
    """Group check names by classification, for the report/markdown layer."""
    summary: dict[str, list[str]] = {name: [] for name in CLASSIFICATIONS}
    for check_name, result in classifications.items():
        summary[result.classification].append(check_name)
    return {key: sorted(value) for key, value in summary.items() if value}
