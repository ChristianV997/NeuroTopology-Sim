"""ArtifactRecordV1 -- registry-level usage tracking for a single committed
artifact (or a documented candidate/unstructured placeholder) within a dataset.

A dataset can have multiple, differently-computed feature families sharing
the same dataset_id (e.g. ds005620's cohort_summary vs spatial_defect_map,
see docs/transition_science_foundation.md); each gets its own
ArtifactRecordV1 rather than being merged into the dataset-level record, so
contamination/role tracking stays feature-family granular -- an exporter
reading only the spatial_defect_map family should not be blocked because
cohort_summary was separately used for theory generation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from benchmarks.validation import validate_artifact_record

_SCHEMA_VERSION = "1"


def compute_artifact_id(
    *,
    dataset_id: str,
    path: str,
    artifact_kind: str,
    modality: Optional[str],
    source_state: Optional[str],
    target_state: Optional[str],
) -> str:
    """Stable sha256[:16] over the artifact's identity fields.

    Mirrors `transitions.record.compute_transition_id`: excludes
    created_at, role/contamination/lock state, and free text -- none of
    those change which artifact is being described. Two records built from
    identical identity fields always produce the same ID.
    """
    basis = {
        "dataset_id": dataset_id,
        "path": path,
        "artifact_kind": artifact_kind,
        "modality": modality,
        "source_state": source_state,
        "target_state": target_state,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class ArtifactRecordV1:
    schema_version: str = _SCHEMA_VERSION
    artifact_id: str = ""
    dataset_id: str = ""
    path: str = ""
    artifact_kind: str = ""
    # "committed_artifact" (real, structured, parseable file on disk) or
    # "candidate_unstructured" (a dataset that has been discussed/processed
    # but has no committed structured artifact yet -- e.g. a prose report
    # only). See validation.py rule 10.
    record_kind: str = "committed_artifact"
    external: bool = False
    modality: str = ""
    feature_families: list[str] = field(default_factory=list)
    source_state: Optional[str] = None
    target_state: Optional[str] = None
    current_role: str = "exploration"
    allowed_uses: list[str] = field(default_factory=list)
    forbidden_uses: list[str] = field(default_factory=list)
    contamination_status: str = "unseen"
    seen_by: list[str] = field(default_factory=list)
    produced_by: str = ""
    consumed_by: list[str] = field(default_factory=list)
    claim_scope_ceiling: str = "exploratory_metric"
    evidence_level_ceiling: str = "L0_computational_artifact"
    limitations: list[str] = field(default_factory=list)
    validation_lock: Optional[dict[str, Any]] = None
    prospective_protocol_id: Optional[str] = None
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        dataset_id: str,
        path: str,
        artifact_kind: str,
        modality: str = "",
        source_state: Optional[str] = None,
        target_state: Optional[str] = None,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "ArtifactRecordV1":
        artifact_id = compute_artifact_id(
            dataset_id=dataset_id,
            path=path,
            artifact_kind=artifact_kind,
            modality=modality,
            source_state=source_state,
            target_state=target_state,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            artifact_id=artifact_id,
            dataset_id=dataset_id,
            path=path,
            artifact_kind=artifact_kind,
            modality=modality,
            source_state=source_state,
            target_state=target_state,
            created_at=ts,
            **kwargs,
        )

    def recompute_id(self) -> str:
        return compute_artifact_id(
            dataset_id=self.dataset_id,
            path=self.path,
            artifact_kind=self.artifact_kind,
            modality=self.modality,
            source_state=self.source_state,
            target_state=self.target_state,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "dataset_id": self.dataset_id,
            "path": self.path,
            "artifact_kind": self.artifact_kind,
            "record_kind": self.record_kind,
            "external": self.external,
            "modality": self.modality,
            "feature_families": list(self.feature_families),
            "source_state": self.source_state,
            "target_state": self.target_state,
            "current_role": self.current_role,
            "allowed_uses": list(self.allowed_uses),
            "forbidden_uses": list(self.forbidden_uses),
            "contamination_status": self.contamination_status,
            "seen_by": list(self.seen_by),
            "produced_by": self.produced_by,
            "consumed_by": list(self.consumed_by),
            "claim_scope_ceiling": self.claim_scope_ceiling,
            "evidence_level_ceiling": self.evidence_level_ceiling,
            "limitations": list(self.limitations),
            "validation_lock": dict(self.validation_lock) if self.validation_lock else None,
            "prospective_protocol_id": self.prospective_protocol_id,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ArtifactRecordV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            artifact_id=d.get("artifact_id", ""),
            dataset_id=d.get("dataset_id", ""),
            path=d.get("path", ""),
            artifact_kind=d.get("artifact_kind", ""),
            record_kind=d.get("record_kind", "committed_artifact"),
            external=bool(d.get("external", False)),
            modality=d.get("modality", ""),
            feature_families=list(d.get("feature_families") or []),
            source_state=d.get("source_state"),
            target_state=d.get("target_state"),
            current_role=d.get("current_role", "exploration"),
            allowed_uses=list(d.get("allowed_uses") or []),
            forbidden_uses=list(d.get("forbidden_uses") or []),
            contamination_status=d.get("contamination_status", "unseen"),
            seen_by=list(d.get("seen_by") or []),
            produced_by=d.get("produced_by", ""),
            consumed_by=list(d.get("consumed_by") or []),
            claim_scope_ceiling=d.get("claim_scope_ceiling", "exploratory_metric"),
            evidence_level_ceiling=d.get("evidence_level_ceiling", "L0_computational_artifact"),
            limitations=list(d.get("limitations") or []),
            validation_lock=d.get("validation_lock"),
            prospective_protocol_id=d.get("prospective_protocol_id"),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def validate(self, *, repo_root: Optional[Path] = None) -> list[str]:
        if repo_root is not None:
            return validate_artifact_record(self, repo_root=repo_root)
        return validate_artifact_record(self)

    def validate_or_raise(self, *, repo_root: Optional[Path] = None) -> None:
        errors = self.validate(repo_root=repo_root)
        if errors:
            from benchmarks.validation import RegistryValidationError

            raise RegistryValidationError("; ".join(errors))
