"""Confidence policy for phase-space coordinates.

v1 is deliberately pessimistic. The ladder is:

  none      -- not estimated at all (insufficient_data / not_applicable /
               failed_validation)
  low       -- estimated, but from a thin or indirect basis
  moderate  -- estimated from several features AND backed by a passing
               null control on the source transition record
  high      -- NOT REACHABLE IN v1

`high` is structurally unreachable by `assign_confidence`, not merely
discouraged: no combination of inputs returns it. Justifying a high-confidence
operational coordinate would require validation work (independent replication,
a preregistered effect, perturbational or behavioural corroboration) that this
layer neither performs nor can verify, so the value exists in the schema only
so a future, better-evidenced version can use it without a schema change.
"""
from __future__ import annotations

from typing import Any, Optional

NONE = "none"
LOW = "low"
MODERATE = "moderate"
HIGH = "high"

CONFIDENCE_ORDER: tuple[str, ...] = (NONE, LOW, MODERATE, HIGH)

# Minimum number of distinct contributing source features before a coordinate
# may rise above `low`.
_MODERATE_MIN_FEATURES = 2


def cap_confidence(confidence: str, ceiling: str) -> str:
    """Return the weaker of `confidence` and `ceiling`."""
    if confidence not in CONFIDENCE_ORDER:
        return NONE
    if ceiling not in CONFIDENCE_ORDER:
        return NONE
    return CONFIDENCE_ORDER[
        min(CONFIDENCE_ORDER.index(confidence), CONFIDENCE_ORDER.index(ceiling))
    ]


def assign_confidence(
    *,
    status: str,
    n_source_features: int,
    null_control_summary: Optional[dict[str, Any]] = None,
    axis_max_confidence: str = MODERATE,
) -> str:
    """Assign a confidence level under the v1 policy.

    Never returns `high`. Returns `none` for any non-estimated status.
    """
    if status != "estimated":
        return NONE

    null_status = (null_control_summary or {}).get("status")
    has_passing_null = null_status == "passed"

    if n_source_features >= _MODERATE_MIN_FEATURES and has_passing_null:
        confidence = MODERATE
    else:
        confidence = LOW

    # Per-axis ceiling (e.g. the *_proxy axes are pinned to `low`).
    return cap_confidence(confidence, axis_max_confidence)


def confidence_rationale(
    *,
    status: str,
    n_source_features: int,
    null_control_summary: Optional[dict[str, Any]] = None,
    axis_max_confidence: str = MODERATE,
) -> str:
    """A short, human-readable justification for the assigned confidence."""
    if status != "estimated":
        return f"status is '{status}', so no confidence is asserted."

    null_status = (null_control_summary or {}).get("status", "not_provided")
    parts = [
        f"{n_source_features} contributing source feature(s)",
        f"source-record null control status '{null_status}'",
    ]
    if axis_max_confidence != MODERATE:
        parts.append(f"axis confidence ceiling '{axis_max_confidence}'")
    parts.append("'high' is unreachable in phase-space v1 by policy")
    return "; ".join(parts) + "."
