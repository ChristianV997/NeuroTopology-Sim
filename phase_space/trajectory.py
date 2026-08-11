"""PhaseSpaceTrajectoryV1 -- a bundle of coordinates from one or more records.

A trajectory is a container, not an analysis. v1 does no interpolation,
smoothing, curve fitting, or dynamical modelling; it groups coordinates that
share a dataset and normalization convention so a later consumer has one
addressable artifact instead of loose files.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from phase_space.coordinate import (
    CLAIM_SCOPE_ORDER,
    PhaseSpaceCoordinateV1,
    cap_claim_scope,
    scan_banned_phrases,
)
from transitions.governance import ALLOWED_CLAIM_SCOPES, ALLOWED_EVIDENCE_LEVELS

_SCHEMA_VERSION = "1"

# Evidence-level ladder, weakest first -- a trajectory inherits the WEAKEST
# evidence level among its coordinates, never the strongest.
_EVIDENCE_ORDER: tuple[str, ...] = (
    "L0_computational_artifact",
    "L1_synthetic_validation",
    "L2_single_subject_real_signal",
    "L3_dataset_specific_effect",
    "L4_cross_subject_dataset_specific",
)


class TrajectoryValidationError(ValueError):
    """Raised when a trajectory fails structural or governance validation."""


def compute_trajectory_id(
    *,
    source_transition_ids: Sequence[str],
    axes: Sequence[str],
    normalization_mode: str,
    estimator_version: str,
) -> str:
    """Stable sha256[:16]; order-insensitive in ids and axes, excludes created_at."""
    basis = {
        "source_transition_ids": sorted(set(source_transition_ids)),
        "axes": sorted(set(axes)),
        "normalization_mode": normalization_mode,
        "estimator_version": estimator_version,
    }
    blob = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _weakest(values: Sequence[str], ladder: Sequence[str], default: str) -> str:
    ranks = [ladder.index(v) for v in values if v in ladder]
    return ladder[min(ranks)] if ranks else default


@dataclass
class PhaseSpaceTrajectoryV1:
    schema_version: str = _SCHEMA_VERSION
    trajectory_id: str = ""
    source_transition_ids: list[str] = field(default_factory=list)
    dataset_id: Optional[str] = None
    subject_id: Optional[str] = None
    record_level: str = "subject"
    axes: list[str] = field(default_factory=list)
    coordinates: list[PhaseSpaceCoordinateV1] = field(default_factory=list)
    normalization_mode: str = "within_record"
    limitations: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    claim_scope: str = "computational_artifact"
    evidence_level: str = "L0_computational_artifact"
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_coordinates(
        cls,
        coordinates: Sequence[PhaseSpaceCoordinateV1],
        *,
        normalization_mode: str,
        estimator_version: str,
        limitations: Optional[Sequence[str]] = None,
        _now: Optional[datetime] = None,
        **extra: Any,
    ) -> "PhaseSpaceTrajectoryV1":
        """Build a trajectory, inheriting the WEAKEST scope/evidence present."""
        coords = list(coordinates)
        transition_ids = [c.transition_id for c in coords]
        axes = [c.axis for c in coords]

        claim_scope = cap_claim_scope(
            _weakest(
                [c.output_claim_scope for c in coords],
                CLAIM_SCOPE_ORDER,
                CLAIM_SCOPE_ORDER[0],
            )
        )
        evidence_level = _weakest(
            [c.input_evidence_level for c in coords],
            _EVIDENCE_ORDER,
            _EVIDENCE_ORDER[0],
        )

        dataset_ids = {c.dataset_id for c in coords if c.dataset_id}
        subject_ids = {c.subject_id for c in coords if c.subject_id}
        record_levels = {c.record_level for c in coords if c.record_level}

        base_limitations = [
            "A phase-space trajectory is a container for coordinates, not a "
            "dynamical model: v1 performs no interpolation, smoothing, curve "
            "fitting, or trajectory inference.",
            "Claim scope and evidence level are inherited from the WEAKEST "
            "contributing coordinate; grouping coordinates never strengthens "
            "any claim.",
        ]
        if len(dataset_ids) > 1:
            base_limitations.append(
                f"Coordinates span multiple datasets ({sorted(dataset_ids)}); "
                "cross-dataset comparison of these values is not supported by "
                "this layer."
            )

        kwargs: dict[str, Any] = dict(
            trajectory_id=compute_trajectory_id(
                source_transition_ids=transition_ids,
                axes=axes,
                normalization_mode=normalization_mode,
                estimator_version=estimator_version,
            ),
            source_transition_ids=sorted(set(transition_ids)),
            dataset_id=next(iter(dataset_ids)) if len(dataset_ids) == 1 else None,
            subject_id=next(iter(subject_ids)) if len(subject_ids) == 1 else None,
            record_level=next(iter(record_levels)) if len(record_levels) == 1 else "mixed",
            axes=sorted(set(axes)),
            coordinates=coords,
            normalization_mode=normalization_mode,
            limitations=list(limitations or []) + base_limitations,
            claim_scope=claim_scope,
            evidence_level=evidence_level,
            created_at=(_now or datetime.now(timezone.utc)).isoformat(),
        )
        kwargs.update(extra)
        return cls(**kwargs)

    # ── serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trajectory_id": self.trajectory_id,
            "source_transition_ids": list(self.source_transition_ids),
            "dataset_id": self.dataset_id,
            "subject_id": self.subject_id,
            "record_level": self.record_level,
            "axes": list(self.axes),
            "coordinates": [c.to_dict() for c in self.coordinates],
            "normalization_mode": self.normalization_mode,
            "limitations": list(self.limitations),
            "provenance": dict(self.provenance or {}),
            "claim_scope": self.claim_scope,
            "evidence_level": self.evidence_level,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PhaseSpaceTrajectoryV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            trajectory_id=d.get("trajectory_id", ""),
            source_transition_ids=list(d.get("source_transition_ids") or []),
            dataset_id=d.get("dataset_id"),
            subject_id=d.get("subject_id"),
            record_level=d.get("record_level", "subject"),
            axes=list(d.get("axes") or []),
            coordinates=[
                PhaseSpaceCoordinateV1.from_dict(c) for c in (d.get("coordinates") or [])
            ],
            normalization_mode=d.get("normalization_mode", "within_record"),
            limitations=list(d.get("limitations") or []),
            provenance=dict(d.get("provenance") or {}),
            claim_scope=d.get("claim_scope", "computational_artifact"),
            evidence_level=d.get("evidence_level", "L0_computational_artifact"),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    @classmethod
    def from_json(cls, text: str) -> "PhaseSpaceTrajectoryV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    # ── validation ──────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.source_transition_ids:
            errors.append("source_transition_ids must be non-empty")
        if not self.limitations:
            errors.append("limitations must be a non-empty list")
        if self.claim_scope not in ALLOWED_CLAIM_SCOPES:
            errors.append(f"claim_scope '{self.claim_scope}' is not recognized")
        if self.evidence_level not in ALLOWED_EVIDENCE_LEVELS:
            errors.append(f"evidence_level '{self.evidence_level}' is not recognized")

        expected_id = compute_trajectory_id(
            source_transition_ids=[c.transition_id for c in self.coordinates]
            or self.source_transition_ids,
            axes=[c.axis for c in self.coordinates] or self.axes,
            normalization_mode=self.normalization_mode,
            estimator_version=(
                self.coordinates[0].estimator_version if self.coordinates else ""
            ),
        )
        if self.coordinates and self.trajectory_id and self.trajectory_id != expected_id:
            errors.append(
                f"trajectory_id '{self.trajectory_id}' does not match the "
                f"deterministic ID computed from its contents ('{expected_id}')"
            )

        for idx, coord in enumerate(self.coordinates):
            for err in coord.validate():
                errors.append(f"coordinates[{idx}]: {err}")
            # A trajectory must never present a stronger scope than any member.
            if (
                coord.output_claim_scope in ALLOWED_CLAIM_SCOPES
                and self.claim_scope in ALLOWED_CLAIM_SCOPES
                and CLAIM_SCOPE_ORDER.index(self.claim_scope)
                > CLAIM_SCOPE_ORDER.index(coord.output_claim_scope)
            ):
                errors.append(
                    f"trajectory claim_scope '{self.claim_scope}' exceeds "
                    f"coordinates[{idx}] output_claim_scope "
                    f"'{coord.output_claim_scope}'"
                )

        scan_banned_phrases(self.limitations, "limitations", errors)
        scan_banned_phrases(self.metadata, "metadata", errors)
        scan_banned_phrases(self.provenance, "provenance", errors)

        return errors

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise TrajectoryValidationError("; ".join(errors))
