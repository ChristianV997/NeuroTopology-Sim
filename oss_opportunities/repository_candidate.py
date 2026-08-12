"""OpenSourceRepositoryCandidateV1 -- a scouting record for a public
open-source repository discovered via a Trendshift snapshot, a Star
History starmap snapshot, GitHub repository metadata, or a manual seed
list.

This carries no execution capability and no evidence/claim status --
purely observed metadata plus a pointer back to where it was observed
(`source`/`source_timeframe`/`source_snapshot_date`), mirroring
`dataset_importers.candidate_record.DatasetCandidateRecordV1`'s role for
dataset scouting. License classification is a *separate* object
(`RepositoryLicenseReviewV1`, see `oss_opportunities.license_review`) --
a candidate only records what license string was observed, never a risk
judgment.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from oss_opportunities.validation import (
    OssOpportunityValidationError,
    validate_repository_candidate,
)

_SCHEMA_VERSION = "1"


def compute_candidate_id(*, repo_full_name: str, source: str, source_timeframe: str, source_snapshot_date: str) -> str:
    """Stable sha256[:16] over (repo_full_name, source, source_timeframe,
    source_snapshot_date) -- deliberately excludes every mutable/free-text
    field (stars, description, ...) so re-scanning the same snapshot always
    yields the same candidate_id regardless of when scoring was last
    refreshed. A different snapshot date is a genuinely different
    observation and gets its own id -- this scout never claims a repo's
    metadata is unchanged across snapshots."""
    basis = {
        "repo_full_name": repo_full_name,
        "source": source,
        "source_timeframe": source_timeframe,
        "source_snapshot_date": source_snapshot_date,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class OpenSourceRepositoryCandidateV1:
    schema_version: str = _SCHEMA_VERSION
    candidate_id: str = ""
    repo_full_name: str = ""
    repo_url: str = ""
    source: str = ""
    source_timeframe: str = ""
    source_rank: Optional[int] = None
    source_snapshot_date: str = ""
    name: str = ""
    owner: str = ""
    description: str = ""
    topics: list[str] = field(default_factory=list)
    primary_language: str = ""
    stars: Optional[int] = None
    star_gain: Optional[int] = None
    fork_count: Optional[int] = None
    license_spdx: str = "unknown"
    license_name: str = "unknown"
    license_url: str = ""
    latest_activity_status: str = "unknown"
    package_ecosystem: str = ""
    homepage_url: str = ""
    observed_categories: list[str] = field(default_factory=list)
    provenance: str = ""
    limitations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        repo_full_name: str,
        source: str,
        source_timeframe: str = "",
        source_snapshot_date: str = "",
        **kwargs: Any,
    ) -> "OpenSourceRepositoryCandidateV1":
        candidate_id = compute_candidate_id(
            repo_full_name=repo_full_name, source=source,
            source_timeframe=source_timeframe, source_snapshot_date=source_snapshot_date,
        )
        return cls(
            candidate_id=candidate_id, repo_full_name=repo_full_name, source=source,
            source_timeframe=source_timeframe, source_snapshot_date=source_snapshot_date, **kwargs,
        )

    def recompute_id(self) -> str:
        return compute_candidate_id(
            repo_full_name=self.repo_full_name, source=self.source,
            source_timeframe=self.source_timeframe, source_snapshot_date=self.source_snapshot_date,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "repo_full_name": self.repo_full_name,
            "repo_url": self.repo_url,
            "source": self.source,
            "source_timeframe": self.source_timeframe,
            "source_rank": self.source_rank,
            "source_snapshot_date": self.source_snapshot_date,
            "name": self.name,
            "owner": self.owner,
            "description": self.description,
            "topics": list(self.topics),
            "primary_language": self.primary_language,
            "stars": self.stars,
            "star_gain": self.star_gain,
            "fork_count": self.fork_count,
            "license_spdx": self.license_spdx,
            "license_name": self.license_name,
            "license_url": self.license_url,
            "latest_activity_status": self.latest_activity_status,
            "package_ecosystem": self.package_ecosystem,
            "homepage_url": self.homepage_url,
            "observed_categories": list(self.observed_categories),
            "provenance": self.provenance,
            "limitations": list(self.limitations),
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OpenSourceRepositoryCandidateV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            candidate_id=d.get("candidate_id", ""),
            repo_full_name=d.get("repo_full_name", ""),
            repo_url=d.get("repo_url", ""),
            source=d.get("source", ""),
            source_timeframe=d.get("source_timeframe", ""),
            source_rank=d.get("source_rank"),
            source_snapshot_date=d.get("source_snapshot_date", ""),
            name=d.get("name", ""),
            owner=d.get("owner", ""),
            description=d.get("description", ""),
            topics=list(d.get("topics") or []),
            primary_language=d.get("primary_language", ""),
            stars=d.get("stars"),
            star_gain=d.get("star_gain"),
            fork_count=d.get("fork_count"),
            license_spdx=d.get("license_spdx", "unknown"),
            license_name=d.get("license_name", "unknown"),
            license_url=d.get("license_url", ""),
            latest_activity_status=d.get("latest_activity_status", "unknown"),
            package_ecosystem=d.get("package_ecosystem", ""),
            homepage_url=d.get("homepage_url", ""),
            observed_categories=list(d.get("observed_categories") or []),
            provenance=d.get("provenance", ""),
            limitations=list(d.get("limitations") or []),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "OpenSourceRepositoryCandidateV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_repository_candidate(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise OssOpportunityValidationError("; ".join(errors))
