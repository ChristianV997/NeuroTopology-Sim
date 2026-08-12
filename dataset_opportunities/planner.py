"""DatasetOpportunityPlanV1 -- turns a ranked `DatasetOpportunityBatchV1`
into candidate next-action lists for a human to review. Nothing here
executes an acquisition, downloads anything, runs a benchmark pack, searches
literature, or contacts a researcher -- every list is a set of proposals,
not actions taken.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from dataset_opportunities.opportunity_batch import DatasetOpportunityBatchV1
from dataset_opportunities.validation import (
    DatasetOpportunityValidationError,
    validate_opportunity_plan,
)

_SCHEMA_VERSION = "1"
PLANNER_VERSION = "1"


def compute_plan_id(*, opportunity_batch_id: str, selected_opportunity_ids: list[str], planner_version: str = PLANNER_VERSION) -> str:
    basis = {
        "opportunity_batch_id": opportunity_batch_id,
        "selected_opportunity_ids": sorted(selected_opportunity_ids),
        "planner_version": planner_version,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class DatasetOpportunityPlanV1:
    schema_version: str = _SCHEMA_VERSION
    plan_id: str = ""
    opportunity_batch_id: str = ""
    selected_opportunity_ids: list[str] = field(default_factory=list)
    planned_acquisition_candidates: list[dict[str, Any]] = field(default_factory=list)
    planned_benchmark_pack_candidates: list[dict[str, Any]] = field(default_factory=list)
    planned_literature_review_tasks: list[dict[str, Any]] = field(default_factory=list)
    planned_outreach_candidates: list[dict[str, Any]] = field(default_factory=list)
    awareness_studio_manifest_path: str = ""
    generated_at: str = ""
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "opportunity_batch_id": self.opportunity_batch_id,
            "selected_opportunity_ids": list(self.selected_opportunity_ids),
            "planned_acquisition_candidates": list(self.planned_acquisition_candidates),
            "planned_benchmark_pack_candidates": list(self.planned_benchmark_pack_candidates),
            "planned_literature_review_tasks": list(self.planned_literature_review_tasks),
            "planned_outreach_candidates": list(self.planned_outreach_candidates),
            "awareness_studio_manifest_path": self.awareness_studio_manifest_path,
            "generated_at": self.generated_at,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DatasetOpportunityPlanV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            plan_id=d.get("plan_id", ""),
            opportunity_batch_id=d.get("opportunity_batch_id", ""),
            selected_opportunity_ids=list(d.get("selected_opportunity_ids") or []),
            planned_acquisition_candidates=list(d.get("planned_acquisition_candidates") or []),
            planned_benchmark_pack_candidates=list(d.get("planned_benchmark_pack_candidates") or []),
            planned_literature_review_tasks=list(d.get("planned_literature_review_tasks") or []),
            planned_outreach_candidates=list(d.get("planned_outreach_candidates") or []),
            awareness_studio_manifest_path=d.get("awareness_studio_manifest_path", ""),
            generated_at=d.get("generated_at", ""),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "DatasetOpportunityPlanV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_opportunity_plan(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise DatasetOpportunityValidationError("; ".join(errors))


def plan_next_actions_from_opportunities(
    batch: DatasetOpportunityBatchV1,
    *,
    max_selected: int = 10,
    manifest_output_path: str = "",
    planner_version: str = PLANNER_VERSION,
    _now: Optional[datetime] = None,
) -> DatasetOpportunityPlanV1:
    batch_errs = batch.validate()
    if batch_errs:
        raise DatasetOpportunityValidationError(f"batch failed validation: {'; '.join(batch_errs)}")

    ts = (_now or datetime.now(timezone.utc)).isoformat()
    selected = batch.ranked_opportunities[:max_selected]
    selected_ids = [o["opportunity_id"] for o in selected]

    acquisition: list[dict[str, Any]] = []
    benchmark: list[dict[str, Any]] = []
    literature: list[dict[str, Any]] = []
    outreach: list[dict[str, Any]] = []

    for o in selected:
        actions = o.get("recommended_next_actions") or []
        oid = o["opportunity_id"]
        dsid = o["source_dataset_id"]

        if "acquisition_plan_only" in actions:
            unknown = o.get("access_status") in ("unknown", "restricted") or o.get("license_risk") == "unknown_high"
            acquisition.append(
                {
                    "opportunity_id": oid,
                    "source_dataset_id": dsid,
                    "suggested_requested_action": "scan_existing_local" if unknown else "plan_download",
                    "safety_notes": "not executed -- proposal only, requires separate dataset_acquisition.planner call",
                }
            )

        if "benchmark_pack_proposal" in actions:
            benchmark.append(
                {
                    "opportunity_id": oid,
                    "source_dataset_id": dsid,
                    "proposed_input_mode": "metadata_only",
                    "missing_requirements": [
                        "explicit condition/state mapping",
                        "bounded feature recipe",
                        "governed report generation",
                    ],
                }
            )

        if "literature_review_task" in actions:
            literature.append(
                {
                    "opportunity_id": oid,
                    "source_dataset_id": dsid,
                    "topic": o.get("dataset_name", dsid),
                    "task_labels": o.get("task_labels") or [],
                    "search_terms": [dsid] + list(o.get("task_labels") or []),
                }
            )

        if "researcher_outreach_candidate" in actions:
            outreach.append(
                {
                    "opportunity_id": oid,
                    "source_dataset_id": dsid,
                    "identifier": dsid,
                    "why_relevant": f"outreach_potential={o.get('outreach_potential')}",
                    "requires_human_review": True,
                    "not_sent": True,
                }
            )

    plan_id = compute_plan_id(
        opportunity_batch_id=batch.batch_id, selected_opportunity_ids=selected_ids, planner_version=planner_version,
    )

    plan = DatasetOpportunityPlanV1(
        plan_id=plan_id,
        opportunity_batch_id=batch.batch_id,
        selected_opportunity_ids=selected_ids,
        planned_acquisition_candidates=acquisition,
        planned_benchmark_pack_candidates=benchmark,
        planned_literature_review_tasks=literature,
        planned_outreach_candidates=outreach,
        awareness_studio_manifest_path=manifest_output_path,
        generated_at=ts,
        limitations=[
            "this plan proposes candidate next actions; it does not execute any of them",
            "no researcher has been contacted, no dataset has been downloaded, no benchmark pack has been generated",
        ],
        provenance=f"planned from opportunity_batch_id={batch.batch_id} via dataset_opportunities.planner.plan_next_actions_from_opportunities",
    )
    plan.validate_or_raise()
    return plan
