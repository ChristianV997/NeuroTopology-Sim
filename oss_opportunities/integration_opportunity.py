"""OpenSourceIntegrationOpportunityV1 -- a ranked leverage opportunity
derived from an already-scored `OpenSourceRepositoryCandidateV1` +
`RepositoryLicenseReviewV1` pair.

An opportunity always points back to both the candidate it was scored
from and the license review that gates its `recommended_action`
(`candidate_id`/`license_review_id`, mission validation rule 3) -- it
never carries its own independent license judgment.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from oss_opportunities.validation import (
    OssOpportunityValidationError,
    SCORING_VERSION,
    validate_integration_opportunity,
)

_SCHEMA_VERSION = "1"


def compute_opportunity_id(*, repo_full_name: str, candidate_id: str, scoring_version: str = SCORING_VERSION) -> str:
    """Stable sha256[:16], deliberately excluding any timestamp -- an
    opportunity is a reproducible output of a scoring run over an
    already-fixed candidate, not an independent execution attempt."""
    basis = {"repo_full_name": repo_full_name, "candidate_id": candidate_id, "scoring_version": scoring_version}
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class OpenSourceIntegrationOpportunityV1:
    schema_version: str = _SCHEMA_VERSION
    opportunity_id: str = ""
    repo_full_name: str = ""
    candidate_id: str = ""
    license_review_id: str = ""
    leverage_category: str = "reject_or_defer"
    recommended_action: str = "defer"
    blocked_actions: list[str] = field(default_factory=list)
    integration_surface: list[str] = field(default_factory=list)
    emulation_surface: list[str] = field(default_factory=list)
    relevance_to_neurotopology_sim: str = "none"
    relevance_to_awareness_studio: str = "none"
    relevance_to_report_packs: str = "none"
    relevance_to_literature_pipeline: str = "none"
    relevance_to_saas_future: str = "none"
    security_risk: str = "unknown"
    dependency_weight: str = "unknown"
    maintenance_signal: str = "unknown"
    implementation_complexity: str = "unknown"
    score_components: dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        repo_full_name: str,
        candidate_id: str,
        license_review_id: str,
        scoring_version: str = SCORING_VERSION,
        **kwargs: Any,
    ) -> "OpenSourceIntegrationOpportunityV1":
        opportunity_id = compute_opportunity_id(
            repo_full_name=repo_full_name, candidate_id=candidate_id, scoring_version=scoring_version,
        )
        return cls(
            opportunity_id=opportunity_id, repo_full_name=repo_full_name,
            candidate_id=candidate_id, license_review_id=license_review_id, **kwargs,
        )

    def recompute_id(self, *, scoring_version: str = SCORING_VERSION) -> str:
        return compute_opportunity_id(
            repo_full_name=self.repo_full_name, candidate_id=self.candidate_id, scoring_version=scoring_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "opportunity_id": self.opportunity_id,
            "repo_full_name": self.repo_full_name,
            "candidate_id": self.candidate_id,
            "license_review_id": self.license_review_id,
            "leverage_category": self.leverage_category,
            "recommended_action": self.recommended_action,
            "blocked_actions": list(self.blocked_actions),
            "integration_surface": list(self.integration_surface),
            "emulation_surface": list(self.emulation_surface),
            "relevance_to_neurotopology_sim": self.relevance_to_neurotopology_sim,
            "relevance_to_awareness_studio": self.relevance_to_awareness_studio,
            "relevance_to_report_packs": self.relevance_to_report_packs,
            "relevance_to_literature_pipeline": self.relevance_to_literature_pipeline,
            "relevance_to_saas_future": self.relevance_to_saas_future,
            "security_risk": self.security_risk,
            "dependency_weight": self.dependency_weight,
            "maintenance_signal": self.maintenance_signal,
            "implementation_complexity": self.implementation_complexity,
            "score_components": dict(self.score_components or {}),
            "total_score": self.total_score,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OpenSourceIntegrationOpportunityV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            opportunity_id=d.get("opportunity_id", ""),
            repo_full_name=d.get("repo_full_name", ""),
            candidate_id=d.get("candidate_id", ""),
            license_review_id=d.get("license_review_id", ""),
            leverage_category=d.get("leverage_category", "reject_or_defer"),
            recommended_action=d.get("recommended_action", "defer"),
            blocked_actions=list(d.get("blocked_actions") or []),
            integration_surface=list(d.get("integration_surface") or []),
            emulation_surface=list(d.get("emulation_surface") or []),
            relevance_to_neurotopology_sim=d.get("relevance_to_neurotopology_sim", "none"),
            relevance_to_awareness_studio=d.get("relevance_to_awareness_studio", "none"),
            relevance_to_report_packs=d.get("relevance_to_report_packs", "none"),
            relevance_to_literature_pipeline=d.get("relevance_to_literature_pipeline", "none"),
            relevance_to_saas_future=d.get("relevance_to_saas_future", "none"),
            security_risk=d.get("security_risk", "unknown"),
            dependency_weight=d.get("dependency_weight", "unknown"),
            maintenance_signal=d.get("maintenance_signal", "unknown"),
            implementation_complexity=d.get("implementation_complexity", "unknown"),
            score_components=dict(d.get("score_components") or {}),
            total_score=float(d.get("total_score", 0.0)),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "OpenSourceIntegrationOpportunityV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_integration_opportunity(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise OssOpportunityValidationError("; ".join(errors))
