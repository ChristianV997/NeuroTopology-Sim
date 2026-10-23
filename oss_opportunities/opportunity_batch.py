"""OpenSourceLeverageBatchV1 -- a ranked batch of
`OpenSourceIntegrationOpportunityV1` records produced from a list of
already-imported `OpenSourceRepositoryCandidateV1` scouting records.

`build_opportunities_from_candidates` never clones a repository, never
installs a dependency, and never executes any external code -- it only
reads already-in-memory `OpenSourceRepositoryCandidateV1` objects, derives
a `RepositoryLicenseReviewV1` for each (via `oss_opportunities.
license_review.classify_license_risk`, an offline string classification),
and scores them via `oss_opportunities.scoring.score_opportunity`.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from oss_opportunities.integration_opportunity import OpenSourceIntegrationOpportunityV1
from oss_opportunities.license_review import RepositoryLicenseReviewV1
from oss_opportunities.repository_candidate import OpenSourceRepositoryCandidateV1
from oss_opportunities.scoring import score_opportunity
from oss_opportunities.validation import (
    OssOpportunityValidationError,
    SCORING_VERSION,
    validate_leverage_batch,
    validate_opportunity_against_license_review,
)

_SCHEMA_VERSION = "1"

# A candidate whose opportunity total_score falls below this, or whose
# recommended_action is itself "reject", is kept out of
# opportunities_ranked and moved to opportunities_rejected -- never
# silently dropped.
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


def compute_batch_id(*, opportunity_ids: list[str], sources_scanned: list[str], scoring_version: str = SCORING_VERSION) -> str:
    basis = {
        "opportunity_ids": sorted(opportunity_ids),
        "sources_scanned": sorted(sources_scanned),
        "scoring_version": scoring_version,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class OpenSourceLeverageBatchV1:
    schema_version: str = _SCHEMA_VERSION
    batch_id: str = ""
    sources_scanned: list[str] = field(default_factory=list)
    candidates_seen: int = 0
    opportunities_ranked: list[dict[str, Any]] = field(default_factory=list)
    opportunities_rejected: list[dict[str, Any]] = field(default_factory=list)
    top_by_category: dict[str, list[str]] = field(default_factory=dict)
    top_immediate_adapters: list[str] = field(default_factory=list)
    top_architecture_emulation: list[str] = field(default_factory=list)
    top_docs_references: list[str] = field(default_factory=list)
    top_rejections: list[str] = field(default_factory=list)
    generated_at: str = ""
    repo_commit: str = ""
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "sources_scanned": list(self.sources_scanned),
            "candidates_seen": self.candidates_seen,
            "opportunities_ranked": list(self.opportunities_ranked),
            "opportunities_rejected": list(self.opportunities_rejected),
            "top_by_category": dict(self.top_by_category or {}),
            "top_immediate_adapters": list(self.top_immediate_adapters),
            "top_architecture_emulation": list(self.top_architecture_emulation),
            "top_docs_references": list(self.top_docs_references),
            "top_rejections": list(self.top_rejections),
            "generated_at": self.generated_at,
            "repo_commit": self.repo_commit,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OpenSourceLeverageBatchV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            batch_id=d.get("batch_id", ""),
            sources_scanned=list(d.get("sources_scanned") or []),
            candidates_seen=int(d.get("candidates_seen", 0)),
            opportunities_ranked=list(d.get("opportunities_ranked") or []),
            opportunities_rejected=list(d.get("opportunities_rejected") or []),
            top_by_category=dict(d.get("top_by_category") or {}),
            top_immediate_adapters=list(d.get("top_immediate_adapters") or []),
            top_architecture_emulation=list(d.get("top_architecture_emulation") or []),
            top_docs_references=list(d.get("top_docs_references") or []),
            top_rejections=list(d.get("top_rejections") or []),
            generated_at=d.get("generated_at", ""),
            repo_commit=d.get("repo_commit", ""),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "OpenSourceLeverageBatchV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_leverage_batch(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise OssOpportunityValidationError("; ".join(errors))


def build_opportunities_from_candidates(
    candidate_records: list[OpenSourceRepositoryCandidateV1],
    *,
    scoring_version: str = SCORING_VERSION,
    top_n: Optional[int] = None,
    _now: Optional[datetime] = None,
) -> OpenSourceLeverageBatchV1:
    """Score every candidate, rank deterministically, and build an
    `OpenSourceLeverageBatchV1`. Never clones a repository, never installs
    a dependency, and never executes external code -- operates only on
    already-constructed `OpenSourceRepositoryCandidateV1` objects."""
    if not candidate_records:
        raise OssOpportunityValidationError("candidate_records must be non-empty -- nothing to score")

    for index, c in enumerate(candidate_records):
        errs = c.validate()
        if errs:
            raise OssOpportunityValidationError(f"candidate at index {index} failed validation: {'; '.join(errs)}")

    # A duplicate repository with conflicting observed SPDX labels is not
    # resolved by choosing the higher-scoring observation. Normalize case
    # and surrounding whitespace only; do not attempt to parse SPDX
    # expressions or infer that different labels are equivalent.
    observations_by_repo: dict[str, list[OpenSourceRepositoryCandidateV1]] = {}
    for candidate in candidate_records:
        observations_by_repo.setdefault(candidate.repo_full_name.casefold(), []).append(candidate)
    license_conflicts: dict[str, tuple[list[str], list[str]]] = {}
    for repo_key, observations in observations_by_repo.items():
        normalized = {
            (candidate.license_spdx or "unknown").strip().casefold()
            for candidate in observations
        }
        if len(normalized) > 1:
            observed_values = sorted(
                {(candidate.license_spdx or "unknown").strip() or "unknown" for candidate in observations},
                key=str.casefold,
            )
            candidate_ids = sorted({candidate.candidate_id for candidate in observations})
            license_conflicts[repo_key] = (observed_values, candidate_ids)

    ts = (_now or datetime.now(timezone.utc)).isoformat()
    sources_scanned = sorted({c.source for c in candidate_records if c.source})

    scored: list[tuple[OpenSourceRepositoryCandidateV1, RepositoryLicenseReviewV1, OpenSourceIntegrationOpportunityV1]] = []
    for candidate in candidate_records:
        conflict = license_conflicts.get(candidate.repo_full_name.casefold())
        if conflict is None:
            scoring_candidate = candidate
            license_review = RepositoryLicenseReviewV1.make(
                repo_full_name=candidate.repo_full_name, license_spdx=candidate.license_spdx,
                license_name=candidate.license_name,
                provenance=f"classified from candidate_id={candidate.candidate_id} via oss_opportunities.license_review.classify_license_risk",
                limitations=["offline SPDX-string classification only; not legal review"],
            )
        else:
            observed_values, candidate_ids = conflict
            scoring_candidate = replace(
                candidate,
                license_spdx="unknown",
                license_name="conflicting license observations",
            )
            license_review = RepositoryLicenseReviewV1.make(
                repo_full_name=candidate.repo_full_name,
                license_spdx="unknown",
                license_name="conflicting license observations",
                provenance=(
                    "conflicting license labels observed across candidate_ids="
                    + ",".join(candidate_ids)
                    + "; routed to license review without resolving the source evidence"
                ),
                limitations=[
                    "conflicting observed license labels require review",
                    "offline license classification is not legal review",
                ],
                metadata={
                    "license_observation_status": "conflict",
                    "observed_license_spdx": observed_values,
                    "candidate_ids": candidate_ids,
                },
            )
        license_review.validate_or_raise()

        components = score_opportunity(scoring_candidate, license_review)
        opportunity = OpenSourceIntegrationOpportunityV1.make(
            repo_full_name=candidate.repo_full_name, candidate_id=candidate.candidate_id,
            license_review_id=license_review.license_review_id, scoring_version=scoring_version,
            provenance=f"scored from candidate_id={candidate.candidate_id} via oss_opportunities.scoring",
            limitations=[
                "leverage-ranking opportunity only; not a completed or attempted integration",
                "score reflects engineering-leverage heuristics only, not repository quality or correctness",
                "engineering-priority output does not establish scientific validity, security certification, legal approval, compatibility, or authorization to adopt",
            ],
            **components,
        )
        opportunity.validate_or_raise()
        cross_errs = validate_opportunity_against_license_review(opportunity, license_review)
        if cross_errs:
            raise OssOpportunityValidationError(f"opportunity/license-review mismatch: {'; '.join(cross_errs)}")

        scored.append((candidate, license_review, opportunity))

    scored.sort(key=lambda triple: (-triple[2].total_score, triple[0].repo_full_name, triple[2].opportunity_id))

    # Duplicate detection. The same repository (case-insensitive
    # repo_full_name) can arrive from several sources or snapshots. `scored` is
    # already sorted best-first, so the first observation per repository is the
    # primary opportunity. Every other observation is kept in
    # opportunities_rejected with a duplicate_of reason -- never ranked twice,
    # never silently dropped.
    primary_by_repo: dict[str, str] = {}
    unique_scored = []
    duplicate_observations = []
    for triple in scored:
        key = triple[0].repo_full_name.casefold()
        if key in primary_by_repo:
            duplicate_observations.append((triple[2], primary_by_repo[key]))
        else:
            primary_by_repo[key] = triple[2].opportunity_id
            unique_scored.append(triple)

    ranked: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for candidate, license_review, opportunity in unique_scored:
        entry = opportunity.to_dict()
        entry["license_review"] = license_review.to_dict()
        if opportunity.total_score >= _MIN_RANKED_SCORE and opportunity.recommended_action != "reject":
            ranked.append(entry)
        else:
            rejected.append(
                {
                    "opportunity_id": opportunity.opportunity_id,
                    "repo_full_name": opportunity.repo_full_name,
                    "total_score": opportunity.total_score,
                    "reason": (
                        "recommended_action='reject'"
                        if opportunity.recommended_action == "reject"
                        else f"total_score {opportunity.total_score} below minimum ranked threshold {_MIN_RANKED_SCORE}"
                    ),
                }
            )

    for duplicate, primary_id in duplicate_observations:
        rejected.append(
            {
                "opportunity_id": duplicate.opportunity_id,
                "repo_full_name": duplicate.repo_full_name,
                "total_score": duplicate.total_score,
                "reason": f"duplicate_of:{primary_id} (same repo_full_name observed from another source or snapshot)",
                "duplicate_of": primary_id,
            }
        )

    if top_n is not None:
        ranked = ranked[:top_n]

    top_by_category: dict[str, list[str]] = {}
    for entry in ranked:
        top_by_category.setdefault(entry["leverage_category"], []).append(entry["repo_full_name"])

    top_immediate_adapters = [
        e["repo_full_name"] for e in ranked
        if e["recommended_action"] in ("integrate_as_optional_adapter", "integrate_as_external_tool_record")
    ]
    top_architecture_emulation = [e["repo_full_name"] for e in ranked if e["recommended_action"] == "emulate_architecture_pattern"]
    top_docs_references = [e["repo_full_name"] for e in ranked if e["recommended_action"] == "create_docs_reference"]
    top_rejections = [e["repo_full_name"] for e in rejected if "duplicate_of" not in e]

    opportunity_ids = [e["opportunity_id"] for e in ranked]
    batch_id = compute_batch_id(opportunity_ids=opportunity_ids, sources_scanned=sources_scanned, scoring_version=scoring_version)

    batch = OpenSourceLeverageBatchV1(
        batch_id=batch_id,
        sources_scanned=sources_scanned,
        candidates_seen=len(candidate_records),
        opportunities_ranked=ranked,
        opportunities_rejected=rejected,
        top_by_category=top_by_category,
        top_immediate_adapters=top_immediate_adapters,
        top_architecture_emulation=top_architecture_emulation,
        top_docs_references=top_docs_references,
        top_rejections=top_rejections,
        generated_at=ts,
        repo_commit=_repo_commit(),
        limitations=[
            "this batch ranks open-source leverage opportunities; it does not perform any integration",
            "trending/star counts are a discovery-priority signal only, never proof of quality or license safety",
            "engineering-priority output does not establish scientific validity, security certification, legal approval, compatibility, or authorization to adopt",
            "no repository was cloned, no dependency was installed, no external code was executed",
        ],
        provenance=f"built from {len(candidate_records)} candidate(s) via oss_opportunities.opportunity_batch.build_opportunities_from_candidates",
        metadata={
            "duplicate_observations": len(duplicate_observations),
            **({"license_conflicts": len(license_conflicts)} if license_conflicts else {}),
        },
    )
    batch.validate_or_raise()
    return batch
