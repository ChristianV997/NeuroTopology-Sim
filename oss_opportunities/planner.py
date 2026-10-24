"""OpenSourceIntegrationPlanV1 -- turns a ranked `OpenSourceLeverageBatchV1`
into candidate next-action lists for a human to review. Nothing here
installs a dependency, clones/executes external code, or files/opens an
actual PR -- every list is a set of proposals, matching this milestone's
core principle: "This scout ranks and plans open-source leverage. It does
not perform the integration."
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from oss_opportunities.opportunity_batch import OpenSourceLeverageBatchV1
from oss_opportunities.validation import (
    OssOpportunityValidationError,
    PLANNER_VERSION,
    reject_forbidden_claim_fields,
    strict_json_loads,
    validate_integration_plan,
)

_SCHEMA_VERSION = "1"

# Conservative, actionable "what to build next" suggestions per
# leverage_category -- these name a *future milestone*, never an
# integration performed by this one (mission Phase F: "Do not actually
# implement those integrations here").
_PROPOSED_PR_BY_CATEGORY: dict[str, str] = {
    "document_ingestion": "Document Ingestion Adapter Registry v1",
    "web_literature_acquisition": "Firecrawl External Tool Record + Literature Source Adapter Plan v1",
    "code_graph_memory": "Awareness Studio Code/Research Graph Memory Design v1",
    "research_memory": "Awareness Studio Code/Research Graph Memory Design v1",
    "agent_harness": "Awareness Studio Agent Harness Emulation Notes v1",
    "workflow_orchestration": "Workflow Orchestration Pattern Reference v1 (not a job_runner replacement)",
    "report_visualization": "Static Report Diagram Renderer Plan v1",
    "frontend_stack": "SaaS Frontend Stack Decision Record v1",
    "backend_api_stack": "SaaS Frontend Stack Decision Record v1",
    "database_data_stack": "SaaS Frontend Stack Decision Record v1",
    "infra_observability_stack": "SaaS Infra/Observability Decision Record v1",
    "dataset_discovery": "Dataset Discovery External Tool Record v1",
}


def compute_plan_id(*, batch_id: str, selected_opportunity_ids: list[str], planner_version: str = PLANNER_VERSION) -> str:
    basis = {
        "batch_id": batch_id,
        "selected_opportunity_ids": sorted(selected_opportunity_ids),
        "planner_version": planner_version,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class OpenSourceIntegrationPlanV1:
    schema_version: str = _SCHEMA_VERSION
    plan_id: str = ""
    planner_version: str = PLANNER_VERSION
    batch_id: str = ""
    selected_opportunity_ids: list[str] = field(default_factory=list)
    immediate_adapter_candidates: list[dict[str, Any]] = field(default_factory=list)
    external_tool_record_candidates: list[dict[str, Any]] = field(default_factory=list)
    architecture_emulation_candidates: list[dict[str, Any]] = field(default_factory=list)
    documentation_reference_candidates: list[dict[str, Any]] = field(default_factory=list)
    license_review_queue: list[dict[str, Any]] = field(default_factory=list)
    security_review_queue: list[dict[str, Any]] = field(default_factory=list)
    deferred_candidates: list[dict[str, Any]] = field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)
    proposed_next_prs: list[str] = field(default_factory=list)
    generated_at: str = ""
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "planner_version": self.planner_version,
            "batch_id": self.batch_id,
            "selected_opportunity_ids": list(self.selected_opportunity_ids),
            "immediate_adapter_candidates": list(self.immediate_adapter_candidates),
            "external_tool_record_candidates": list(self.external_tool_record_candidates),
            "architecture_emulation_candidates": list(self.architecture_emulation_candidates),
            "documentation_reference_candidates": list(self.documentation_reference_candidates),
            "license_review_queue": list(self.license_review_queue),
            "security_review_queue": list(self.security_review_queue),
            "deferred_candidates": list(self.deferred_candidates),
            "rejected_candidates": list(self.rejected_candidates),
            "proposed_next_prs": list(self.proposed_next_prs),
            "generated_at": self.generated_at,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OpenSourceIntegrationPlanV1":
        if not isinstance(d, dict):
            raise OssOpportunityValidationError("plan payload must be a mapping")
        reject_forbidden_claim_fields(d, "plan payload")
        list_fields = (
            "selected_opportunity_ids", "immediate_adapter_candidates", "external_tool_record_candidates",
            "architecture_emulation_candidates", "documentation_reference_candidates", "license_review_queue",
            "security_review_queue", "deferred_candidates", "rejected_candidates", "proposed_next_prs", "limitations",
        )
        for key in list_fields:
            if key in d and not isinstance(d[key], list):
                raise OssOpportunityValidationError(f"plan {key} must be a list")
        if "metadata" in d and not isinstance(d["metadata"], dict):
            raise OssOpportunityValidationError("plan metadata must be a mapping")
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            plan_id=d.get("plan_id", ""),
            planner_version=d.get("planner_version", PLANNER_VERSION),
            batch_id=d.get("batch_id", ""),
            selected_opportunity_ids=list(d.get("selected_opportunity_ids") or []),
            immediate_adapter_candidates=list(d.get("immediate_adapter_candidates") or []),
            external_tool_record_candidates=list(d.get("external_tool_record_candidates") or []),
            architecture_emulation_candidates=list(d.get("architecture_emulation_candidates") or []),
            documentation_reference_candidates=list(d.get("documentation_reference_candidates") or []),
            license_review_queue=list(d.get("license_review_queue") or []),
            security_review_queue=list(d.get("security_review_queue") or []),
            deferred_candidates=list(d.get("deferred_candidates") or []),
            rejected_candidates=list(d.get("rejected_candidates") or []),
            proposed_next_prs=list(d.get("proposed_next_prs") or []),
            generated_at=d.get("generated_at", ""),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        self.validate_or_raise()
        return json.dumps(self.to_dict(), indent=2, sort_keys=False, allow_nan=False)

    @classmethod
    def from_json(cls, text: str) -> "OpenSourceIntegrationPlanV1":
        return cls.from_dict(strict_json_loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_integration_plan(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise OssOpportunityValidationError("; ".join(errors))


def plan_oss_integrations_from_opportunities(
    batch: OpenSourceLeverageBatchV1,
    *,
    max_selected: int = 20,
    planner_version: str = PLANNER_VERSION,
    _now: Optional[datetime] = None,
) -> OpenSourceIntegrationPlanV1:
    if not isinstance(max_selected, int) or isinstance(max_selected, bool) or max_selected < 0:
        raise OssOpportunityValidationError("max_selected must be a non-negative integer")
    batch_errs = batch.validate()
    if batch_errs:
        raise OssOpportunityValidationError(f"batch failed validation: {'; '.join(batch_errs)}")

    ts = (_now or datetime.now(timezone.utc)).isoformat()
    must_surface_actions = {"license_review_required", "security_review_required"}
    required = [entry for entry in batch.opportunities_ranked if entry["recommended_action"] in must_surface_actions]
    ordinary = [entry for entry in batch.opportunities_ranked if entry["recommended_action"] not in must_surface_actions]
    selected_set = {id(entry) for entry in required + ordinary[:max(0, max_selected - len(required))]}
    selected = [entry for entry in batch.opportunities_ranked if id(entry) in selected_set]
    omitted = [entry for entry in batch.opportunities_ranked if id(entry) not in selected_set]
    selected_ids = [e["opportunity_id"] for e in selected]

    immediate_adapter: list[dict[str, Any]] = []
    external_tool_record: list[dict[str, Any]] = []
    architecture_emulation: list[dict[str, Any]] = []
    docs_reference: list[dict[str, Any]] = []
    license_review_queue: list[dict[str, Any]] = []
    security_review_queue: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    categories_seen: set[str] = set()

    for entry in selected:
        action = entry["recommended_action"]
        repo = entry["repo_full_name"]
        category = entry["leverage_category"]
        license_review = entry.get("license_review") or {}
        categories_seen.add(category)

        item = {
            "opportunity_id": entry["opportunity_id"],
            "repo_full_name": repo,
            "leverage_category": category,
            "license_risk": license_review.get("license_risk", "unknown"),
            "commercial_core_policy": license_review.get("commercial_core_policy", "blocked_pending_review"),
            "not_executed": True,
            "not_installed": True,
        }

        if action == "integrate_as_optional_adapter":
            immediate_adapter.append(item)
        elif action == "integrate_as_external_tool_record":
            external_tool_record.append(item)
        elif action == "emulate_architecture_pattern":
            architecture_emulation.append(item)
        elif action == "create_docs_reference":
            docs_reference.append(item)
        elif action == "license_review_required":
            license_review_queue.append(item)
        elif action == "security_review_required":
            security_review_queue.append(item)
        elif action == "defer":
            deferred.append(item)
        elif action == "create_future_task":
            docs_reference.append(item)

    rejected = [
        {"repo_full_name": r["repo_full_name"], "reason": r["reason"], "not_executed": True}
        for r in batch.opportunities_rejected
    ]
    rejected.extend(
        {
            "repo_full_name": entry["repo_full_name"],
            "reason": f"max_selected_limit:{max_selected}",
            "not_executed": True,
            "omitted_by_max_selected": True,
        }
        for entry in omitted
    )

    proposed_next_prs: list[str] = []
    for category in sorted(categories_seen):
        pr_name = _PROPOSED_PR_BY_CATEGORY.get(category)
        if pr_name and pr_name not in proposed_next_prs:
            proposed_next_prs.append(pr_name)

    plan_id = compute_plan_id(batch_id=batch.batch_id, selected_opportunity_ids=selected_ids, planner_version=planner_version)

    plan = OpenSourceIntegrationPlanV1(
        plan_id=plan_id,
        planner_version=planner_version,
        batch_id=batch.batch_id,
        selected_opportunity_ids=selected_ids,
        immediate_adapter_candidates=immediate_adapter,
        external_tool_record_candidates=external_tool_record,
        architecture_emulation_candidates=architecture_emulation,
        documentation_reference_candidates=docs_reference,
        license_review_queue=license_review_queue,
        security_review_queue=security_review_queue,
        deferred_candidates=deferred,
        rejected_candidates=rejected,
        proposed_next_prs=proposed_next_prs,
        generated_at=ts,
        limitations=[
            "this plan proposes candidate next actions; it does not perform any integration",
            "no dependency has been installed, no repository has been cloned, no external code has been executed",
            "proposed_next_prs name future milestones only -- none of them has been implemented by this plan",
        ],
        provenance=f"planned from batch_id={batch.batch_id} via oss_opportunities.planner.plan_oss_integrations_from_opportunities",
    )
    plan.validate_or_raise()
    return plan
