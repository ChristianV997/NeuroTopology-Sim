"""Classify a single GitHub check entry into one of the six
``CHECK_STATES``. Independently implemented for this package -- no
import of any sibling tool's ci_classifier.

A bare ``"failure"`` conclusion with no supporting ``failure_signature``
evidence is reported as ``"failing"``, never silently downgraded to
``"infrastructure_blocked"`` -- that downgrade requires actual evidence
(a non-empty ``failure_signature`` string) that the failure happened
before any usable step/log ran (billing, quota, runner provisioning,
etc.), not just an assumption.
"""
from __future__ import annotations

from typing import Any, Mapping, Tuple

from .models import Evidence


def classify_check(name: str, check: Mapping[str, Any]) -> Tuple[str, Evidence]:
    """Return ``(check_name, Evidence(state, source))`` for one check
    entry, e.g. ``{"status": "completed", "conclusion": "failure",
    "failure_signature": "..."}``."""
    if not isinstance(check, Mapping) or not check:
        return name, Evidence("unavailable", "no check data supplied")

    status = check.get("status")
    conclusion = check.get("conclusion")
    signature = check.get("failure_signature")

    if status is not None and status != "completed":
        return name, Evidence("pending", f"status={status!r}")

    if conclusion == "success":
        return name, Evidence("passing", "conclusion=success")
    if conclusion == "skipped" or conclusion == "neutral":
        return name, Evidence("skipped", f"conclusion={conclusion!r}")
    if conclusion == "failure":
        if isinstance(signature, str) and signature.strip():
            return name, Evidence(
                "infrastructure_blocked",
                f"conclusion=failure with failure_signature={signature!r}",
            )
        return name, Evidence(
            "failing", "conclusion=failure with no failure_signature evidence"
        )
    if conclusion in ("cancelled", "timed_out", "action_required"):
        return name, Evidence("failing", f"conclusion={conclusion!r}")

    return name, Evidence("unavailable", f"unrecognized status/conclusion ({status!r}/{conclusion!r})")


def classify_all_checks(checks: Mapping[str, Any]) -> dict:
    return {name: evidence.to_dict() for name, evidence in (
        classify_check(n, c) for n, c in sorted(checks.items())
    )}


def worst_check_state(classified: Mapping[str, dict]) -> str:
    """Aggregate priority (worst wins) across a set of already-classified
    checks, for merge_state.py to consume as one signal."""
    priority = ["failing", "infrastructure_blocked", "pending", "unavailable", "skipped", "passing"]
    if not classified:
        return "unavailable"
    states = {entry["value"] for entry in classified.values()}
    for state in priority:
        if state in states:
            return state
    return "unavailable"
