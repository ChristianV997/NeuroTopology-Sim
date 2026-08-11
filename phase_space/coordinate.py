"""PhaseSpaceCoordinateV1 -- a derived, provenance-aware coordinate.

A phase-space coordinate is **not a consciousness measure**. It is an
operational summary of named, measurable features carried by one
`TransitionRecordV1`, plus explicit provenance, confidence, missing-feature
status, limitations, and claim scope.

Mirrors the deterministic-ID / to_dict / from_dict / write_json conventions
already established by `transitions.record.TransitionRecordV1` and
`runs.run_record.RunRecordV1`, so all three artifact schemas read as
siblings.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from transitions.governance import (
    ALLOWED_CLAIM_SCOPES,
    ALLOWED_EVIDENCE_LEVELS,
    BLOCKED_CLAIM_SCOPES,
    TRANSITION_EXTRA_BANNED_PHRASES,
)
from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES

# The phrase LISTS are imported, never re-declared -- `report_guardrails` is
# this repository's documented single source of truth and already had four
# near-duplicate copies before the transition layer deliberately stopped
# adding a fifth. Only the small recursive walk is local, so this module does
# not depend on another package's private helper.
_ALL_BANNED_PHRASES: tuple[str, ...] = (
    BANNED_REPORT_PHRASES + TRANSITION_EXTRA_BANNED_PHRASES
)


def scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    """Recursively flag banned overclaim phrases in any free-text payload."""
    if isinstance(value, str):
        low = value.lower()
        for phrase in _ALL_BANNED_PHRASES:
            if phrase in low:
                errors.append(f"{path}: banned phrase detected: '{phrase}'")
    elif isinstance(value, dict):
        for key, sub in value.items():
            scan_banned_phrases(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            scan_banned_phrases(item, f"{path}[{idx}]", errors)

_SCHEMA_VERSION = "1"

# Estimator contract version. Bump when an estimator's *numeric output* for
# the same input would change -- it participates in coordinate_id, so a bump
# deliberately yields new IDs rather than silently overwriting old ones.
ESTIMATOR_VERSION = "phase_space.v1"

STATUS_VALUES: frozenset[str] = frozenset(
    {"estimated", "insufficient_data", "not_applicable", "failed_validation"}
)

CONFIDENCE_VALUES: frozenset[str] = frozenset({"none", "low", "moderate", "high"})

NORMALIZATION_MODES: frozenset[str] = frozenset(
    {"raw", "within_record", "zscore_if_available"}
)

# Claim-scope strength ladder, weakest first. Used to enforce that a derived
# coordinate never asserts a stronger scope than the record it came from.
CLAIM_SCOPE_ORDER: tuple[str, ...] = (
    "computational_artifact",
    "exploratory_metric",
    "dataset_specific",
    "cross_subject_dataset_specific",
)

# Hard ceiling for this layer regardless of input. A phase-space coordinate
# is an unvalidated derived proxy, so v1 never emits a dataset-specific or
# cross-subject scope even when the source transition record carries one.
PHASE_SPACE_MAX_CLAIM_SCOPE = "exploratory_metric"


class CoordinateValidationError(ValueError):
    """Raised when a coordinate fails structural or governance validation."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_coordinate_id(
    *,
    transition_id: str,
    axis: str,
    estimator_version: str,
    normalization_mode: str,
) -> str:
    """Stable sha256[:16] over the coordinate's identity fields only.

    Excludes created_at, the computed value, confidence, and all free text --
    none of those change *which* coordinate is being described. Re-running an
    unchanged estimator on an unchanged transition record always reproduces
    the same ID.
    """
    basis = {
        "transition_id": transition_id,
        "axis": axis,
        "estimator_version": estimator_version,
        "normalization_mode": normalization_mode,
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


def cap_claim_scope(input_scope: str) -> str:
    """Weaken `input_scope` to this layer's ceiling; never strengthen it.

    Unknown or blocked input scopes fail closed to the weakest scope rather
    than being passed through.
    """
    if input_scope in BLOCKED_CLAIM_SCOPES or input_scope not in ALLOWED_CLAIM_SCOPES:
        return CLAIM_SCOPE_ORDER[0]
    input_rank = CLAIM_SCOPE_ORDER.index(input_scope)
    ceiling_rank = CLAIM_SCOPE_ORDER.index(PHASE_SPACE_MAX_CLAIM_SCOPE)
    return CLAIM_SCOPE_ORDER[min(input_rank, ceiling_rank)]


@dataclass
class PhaseSpaceCoordinateV1:
    schema_version: str = _SCHEMA_VERSION
    coordinate_id: str = ""
    transition_id: str = ""
    dataset_id: Optional[str] = None
    subject_id: Optional[str] = None
    session_id: Optional[str] = None
    record_level: str = "subject"
    modality: Optional[str] = None
    axis: str = ""
    value: Optional[float] = None
    status: str = "insufficient_data"
    confidence: str = "none"
    source_features: list[str] = field(default_factory=list)
    missing_features: list[str] = field(default_factory=list)
    normalization_mode: str = "within_record"
    estimator: str = ""
    estimator_version: str = ESTIMATOR_VERSION
    input_claim_scope: str = "computational_artifact"
    output_claim_scope: str = "computational_artifact"
    input_evidence_level: str = "L0_computational_artifact"
    limitations: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── construction ────────────────────────────────────────────────────

    @classmethod
    def make(
        cls,
        *,
        transition_id: str,
        axis: str,
        normalization_mode: str,
        estimator: str,
        estimator_version: str = ESTIMATOR_VERSION,
        input_claim_scope: str = "computational_artifact",
        _now: Optional[datetime] = None,
        **extra: Any,
    ) -> "PhaseSpaceCoordinateV1":
        """Build a coordinate with a deterministic id and a capped output scope."""
        coordinate_id = compute_coordinate_id(
            transition_id=transition_id,
            axis=axis,
            estimator_version=estimator_version,
            normalization_mode=normalization_mode,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        kwargs: dict[str, Any] = dict(
            coordinate_id=coordinate_id,
            transition_id=transition_id,
            axis=axis,
            normalization_mode=normalization_mode,
            estimator=estimator,
            estimator_version=estimator_version,
            input_claim_scope=input_claim_scope,
            output_claim_scope=cap_claim_scope(input_claim_scope),
            created_at=ts,
        )
        kwargs.update(extra)
        return cls(**kwargs)

    # ── serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "coordinate_id": self.coordinate_id,
            "transition_id": self.transition_id,
            "dataset_id": self.dataset_id,
            "subject_id": self.subject_id,
            "session_id": self.session_id,
            "record_level": self.record_level,
            "modality": self.modality,
            "axis": self.axis,
            "value": self.value,
            "status": self.status,
            "confidence": self.confidence,
            "source_features": list(self.source_features),
            "missing_features": list(self.missing_features),
            "normalization_mode": self.normalization_mode,
            "estimator": self.estimator,
            "estimator_version": self.estimator_version,
            "input_claim_scope": self.input_claim_scope,
            "output_claim_scope": self.output_claim_scope,
            "input_evidence_level": self.input_evidence_level,
            "limitations": list(self.limitations),
            "provenance": dict(self.provenance or {}),
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PhaseSpaceCoordinateV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            coordinate_id=d.get("coordinate_id", ""),
            transition_id=d.get("transition_id", ""),
            dataset_id=d.get("dataset_id"),
            subject_id=d.get("subject_id"),
            session_id=d.get("session_id"),
            record_level=d.get("record_level", "subject"),
            modality=d.get("modality"),
            axis=d.get("axis", ""),
            value=d.get("value"),
            status=d.get("status", "insufficient_data"),
            confidence=d.get("confidence", "none"),
            source_features=list(d.get("source_features") or []),
            missing_features=list(d.get("missing_features") or []),
            normalization_mode=d.get("normalization_mode", "within_record"),
            estimator=d.get("estimator", ""),
            estimator_version=d.get("estimator_version", ESTIMATOR_VERSION),
            input_claim_scope=d.get("input_claim_scope", "computational_artifact"),
            output_claim_scope=d.get("output_claim_scope", "computational_artifact"),
            input_evidence_level=d.get("input_evidence_level", "L0_computational_artifact"),
            limitations=list(d.get("limitations") or []),
            provenance=dict(d.get("provenance") or {}),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    @classmethod
    def from_json(cls, text: str) -> "PhaseSpaceCoordinateV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    # ── validation ──────────────────────────────────────────────────────

    def recompute_id(self) -> str:
        return compute_coordinate_id(
            transition_id=self.transition_id,
            axis=self.axis,
            estimator_version=self.estimator_version,
            normalization_mode=self.normalization_mode,
        )

    def validate(self) -> list[str]:
        """Return a list of error strings (empty = valid). Never raises."""
        from phase_space.axes import AxisError, validate_axis_name

        errors: list[str] = []

        if not self.transition_id:
            errors.append("transition_id is required")

        try:
            validate_axis_name(self.axis)
        except AxisError as exc:
            errors.append(str(exc))

        if self.status not in STATUS_VALUES:
            errors.append(
                f"status '{self.status}' must be one of {sorted(STATUS_VALUES)}"
            )
        if self.confidence not in CONFIDENCE_VALUES:
            errors.append(
                f"confidence '{self.confidence}' must be one of {sorted(CONFIDENCE_VALUES)}"
            )
        if self.normalization_mode not in NORMALIZATION_MODES:
            errors.append(
                f"normalization_mode '{self.normalization_mode}' must be one of "
                f"{sorted(NORMALIZATION_MODES)}"
            )

        # Status/value/confidence coherence -- fail closed on contradictions.
        if self.status == "estimated":
            if self.value is None:
                errors.append("status 'estimated' requires a non-null value")
            if not self.source_features:
                errors.append("status 'estimated' requires non-empty source_features")
            if self.confidence == "none":
                errors.append("status 'estimated' must carry a confidence above 'none'")
        else:
            if self.value is not None:
                errors.append(
                    f"status '{self.status}' must not carry a value "
                    "(non-estimated coordinates never report a number)"
                )
            if self.confidence != "none":
                errors.append(
                    f"status '{self.status}' must carry confidence 'none'"
                )

        if self.status == "insufficient_data" and not self.missing_features:
            errors.append(
                "status 'insufficient_data' requires explicit missing_features"
            )

        # Claim-scope governance: never promote.
        if self.input_claim_scope in BLOCKED_CLAIM_SCOPES:
            errors.append(
                f"input_claim_scope '{self.input_claim_scope}' is blocked"
            )
        if self.output_claim_scope in BLOCKED_CLAIM_SCOPES:
            errors.append(
                f"output_claim_scope '{self.output_claim_scope}' is blocked"
            )
        if self.output_claim_scope not in ALLOWED_CLAIM_SCOPES:
            errors.append(
                f"output_claim_scope '{self.output_claim_scope}' is not recognized"
            )
        elif self.input_claim_scope in ALLOWED_CLAIM_SCOPES:
            if CLAIM_SCOPE_ORDER.index(self.output_claim_scope) > CLAIM_SCOPE_ORDER.index(
                self.input_claim_scope
            ):
                errors.append(
                    f"output_claim_scope '{self.output_claim_scope}' exceeds "
                    f"input_claim_scope '{self.input_claim_scope}' -- a derived "
                    "coordinate may never promote a claim"
                )
            if CLAIM_SCOPE_ORDER.index(self.output_claim_scope) > CLAIM_SCOPE_ORDER.index(
                PHASE_SPACE_MAX_CLAIM_SCOPE
            ):
                errors.append(
                    f"output_claim_scope '{self.output_claim_scope}' exceeds the "
                    f"phase-space ceiling '{PHASE_SPACE_MAX_CLAIM_SCOPE}'"
                )

        if self.input_evidence_level not in ALLOWED_EVIDENCE_LEVELS:
            errors.append(
                f"input_evidence_level '{self.input_evidence_level}' is not recognized"
            )

        if not self.limitations:
            errors.append("limitations must be a non-empty list")
        elif any(not str(item).strip() for item in self.limitations):
            errors.append("limitations must not contain empty strings")

        expected_id = self.recompute_id()
        if self.coordinate_id and self.coordinate_id != expected_id:
            errors.append(
                f"coordinate_id '{self.coordinate_id}' does not match the "
                f"deterministic ID computed from its identity fields ('{expected_id}')"
            )

        # Free-text overreach firewall, same source of truth as the
        # transition layer's.
        scan_banned_phrases(self.limitations, "limitations", errors)
        scan_banned_phrases(self.metadata, "metadata", errors)
        scan_banned_phrases(self.provenance, "provenance", errors)
        scan_banned_phrases(self.axis, "axis", errors)

        return errors

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise CoordinateValidationError("; ".join(errors))
