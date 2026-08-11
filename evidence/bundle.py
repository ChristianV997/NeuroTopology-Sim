"""EvidenceBundleV1 -- the durable object linking registry authorization,
TransitionRecordV1 artifacts, and PhaseSpaceCoordinateV1 artifacts for one
source dataset/artifact into a single reproducible manifest.

Mirrors the deterministic-ID / to_dict / from_dict / write_json / validate
conventions already established by `transitions.record.TransitionRecordV1`
and `phase_space.coordinate.PhaseSpaceCoordinateV1`, so all three schemas
read as siblings. Structural validation lives in `evidence.validation`
(mirroring `TransitionRecordV1` <-> `transitions.governance`); this module
defines only the record shape and its serialization.

A governed evidence bundle is still not a theory result. It is a
reproducible artifact manifest: which source artifact was read, what the
benchmark registry decided, which TransitionRecordV1/PhaseSpaceCoordinateV1
artifacts were produced, what their claim/evidence ceilings are, and what
contamination updates (if any) were applied -- nothing more.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from evidence.validation import validate_bundle

_SCHEMA_VERSION = "1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_bundle_id(
    *,
    dataset_id: Optional[str],
    artifact_ids: list[str],
    requested_use: Optional[str],
    transition_record_ids: list[str],
    phase_space_coordinate_ids: list[str],
) -> str:
    """Stable sha256[:16] over the bundle's identity fields only.

    Excludes created_at, repo_commit, registry_decisions,
    contamination_updates, ceilings, null_control_summary,
    validation_summary, and all free text -- none of those change *which*
    evidence bundle is being described. Mirrors
    `transitions.record.compute_transition_id` and
    `phase_space.coordinate.compute_coordinate_id`.
    """
    basis = {
        "dataset_id": dataset_id,
        "artifact_ids": sorted(artifact_ids or []),
        "requested_use": requested_use,
        "transition_record_ids": sorted(transition_record_ids or []),
        "phase_space_coordinate_ids": sorted(phase_space_coordinate_ids or []),
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class BundleValidationError(ValueError):
    """Raised when an EvidenceBundleV1 fails structural or governance validation."""


@dataclass
class EvidenceBundleV1:
    schema_version: str = _SCHEMA_VERSION
    bundle_id: str = ""
    dataset_id: str = ""
    artifact_ids: list[str] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    requested_use: str = "transition_export"
    registry_path: Optional[str] = None
    registry_decisions: list[dict[str, Any]] = field(default_factory=list)
    contamination_updates: list[dict[str, Any]] = field(default_factory=list)
    transition_record_ids: list[str] = field(default_factory=list)
    transition_record_paths: list[str] = field(default_factory=list)
    phase_space_coordinate_ids: list[str] = field(default_factory=list)
    phase_space_coordinate_paths: list[str] = field(default_factory=list)
    phase_space_trajectory_paths: list[str] = field(default_factory=list)
    claim_scope_ceiling: str = "exploratory_metric"
    evidence_level_ceiling: str = "L0_computational_artifact"
    generated_claim_scope: Optional[str] = None
    generated_evidence_levels: list[str] = field(default_factory=list)
    null_control_summary: dict[str, Any] = field(default_factory=lambda: {"status": "not_provided"})
    validation_summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    created_at: str = ""
    repo_commit: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── construction ────────────────────────────────────────────────────

    @classmethod
    def make(
        cls,
        *,
        dataset_id: str,
        artifact_ids: Optional[list[str]] = None,
        requested_use: str = "transition_export",
        transition_record_ids: Optional[list[str]] = None,
        phase_space_coordinate_ids: Optional[list[str]] = None,
        _now: Optional[datetime] = None,
        **extra: Any,
    ) -> "EvidenceBundleV1":
        artifact_ids = artifact_ids or []
        transition_record_ids = transition_record_ids or []
        phase_space_coordinate_ids = phase_space_coordinate_ids or []
        bundle_id = compute_bundle_id(
            dataset_id=dataset_id,
            artifact_ids=artifact_ids,
            requested_use=requested_use,
            transition_record_ids=transition_record_ids,
            phase_space_coordinate_ids=phase_space_coordinate_ids,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        kwargs: dict[str, Any] = dict(
            bundle_id=bundle_id,
            dataset_id=dataset_id,
            artifact_ids=list(artifact_ids),
            requested_use=requested_use,
            transition_record_ids=list(transition_record_ids),
            phase_space_coordinate_ids=list(phase_space_coordinate_ids),
            created_at=ts,
        )
        kwargs.update(extra)
        return cls(**kwargs)

    # ── serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "dataset_id": self.dataset_id,
            "artifact_ids": list(self.artifact_ids),
            "artifact_paths": dict(self.artifact_paths or {}),
            "requested_use": self.requested_use,
            "registry_path": self.registry_path,
            "registry_decisions": list(self.registry_decisions),
            "contamination_updates": list(self.contamination_updates),
            "transition_record_ids": list(self.transition_record_ids),
            "transition_record_paths": list(self.transition_record_paths),
            "phase_space_coordinate_ids": list(self.phase_space_coordinate_ids),
            "phase_space_coordinate_paths": list(self.phase_space_coordinate_paths),
            "phase_space_trajectory_paths": list(self.phase_space_trajectory_paths),
            "claim_scope_ceiling": self.claim_scope_ceiling,
            "evidence_level_ceiling": self.evidence_level_ceiling,
            "generated_claim_scope": self.generated_claim_scope,
            "generated_evidence_levels": list(self.generated_evidence_levels),
            "null_control_summary": dict(self.null_control_summary or {}),
            "validation_summary": dict(self.validation_summary or {}),
            "limitations": list(self.limitations),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "metadata": dict(self.metadata or {}),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvidenceBundleV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            bundle_id=d.get("bundle_id", ""),
            dataset_id=d.get("dataset_id", ""),
            artifact_ids=list(d.get("artifact_ids") or []),
            artifact_paths=dict(d.get("artifact_paths") or {}),
            requested_use=d.get("requested_use", "transition_export"),
            registry_path=d.get("registry_path"),
            registry_decisions=list(d.get("registry_decisions") or []),
            contamination_updates=list(d.get("contamination_updates") or []),
            transition_record_ids=list(d.get("transition_record_ids") or []),
            transition_record_paths=list(d.get("transition_record_paths") or []),
            phase_space_coordinate_ids=list(d.get("phase_space_coordinate_ids") or []),
            phase_space_coordinate_paths=list(d.get("phase_space_coordinate_paths") or []),
            phase_space_trajectory_paths=list(d.get("phase_space_trajectory_paths") or []),
            claim_scope_ceiling=d.get("claim_scope_ceiling", "exploratory_metric"),
            evidence_level_ceiling=d.get("evidence_level_ceiling", "L0_computational_artifact"),
            generated_claim_scope=d.get("generated_claim_scope"),
            generated_evidence_levels=list(d.get("generated_evidence_levels") or []),
            null_control_summary=dict(d.get("null_control_summary") or {"status": "not_provided"}),
            validation_summary=dict(d.get("validation_summary") or {}),
            limitations=list(d.get("limitations") or []),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit"),
            metadata=dict(d.get("metadata") or {}),
        )

    @classmethod
    def from_json(cls, text: str) -> "EvidenceBundleV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    # ── validation ──────────────────────────────────────────────────────

    def recompute_id(self) -> str:
        return compute_bundle_id(
            dataset_id=self.dataset_id,
            artifact_ids=self.artifact_ids,
            requested_use=self.requested_use,
            transition_record_ids=self.transition_record_ids,
            phase_space_coordinate_ids=self.phase_space_coordinate_ids,
        )

    def validate(self, *, repo_root: Optional[Path] = None) -> list[str]:
        """Return a list of error strings (empty = valid). Never raises."""
        errors: list[str] = []

        expected_id = self.recompute_id()
        if self.bundle_id and self.bundle_id != expected_id:
            errors.append(
                f"bundle_id '{self.bundle_id}' does not match the deterministic ID "
                f"computed from this bundle's identity fields ('{expected_id}')"
            )

        if repo_root is not None:
            errors.extend(validate_bundle(self, repo_root=repo_root))
        else:
            errors.extend(validate_bundle(self))
        return errors

    def validate_or_raise(self, *, repo_root: Optional[Path] = None) -> None:
        errors = self.validate(repo_root=repo_root)
        if errors:
            raise BundleValidationError("; ".join(errors))
