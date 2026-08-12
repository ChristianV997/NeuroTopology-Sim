"""RepositoryLicenseReviewV1 -- a license-risk classification for a
candidate repository, kept as a separate object from
`OpenSourceRepositoryCandidateV1` so a license judgment is always
explicit, auditable, and re-derivable from a fixed policy version rather
than folded silently into a candidate's own fields.

This module does not check licenses over the network -- it classifies an
already-observed `license_spdx` string (from a candidate, a fixture, or a
manual seed entry) against a fixed, documented risk ladder
(`classify_license_risk`). It never claims to have performed real legal
review; `review_status` defaults to `"heuristic_unreviewed"` and only a
human-set `"human_reviewed"` value means an actual person looked at it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from oss_opportunities.validation import (
    LICENSE_POLICY_VERSION,
    OssOpportunityValidationError,
    validate_license_review,
)

_SCHEMA_VERSION = "1"

# Fixed classification ladder, additive to (not a replacement for)
# `external_tools.validation.ALLOWED_LICENSE_RISK`'s own permissive/
# copyleft/agpl/proprietary/unknown split -- this ladder adds the
# fair-code/source-available tier this milestone's manual seed list
# (n8n, Dify) specifically needs. Keys are matched case-insensitively
# against a normalized SPDX-ish string; anything unmatched is high risk
# by default (fail closed), never assumed permissive.
_PERMISSIVE_SPDX: frozenset[str] = frozenset(
    {"mit", "apache-2.0", "apache2", "bsd-2-clause", "bsd-3-clause", "isc", "0bsd", "unlicense", "cc0-1.0"}
)
_WEAK_COPYLEFT_SPDX: frozenset[str] = frozenset({"lgpl-2.1", "lgpl-3.0", "mpl-2.0", "epl-2.0", "epl-1.0"})
_STRONG_COPYLEFT_SPDX: frozenset[str] = frozenset({"gpl-2.0", "gpl-3.0", "agpl-3.0", "agpl-1.0"})
# Not real SPDX identifiers (fair-code/source-available licenses generally
# aren't OSI-approved), but repositories in this milestone's manual seed
# list (n8n Sustainable Use License, temporal's BSL-adjacent history, etc.)
# self-describe this way -- matched as free-text tokens, not SPDX codes.
_FAIR_CODE_MARKERS: frozenset[str] = frozenset(
    {"bsl-1.1", "bsl", "sspl-1.0", "sspl", "elastic-2.0", "elv2", "fair-code", "sustainable-use", "source-available"}
)


def classify_license_risk(license_spdx: str) -> str:
    """Deterministic, offline classification -- never a network license
    check. Returns one of `ALLOWED_LICENSE_RISK`. Unmatched/empty input is
    `missing_high` (fail closed, never assumed safe)."""
    if not license_spdx or not str(license_spdx).strip():
        return "missing_high"
    normalized = str(license_spdx).strip().lower()
    if normalized in ("unknown", "none", "no-license", "no license", "noassertion"):
        return "missing_high"
    if normalized in _PERMISSIVE_SPDX:
        return "permissive_low"
    if normalized in _WEAK_COPYLEFT_SPDX:
        return "weak_copyleft_medium"
    if normalized in _STRONG_COPYLEFT_SPDX:
        return "strong_copyleft_high"
    if normalized in _FAIR_CODE_MARKERS:
        return "source_available_or_fair_code_high"
    return "proprietary_or_unknown_high"


# Deterministic default policy for each risk tier -- a starting point a
# caller may override, never a promise that no human review is warranted.
_DEFAULT_POLICY_BY_RISK: dict[str, dict[str, Any]] = {
    "permissive_low": {
        "commercial_core_policy": "allowed_with_attribution",
        "allowed_use_modes": ["adapter_only", "docs_reference", "attributed_snippet_copy"],
        "blocked_use_modes": ["unattributed_copy"],
        "attribution_required": True,
    },
    "weak_copyleft_medium": {
        "commercial_core_policy": "adapter_only",
        "allowed_use_modes": ["adapter_only", "docs_reference", "external_process_only"],
        "blocked_use_modes": ["commercial_core_copy", "unattributed_copy"],
        "attribution_required": True,
    },
    "strong_copyleft_high": {
        "commercial_core_policy": "external_process_only",
        "allowed_use_modes": ["external_process_only", "docs_reference"],
        "blocked_use_modes": ["commercial_core_copy", "code_copy_of_any_kind"],
        "attribution_required": True,
    },
    "source_available_or_fair_code_high": {
        "commercial_core_policy": "docs_reference_only",
        "allowed_use_modes": ["docs_reference", "external_process_only_if_terms_permit"],
        "blocked_use_modes": ["commercial_core_copy", "code_copy_of_any_kind", "resale_without_review"],
        "attribution_required": True,
    },
    "proprietary_or_unknown_high": {
        "commercial_core_policy": "blocked_pending_review",
        "allowed_use_modes": ["docs_reference"],
        "blocked_use_modes": ["commercial_core_copy", "code_copy_of_any_kind", "adapter_without_review"],
        "attribution_required": True,
    },
    "missing_high": {
        "commercial_core_policy": "blocked_pending_review",
        "allowed_use_modes": ["docs_reference"],
        "blocked_use_modes": ["commercial_core_copy", "code_copy_of_any_kind", "adapter_without_review"],
        "attribution_required": True,
    },
}


def compute_license_review_id(*, repo_full_name: str, license_spdx: str, license_policy_version: str = LICENSE_POLICY_VERSION) -> str:
    basis = {"repo_full_name": repo_full_name, "license_spdx": license_spdx, "license_policy_version": license_policy_version}
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class RepositoryLicenseReviewV1:
    schema_version: str = _SCHEMA_VERSION
    license_review_id: str = ""
    repo_full_name: str = ""
    license_spdx: str = "unknown"
    license_name: str = "unknown"
    license_risk: str = "missing_high"
    commercial_core_policy: str = "blocked_pending_review"
    allowed_use_modes: list[str] = field(default_factory=list)
    blocked_use_modes: list[str] = field(default_factory=list)
    attribution_required: bool = True
    review_status: str = "heuristic_unreviewed"
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        repo_full_name: str,
        license_spdx: str = "unknown",
        license_name: str = "unknown",
        license_policy_version: str = LICENSE_POLICY_VERSION,
        **kwargs: Any,
    ) -> "RepositoryLicenseReviewV1":
        license_review_id = compute_license_review_id(
            repo_full_name=repo_full_name, license_spdx=license_spdx, license_policy_version=license_policy_version,
        )
        license_risk = classify_license_risk(license_spdx)
        defaults = dict(_DEFAULT_POLICY_BY_RISK[license_risk])
        defaults.update(kwargs)
        return cls(
            license_review_id=license_review_id, repo_full_name=repo_full_name,
            license_spdx=license_spdx, license_name=license_name, license_risk=license_risk, **defaults,
        )

    def recompute_id(self, *, license_policy_version: str = LICENSE_POLICY_VERSION) -> str:
        return compute_license_review_id(
            repo_full_name=self.repo_full_name, license_spdx=self.license_spdx, license_policy_version=license_policy_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "license_review_id": self.license_review_id,
            "repo_full_name": self.repo_full_name,
            "license_spdx": self.license_spdx,
            "license_name": self.license_name,
            "license_risk": self.license_risk,
            "commercial_core_policy": self.commercial_core_policy,
            "allowed_use_modes": list(self.allowed_use_modes),
            "blocked_use_modes": list(self.blocked_use_modes),
            "attribution_required": bool(self.attribution_required),
            "review_status": self.review_status,
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RepositoryLicenseReviewV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            license_review_id=d.get("license_review_id", ""),
            repo_full_name=d.get("repo_full_name", ""),
            license_spdx=d.get("license_spdx", "unknown"),
            license_name=d.get("license_name", "unknown"),
            license_risk=d.get("license_risk", "missing_high"),
            commercial_core_policy=d.get("commercial_core_policy", "blocked_pending_review"),
            allowed_use_modes=list(d.get("allowed_use_modes") or []),
            blocked_use_modes=list(d.get("blocked_use_modes") or []),
            attribution_required=bool(d.get("attribution_required", True)),
            review_status=d.get("review_status", "heuristic_unreviewed"),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "RepositoryLicenseReviewV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_license_review(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise OssOpportunityValidationError("; ".join(errors))
