"""TransitionRecordV1 — canonical, governance-aware state-transition artifact.

Mirrors the deterministic-ID / to_dict / from_dict / write_json conventions
already established by `runs.run_record.RunRecordV1` (the repo's canonical
run artifact) so the two schemas feel like siblings, while representing a
different object: not "one pipeline run" but "one observed or hypothesized
state transition," reusable across EEG, fMRI, topology, connectivity, and
future modalities.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from transitions.features import validate_feature_names
from transitions.governance import DEFAULT_NULL_CONTROL_SUMMARY, validate_governance

_SCHEMA_VERSION = "1"

RECORD_LEVELS: frozenset[str] = frozenset({"subject", "cohort"})

# claim_scope values that permit an unlabeled, exploratory transition (no
# source_state/target_state) — see transitions.governance.ALLOWED_CLAIM_SCOPES
# for the full scope vocabulary; only these two are narrow enough to allow
# missing state labels.
_UNLABELED_ALLOWED_SCOPES: frozenset[str] = frozenset(
    {"computational_artifact", "exploratory_metric"}
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_transition_id(
    *,
    dataset_id: Optional[str],
    subject_id: Optional[str],
    session_id: Optional[str],
    source_state: Optional[str],
    target_state: Optional[str],
    modality: Optional[str],
    feature_names: list[str],
) -> str:
    """Stable sha256[:16] over the scientific-identity fields only.

    Excludes created_at, artifact paths, computed summaries, claim_scope,
    evidence_level, and free-text fields — none of those change what
    transition is being described. Two records built from identical
    dataset_id/subject_id/session_id/source_state/target_state/modality/
    feature_names always produce the same ID; changing any one of those
    seven fields always changes it.
    """
    basis = {
        "dataset_id": dataset_id,
        "subject_id": subject_id,
        "session_id": session_id,
        "source_state": source_state,
        "target_state": target_state,
        "modality": modality,
        "feature_names": sorted(feature_names or []),
    }
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:16]


class TransitionValidationError(ValueError):
    """Raised when a TransitionRecordV1 fails structural or governance validation."""


@dataclass
class TransitionRecordV1:
    schema_version: str = _SCHEMA_VERSION
    transition_id: str = ""
    dataset_id: Optional[str] = None
    subject_id: Optional[str] = None
    session_id: Optional[str] = None
    record_level: str = "subject"
    modality: Optional[str] = None
    source_state: Optional[str] = None
    target_state: Optional[str] = None
    transition_class: Optional[str] = None
    time_axis: Optional[dict[str, Any]] = None
    feature_names: list[str] = field(default_factory=list)
    trajectory_artifact: Optional[str] = None
    delta_summary: Optional[dict[str, Any]] = None
    velocity_summary: Optional[dict[str, Any]] = None
    duration: Optional[float] = None
    intervention: Optional[dict[str, Any]] = None
    preprocessing_provenance: Optional[dict[str, Any]] = None
    null_control_summary: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_NULL_CONTROL_SUMMARY)
    )
    state_label_confidence: Optional[float] = None
    claim_scope: str = "computational_artifact"
    evidence_level: str = "L0_computational_artifact"
    limitations: list[str] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    repo_commit: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── construction ────────────────────────────────────────────────────

    @classmethod
    def make(
        cls,
        *,
        dataset_id: Optional[str],
        subject_id: Optional[str] = None,
        session_id: Optional[str] = None,
        record_level: str = "subject",
        modality: Optional[str] = None,
        source_state: Optional[str] = None,
        target_state: Optional[str] = None,
        transition_class: Optional[str] = None,
        feature_names: Optional[list[str]] = None,
        limitations: Optional[list[str]] = None,
        claim_scope: str = "computational_artifact",
        evidence_level: str = "L0_computational_artifact",
        repo_commit: Optional[str] = None,
        _now: Optional[datetime] = None,
        **extra: Any,
    ) -> "TransitionRecordV1":
        """Build a record with a freshly computed deterministic transition_id.

        `**extra` accepts any other dataclass field (time_axis, duration,
        intervention, preprocessing_provenance, null_control_summary,
        state_label_confidence, artifact_paths, metadata, ...).
        """
        names = feature_names or []
        transition_id = compute_transition_id(
            dataset_id=dataset_id,
            subject_id=subject_id,
            session_id=session_id,
            source_state=source_state,
            target_state=target_state,
            modality=modality,
            feature_names=names,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        kwargs: dict[str, Any] = dict(
            transition_id=transition_id,
            dataset_id=dataset_id,
            subject_id=subject_id,
            session_id=session_id,
            record_level=record_level,
            modality=modality,
            source_state=source_state,
            target_state=target_state,
            transition_class=transition_class,
            feature_names=list(names),
            limitations=list(limitations or []),
            claim_scope=claim_scope,
            evidence_level=evidence_level,
            created_at=ts,
            repo_commit=repo_commit,
        )
        kwargs.update(extra)
        return cls(**kwargs)

    # ── serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "transition_id": self.transition_id,
            "dataset_id": self.dataset_id,
            "subject_id": self.subject_id,
            "session_id": self.session_id,
            "record_level": self.record_level,
            "modality": self.modality,
            "source_state": self.source_state,
            "target_state": self.target_state,
            "transition_class": self.transition_class,
            "time_axis": self.time_axis,
            "feature_names": list(self.feature_names),
            "trajectory_artifact": self.trajectory_artifact,
            "delta_summary": self.delta_summary,
            "velocity_summary": self.velocity_summary,
            "duration": self.duration,
            "intervention": self.intervention,
            "preprocessing_provenance": self.preprocessing_provenance,
            "null_control_summary": dict(self.null_control_summary or {}),
            "state_label_confidence": self.state_label_confidence,
            "claim_scope": self.claim_scope,
            "evidence_level": self.evidence_level,
            "limitations": list(self.limitations),
            "artifact_paths": dict(self.artifact_paths or {}),
            "created_at": self.created_at,
            "repo_commit": self.repo_commit,
            "metadata": dict(self.metadata or {}),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TransitionRecordV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            transition_id=d.get("transition_id", ""),
            dataset_id=d.get("dataset_id"),
            subject_id=d.get("subject_id"),
            session_id=d.get("session_id"),
            record_level=d.get("record_level", "subject"),
            modality=d.get("modality"),
            source_state=d.get("source_state"),
            target_state=d.get("target_state"),
            transition_class=d.get("transition_class"),
            time_axis=d.get("time_axis"),
            feature_names=list(d.get("feature_names") or []),
            trajectory_artifact=d.get("trajectory_artifact"),
            delta_summary=d.get("delta_summary"),
            velocity_summary=d.get("velocity_summary"),
            duration=d.get("duration"),
            intervention=d.get("intervention"),
            preprocessing_provenance=d.get("preprocessing_provenance"),
            null_control_summary=dict(
                d.get("null_control_summary") or DEFAULT_NULL_CONTROL_SUMMARY
            ),
            state_label_confidence=d.get("state_label_confidence"),
            claim_scope=d.get("claim_scope", "computational_artifact"),
            evidence_level=d.get("evidence_level", "L0_computational_artifact"),
            limitations=list(d.get("limitations") or []),
            artifact_paths=dict(d.get("artifact_paths") or {}),
            created_at=d.get("created_at", ""),
            repo_commit=d.get("repo_commit"),
            metadata=dict(d.get("metadata") or {}),
        )

    @classmethod
    def from_json(cls, text: str) -> "TransitionRecordV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    # ── validation ──────────────────────────────────────────────────────

    def recompute_id(self) -> str:
        """Recompute the deterministic ID from this record's current identity fields."""
        return compute_transition_id(
            dataset_id=self.dataset_id,
            subject_id=self.subject_id,
            session_id=self.session_id,
            source_state=self.source_state,
            target_state=self.target_state,
            modality=self.modality,
            feature_names=self.feature_names,
        )

    def validate(self) -> list[str]:
        """Return a list of error strings (empty = valid). Never raises."""
        errors: list[str] = []

        if not self.dataset_id:
            errors.append("dataset_id is required")

        if self.record_level not in RECORD_LEVELS:
            errors.append(
                f"record_level '{self.record_level}' must be one of {sorted(RECORD_LEVELS)}"
            )
        elif self.record_level == "subject" and not self.subject_id:
            errors.append("record_level 'subject' requires subject_id")
        elif self.record_level == "cohort" and self.subject_id:
            errors.append(
                "record_level 'cohort' must not carry a single subject_id "
                "(use metadata.subject_count / metadata.subject_ids instead)"
            )

        states_missing = not self.source_state or not self.target_state
        if states_missing and self.claim_scope not in _UNLABELED_ALLOWED_SCOPES:
            errors.append(
                "source_state and target_state are required unless claim_scope is "
                f"one of {sorted(_UNLABELED_ALLOWED_SCOPES)} (unlabeled exploratory transition)"
            )

        if self.state_label_confidence is not None and not (
            0.0 <= float(self.state_label_confidence) <= 1.0
        ):
            errors.append("state_label_confidence must be between 0.0 and 1.0")

        if self.duration is not None and float(self.duration) < 0.0:
            errors.append("duration must be non-negative")

        errors.extend(validate_feature_names(self.feature_names))

        expected_id = self.recompute_id()
        if self.transition_id and self.transition_id != expected_id:
            errors.append(
                f"transition_id '{self.transition_id}' does not match the deterministic "
                f"ID computed from this record's identity fields ('{expected_id}')"
            )

        errors.extend(validate_governance(self))

        return errors

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise TransitionValidationError("; ".join(errors))
