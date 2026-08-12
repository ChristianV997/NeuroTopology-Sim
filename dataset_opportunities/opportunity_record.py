"""DatasetOpportunityRecordV1 -- a ranked scouting opportunity derived from
an already-imported `dataset_importers.candidate_record.DatasetCandidateRecordV1`.

An opportunity never stands alone: `source_candidate_id`/`source_catalog`/
`source_dataset_id` always point back to the candidate it was scored from
(mission validation rule 3). This module contains no scoring logic itself
(see `dataset_opportunities.scoring`) and no acquisition/execution logic
(see `dataset_opportunities.planner`) -- it is purely the schema plus
deterministic id/roundtrip/validation plumbing, mirroring every other
sibling-schema module in this repository.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from dataset_opportunities.validation import (
    DatasetOpportunityValidationError,
    validate_opportunity_record,
)

_SCHEMA_VERSION = "1"

# Bumping this changes every opportunity_id -- it is part of the id basis so
# that a scoring-methodology change never collides with ids computed under a
# prior methodology.
SCORING_VERSION = "1"


def compute_opportunity_id(
    *, source_catalog: str, source_dataset_id: str, source_candidate_id: str, scoring_version: str = SCORING_VERSION
) -> str:
    """Stable sha256[:16], deliberately excluding any timestamp -- an
    opportunity is meant to be a reproducible output of a scoring run, not an
    independent execution attempt (unlike this repository's execution-event
    ids elsewhere)."""
    basis = {
        "source_catalog": source_catalog,
        "source_dataset_id": source_dataset_id,
        "source_candidate_id": source_candidate_id,
        "scoring_version": scoring_version,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class DatasetOpportunityRecordV1:
    schema_version: str = _SCHEMA_VERSION
    opportunity_id: str = ""
    source_candidate_id: str = ""
    source_catalog: str = ""
    source_dataset_id: str = ""
    dataset_name: str = ""
    modality: str = ""
    task_labels: list[str] = field(default_factory=list)
    available_metadata_fields: list[str] = field(default_factory=list)
    access_status: str = "unknown"
    license: str = "unknown"
    license_risk: str = "unknown_high"
    estimated_size_status: str = "not_assessed"
    loadability_status: str = "unknown"
    bids_compliance_status: str = "unknown"
    participant_count_status: str = "unknown"
    recording_duration_status: str = "unknown"
    state_mapping_potential: str = "unknown"
    transition_analysis_potential: str = "unknown"
    benchmark_pack_potential: str = "unknown"
    literature_link_potential: str = "unknown"
    outreach_potential: str = "insufficient_data"
    commercial_demo_potential: str = "unknown"
    risk_flags: list[str] = field(default_factory=list)
    recommended_next_actions: list[str] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)
    score_components: dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        source_catalog: str,
        source_dataset_id: str,
        source_candidate_id: str,
        scoring_version: str = SCORING_VERSION,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "DatasetOpportunityRecordV1":
        opportunity_id = compute_opportunity_id(
            source_catalog=source_catalog,
            source_dataset_id=source_dataset_id,
            source_candidate_id=source_candidate_id,
            scoring_version=scoring_version,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            opportunity_id=opportunity_id,
            source_catalog=source_catalog,
            source_dataset_id=source_dataset_id,
            source_candidate_id=source_candidate_id,
            created_at=ts,
            **kwargs,
        )

    def recompute_id(self, *, scoring_version: str = SCORING_VERSION) -> str:
        return compute_opportunity_id(
            source_catalog=self.source_catalog,
            source_dataset_id=self.source_dataset_id,
            source_candidate_id=self.source_candidate_id,
            scoring_version=scoring_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "opportunity_id": self.opportunity_id,
            "source_candidate_id": self.source_candidate_id,
            "source_catalog": self.source_catalog,
            "source_dataset_id": self.source_dataset_id,
            "dataset_name": self.dataset_name,
            "modality": self.modality,
            "task_labels": list(self.task_labels),
            "available_metadata_fields": list(self.available_metadata_fields),
            "access_status": self.access_status,
            "license": self.license,
            "license_risk": self.license_risk,
            "estimated_size_status": self.estimated_size_status,
            "loadability_status": self.loadability_status,
            "bids_compliance_status": self.bids_compliance_status,
            "participant_count_status": self.participant_count_status,
            "recording_duration_status": self.recording_duration_status,
            "state_mapping_potential": self.state_mapping_potential,
            "transition_analysis_potential": self.transition_analysis_potential,
            "benchmark_pack_potential": self.benchmark_pack_potential,
            "literature_link_potential": self.literature_link_potential,
            "outreach_potential": self.outreach_potential,
            "commercial_demo_potential": self.commercial_demo_potential,
            "risk_flags": list(self.risk_flags),
            "recommended_next_actions": list(self.recommended_next_actions),
            "blocked_actions": list(self.blocked_actions),
            "score_components": dict(self.score_components or {}),
            "total_score": self.total_score,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DatasetOpportunityRecordV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            opportunity_id=d.get("opportunity_id", ""),
            source_candidate_id=d.get("source_candidate_id", ""),
            source_catalog=d.get("source_catalog", ""),
            source_dataset_id=d.get("source_dataset_id", ""),
            dataset_name=d.get("dataset_name", ""),
            modality=d.get("modality", ""),
            task_labels=list(d.get("task_labels") or []),
            available_metadata_fields=list(d.get("available_metadata_fields") or []),
            access_status=d.get("access_status", "unknown"),
            license=d.get("license", "unknown"),
            license_risk=d.get("license_risk", "unknown_high"),
            estimated_size_status=d.get("estimated_size_status", "unknown"),
            loadability_status=d.get("loadability_status", "unknown"),
            bids_compliance_status=d.get("bids_compliance_status", "unknown"),
            participant_count_status=d.get("participant_count_status", "unknown"),
            recording_duration_status=d.get("recording_duration_status", "unknown"),
            state_mapping_potential=d.get("state_mapping_potential", "unknown"),
            transition_analysis_potential=d.get("transition_analysis_potential", "unknown"),
            benchmark_pack_potential=d.get("benchmark_pack_potential", "unknown"),
            literature_link_potential=d.get("literature_link_potential", "unknown"),
            outreach_potential=d.get("outreach_potential", "insufficient_data"),
            commercial_demo_potential=d.get("commercial_demo_potential", "unknown"),
            risk_flags=list(d.get("risk_flags") or []),
            recommended_next_actions=list(d.get("recommended_next_actions") or []),
            blocked_actions=list(d.get("blocked_actions") or []),
            score_components=dict(d.get("score_components") or {}),
            total_score=float(d.get("total_score", 0.0)),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "DatasetOpportunityRecordV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_opportunity_record(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise DatasetOpportunityValidationError("; ".join(errors))
