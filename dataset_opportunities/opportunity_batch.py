"""DatasetOpportunityBatchV1 -- a ranked batch of `DatasetOpportunityRecordV1`
opportunities produced from a list of already-imported
`DatasetCandidateRecordV1` scouting records.

`build_opportunities_from_candidates` never queries signal data, never
materializes an `EEGDashDataset`, and never invokes any download/cache
function -- it only reads already-in-memory/already-on-disk
`DatasetCandidateRecordV1` objects and scores them via
`dataset_opportunities.scoring.score_opportunity`.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from dataset_importers.candidate_record import DatasetCandidateRecordV1
from dataset_opportunities.opportunity_record import DatasetOpportunityRecordV1
from dataset_opportunities.scoring import score_opportunity
from dataset_opportunities.validation import (
    DatasetOpportunityValidationError,
    validate_opportunity_batch,
)

_SCHEMA_VERSION = "1"
SCORING_VERSION = "1"

# A candidate scoring below this total is kept out of `ranked_opportunities`
# and moved to `rejected_opportunities` instead -- never silently dropped.
_MIN_RANKED_SCORE = 0.0


def _repo_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def compute_batch_id(*, source_catalog: str, query_summary: str, opportunity_ids: list[str], scoring_version: str = SCORING_VERSION) -> str:
    basis = {
        "source_catalog": source_catalog,
        "query_summary": query_summary,
        "opportunity_ids": sorted(opportunity_ids),
        "scoring_version": scoring_version,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class DatasetOpportunityBatchV1:
    schema_version: str = _SCHEMA_VERSION
    batch_id: str = ""
    source_catalog: str = ""
    query_summary: str = ""
    opportunity_ids: list[str] = field(default_factory=list)
    ranked_opportunities: list[dict[str, Any]] = field(default_factory=list)
    rejected_opportunities: list[dict[str, Any]] = field(default_factory=list)
    total_candidates_seen: int = 0
    total_opportunities_ranked: int = 0
    top_modalities: list[str] = field(default_factory=list)
    top_tasks: list[str] = field(default_factory=list)
    top_recommended_actions: list[str] = field(default_factory=list)
    generated_at: str = ""
    repo_commit: str = ""
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "source_catalog": self.source_catalog,
            "query_summary": self.query_summary,
            "opportunity_ids": list(self.opportunity_ids),
            "ranked_opportunities": list(self.ranked_opportunities),
            "rejected_opportunities": list(self.rejected_opportunities),
            "total_candidates_seen": self.total_candidates_seen,
            "total_opportunities_ranked": self.total_opportunities_ranked,
            "top_modalities": list(self.top_modalities),
            "top_tasks": list(self.top_tasks),
            "top_recommended_actions": list(self.top_recommended_actions),
            "generated_at": self.generated_at,
            "repo_commit": self.repo_commit,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DatasetOpportunityBatchV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            batch_id=d.get("batch_id", ""),
            source_catalog=d.get("source_catalog", ""),
            query_summary=d.get("query_summary", ""),
            opportunity_ids=list(d.get("opportunity_ids") or []),
            ranked_opportunities=list(d.get("ranked_opportunities") or []),
            rejected_opportunities=list(d.get("rejected_opportunities") or []),
            total_candidates_seen=int(d.get("total_candidates_seen", 0)),
            total_opportunities_ranked=int(d.get("total_opportunities_ranked", 0)),
            top_modalities=list(d.get("top_modalities") or []),
            top_tasks=list(d.get("top_tasks") or []),
            top_recommended_actions=list(d.get("top_recommended_actions") or []),
            generated_at=d.get("generated_at", ""),
            repo_commit=d.get("repo_commit", ""),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "DatasetOpportunityBatchV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_opportunity_batch(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise DatasetOpportunityValidationError("; ".join(errors))


def build_opportunities_from_candidates(
    candidate_records: list[DatasetCandidateRecordV1],
    *,
    query_summary: str = "",
    top_n: Optional[int] = None,
    scoring_version: str = SCORING_VERSION,
    _now: Optional[datetime] = None,
) -> DatasetOpportunityBatchV1:
    """Score every candidate, rank deterministically, and build a
    `DatasetOpportunityBatchV1`. Never queries signal data or invokes any
    download/cache function -- operates only on already-constructed
    `DatasetCandidateRecordV1` objects."""
    if not candidate_records:
        raise DatasetOpportunityValidationError("candidate_records must be non-empty -- nothing to score")

    for c in candidate_records:
        errs = c.validate()
        if errs:
            raise DatasetOpportunityValidationError(
                f"candidate {c.candidate_id!r} failed validation: {'; '.join(errs)}"
            )

    ts = (_now or datetime.now(timezone.utc)).isoformat()
    source_catalog = candidate_records[0].source_catalog if candidate_records else ""

    scored: list[tuple[DatasetCandidateRecordV1, DatasetOpportunityRecordV1]] = []
    for candidate in candidate_records:
        components = score_opportunity(candidate)
        opportunity = DatasetOpportunityRecordV1.make(
            source_catalog=candidate.source_catalog,
            source_dataset_id=candidate.source_dataset_id,
            source_candidate_id=candidate.candidate_id,
            scoring_version=scoring_version,
            dataset_name=candidate.display_name or candidate.source_dataset_id,
            modality=(candidate.modalities[0] if candidate.modalities else ""),
            task_labels=list(candidate.task_labels),
            available_metadata_fields=list(candidate.available_metadata),
            access_status=candidate.access_status,
            license=candidate.license,
            license_risk=candidate.license_risk,
            provenance=f"scored from candidate_id={candidate.candidate_id} via dataset_opportunities.scoring",
            limitations=[
                "metadata-only scouting opportunity; not evidence, not validated, not clinical",
                "score reflects scouting completeness heuristics only, not scientific or clinical relevance",
            ],
            _now=_now,
            **components,
        )
        opportunity.validate_or_raise()
        scored.append((candidate, opportunity))

    scored.sort(key=lambda pair: (-pair[1].total_score, pair[0].source_dataset_id, pair[1].opportunity_id))

    ranked: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for candidate, opportunity in scored:
        if opportunity.total_score >= _MIN_RANKED_SCORE and "reject" not in opportunity.recommended_next_actions:
            ranked.append(opportunity.to_dict())
        else:
            rejected.append(
                {
                    "opportunity_id": opportunity.opportunity_id,
                    "source_dataset_id": opportunity.source_dataset_id,
                    "total_score": opportunity.total_score,
                    "reason": (
                        "recommended_next_actions includes 'reject'"
                        if "reject" in opportunity.recommended_next_actions
                        else f"total_score {opportunity.total_score} below minimum ranked threshold {_MIN_RANKED_SCORE}"
                    ),
                }
            )

    if top_n is not None:
        ranked = ranked[:top_n]

    top_modalities = sorted({o["modality"] for o in ranked if o.get("modality")})
    top_tasks: list[str] = []
    for o in ranked:
        for task in o.get("task_labels") or []:
            if task not in top_tasks:
                top_tasks.append(task)
    top_recommended_actions: list[str] = []
    for o in ranked:
        for action in o.get("recommended_next_actions") or []:
            if action not in top_recommended_actions:
                top_recommended_actions.append(action)

    opportunity_ids = [o["opportunity_id"] for o in ranked]
    batch_id = compute_batch_id(
        source_catalog=source_catalog, query_summary=query_summary,
        opportunity_ids=opportunity_ids, scoring_version=scoring_version,
    )

    batch = DatasetOpportunityBatchV1(
        batch_id=batch_id,
        source_catalog=source_catalog,
        query_summary=query_summary,
        opportunity_ids=opportunity_ids,
        ranked_opportunities=ranked,
        rejected_opportunities=rejected,
        total_candidates_seen=len(candidate_records),
        total_opportunities_ranked=len(ranked),
        top_modalities=top_modalities,
        top_tasks=top_tasks,
        top_recommended_actions=top_recommended_actions,
        generated_at=ts,
        repo_commit=_repo_commit(),
        limitations=[
            "this batch ranks scouting opportunities; it does not create evidence",
            "real analysis requires separate acquisition, explicit mappings, bounded feature recipes, and governed report generation",
        ],
        provenance=f"built from {len(candidate_records)} candidate(s) via dataset_opportunities.opportunity_batch.build_opportunities_from_candidates",
    )
    batch.validate_or_raise()
    return batch
