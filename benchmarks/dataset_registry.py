"""DatasetRecordV1 -- registry-level usage tracking for a dataset.

Tracks HOW a dataset may be used across the research pipeline (discovery
vs. confirmation), not scientific results. See
docs/benchmark_dataset_registry.md for the full rationale. Structural
validation lives in `benchmarks.validation`; use-policy decisions live in
`benchmarks.split_policy`; lock issuance/consumption lives in
`benchmarks.holdout_lock` -- this module defines only the record shape and
its serialization, mirroring `transitions.record.TransitionRecordV1`'s
relationship to `transitions.governance`.

The CLI lives in `benchmarks.export_registry` (``python -m
benchmarks.export_registry ...``); this module is not runnable as a script,
mirroring how `transitions.record.TransitionRecordV1` has no CLI of its own
even though `transitions.export_from_results` does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from benchmarks.validation import validate_dataset_record

_SCHEMA_VERSION = "1"


@dataclass
class DatasetRecordV1:
    schema_version: str = _SCHEMA_VERSION
    dataset_id: str = ""
    display_name: str = ""
    modalities: list[str] = field(default_factory=list)
    transition_classes: list[str] = field(default_factory=list)
    source_states: list[str] = field(default_factory=list)
    target_states: list[str] = field(default_factory=list)
    artifact_paths: list[str] = field(default_factory=list)
    artifact_kinds: list[str] = field(default_factory=list)
    current_role: str = "exploration"
    allowed_uses: list[str] = field(default_factory=list)
    forbidden_uses: list[str] = field(default_factory=list)
    contamination_status: str = "unseen"
    seen_by: list[str] = field(default_factory=list)
    claim_scope_ceiling: str = "exploratory_metric"
    evidence_level_ceiling: str = "L0_computational_artifact"
    label_quality: str = ""
    provenance: str = ""
    limitations: list[str] = field(default_factory=list)
    validation_lock: Optional[dict[str, Any]] = None
    prospective_protocol_id: Optional[str] = None
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(cls, *, dataset_id: str, _now: Optional[datetime] = None, **kwargs: Any) -> "DatasetRecordV1":
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(dataset_id=dataset_id, created_at=ts, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "display_name": self.display_name,
            "modalities": list(self.modalities),
            "transition_classes": list(self.transition_classes),
            "source_states": list(self.source_states),
            "target_states": list(self.target_states),
            "artifact_paths": list(self.artifact_paths),
            "artifact_kinds": list(self.artifact_kinds),
            "current_role": self.current_role,
            "allowed_uses": list(self.allowed_uses),
            "forbidden_uses": list(self.forbidden_uses),
            "contamination_status": self.contamination_status,
            "seen_by": list(self.seen_by),
            "claim_scope_ceiling": self.claim_scope_ceiling,
            "evidence_level_ceiling": self.evidence_level_ceiling,
            "label_quality": self.label_quality,
            "provenance": self.provenance,
            "limitations": list(self.limitations),
            "validation_lock": dict(self.validation_lock) if self.validation_lock else None,
            "prospective_protocol_id": self.prospective_protocol_id,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DatasetRecordV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            dataset_id=d.get("dataset_id", ""),
            display_name=d.get("display_name", ""),
            modalities=list(d.get("modalities") or []),
            transition_classes=list(d.get("transition_classes") or []),
            source_states=list(d.get("source_states") or []),
            target_states=list(d.get("target_states") or []),
            artifact_paths=list(d.get("artifact_paths") or []),
            artifact_kinds=list(d.get("artifact_kinds") or []),
            current_role=d.get("current_role", "exploration"),
            allowed_uses=list(d.get("allowed_uses") or []),
            forbidden_uses=list(d.get("forbidden_uses") or []),
            contamination_status=d.get("contamination_status", "unseen"),
            seen_by=list(d.get("seen_by") or []),
            claim_scope_ceiling=d.get("claim_scope_ceiling", "exploratory_metric"),
            evidence_level_ceiling=d.get("evidence_level_ceiling", "L0_computational_artifact"),
            label_quality=d.get("label_quality", ""),
            provenance=d.get("provenance", ""),
            limitations=list(d.get("limitations") or []),
            validation_lock=d.get("validation_lock"),
            prospective_protocol_id=d.get("prospective_protocol_id"),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def validate(self) -> list[str]:
        return validate_dataset_record(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            from benchmarks.validation import RegistryValidationError

            raise RegistryValidationError("; ".join(errors))
