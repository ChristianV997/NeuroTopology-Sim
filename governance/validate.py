"""
Validation logic for HypothesisSpec — hard governance gates.

Rules:
- claim_type in {K, C}:
  - discriminator must be present and non-empty (description not blank)
  - controls must have ≥1 entry
  - readouts must have ≥1 entry
- claim_type == C additionally requires:
  - alternatives_considered must have ≥1 string
  - pass_fail.thresholds must be non-empty
"""
from __future__ import annotations

from typing import List

from governance.spec import HypothesisSpec

VALID_CLAIM_TYPES = {"M", "K", "C"}
VALID_LAYERS = {"Marker", "Topology", "Substrate"}


class ValidationError(Exception):
    """Raised when a HypothesisSpec fails a hard governance gate."""

    def __init__(self, spec_id: str, errors: List[str]) -> None:
        self.spec_id = spec_id
        self.errors = errors
        msg = f"Spec '{spec_id}' failed validation:\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(msg)


def validate_spec(spec: HypothesisSpec) -> None:
    """Validate a HypothesisSpec against governance rules.

    Raises ValidationError listing all violations if the spec is invalid.
    Returns silently if valid.
    """
    errors: List[str] = []

    # Basic field checks
    if not spec.id or not spec.id.strip():
        errors.append("'id' must not be empty")
    if not spec.title or not spec.title.strip():
        errors.append("'title' must not be empty")
    if spec.claim_type not in VALID_CLAIM_TYPES:
        errors.append(f"'claim_type' must be one of {sorted(VALID_CLAIM_TYPES)}, got '{spec.claim_type}'")
    if spec.layer not in VALID_LAYERS:
        errors.append(f"'layer' must be one of {sorted(VALID_LAYERS)}, got '{spec.layer}'")
    if not spec.summary or not spec.summary.strip():
        errors.append("'summary' must not be empty")

    # K/C gates
    if spec.claim_type in {"K", "C"}:
        if spec.discriminator is None or not spec.discriminator.description.strip():
            errors.append(
                "claim_type K/C requires a non-empty 'discriminator.description'"
            )
        if len(spec.controls) < 1:
            errors.append("claim_type K/C requires at least one entry in 'controls'")
        if len(spec.readouts) < 1:
            errors.append("claim_type K/C requires at least one entry in 'readouts'")

    # C-only stricter gates
    if spec.claim_type == "C":
        if len(spec.alternatives_considered) < 1:
            errors.append(
                "claim_type C requires 'alternatives_considered' to have at least one entry"
            )
        if not spec.pass_fail.thresholds:
            errors.append(
                "claim_type C requires non-empty 'pass_fail.thresholds'"
            )

    if errors:
        raise ValidationError(spec.id or "<unknown>", errors)
