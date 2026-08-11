"""DatasetAcquisitionPlanV1 -- a dry-run-first, disk-bounded plan for
acquiring a selected `dataset_importers.candidate_record.DatasetCandidateRecordV1`
into a local, gitignored workspace.

A plan is not a download. `dry_run=False` on a plan only records that the
plan was *authored* with every safety flag explicitly present and nothing
blocked -- actually touching the filesystem/network is
`dataset_acquisition.executor.execute_acquisition_plan`'s job, and it
requires its own separate `execute=True`. See
docs/dataset_acquisition_planner.md.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from dataset_acquisition.validation import validate_plan

_SCHEMA_VERSION = "1"


def compute_plan_id(
    *,
    candidate_id: str,
    requested_action: str,
    acquisition_mode: str,
    target_root: str,
    disk_limit_bytes: Optional[int],
) -> str:
    """Stable sha256[:16] over the plan's identity fields only. `created_at`
    (and everything else -- risks, limitations, provenance, blocked_reasons,
    ...) is deliberately excluded, mirroring
    `dataset_importers.candidate_record.compute_candidate_id`: replanning
    the same request always yields the same plan_id."""
    basis = {
        "candidate_id": candidate_id,
        "requested_action": requested_action,
        "acquisition_mode": acquisition_mode,
        "target_root": target_root,
        "disk_limit_bytes": disk_limit_bytes,
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class DatasetAcquisitionPlanV1:
    schema_version: str = _SCHEMA_VERSION
    plan_id: str = ""
    candidate_id: str = ""
    source_catalog: str = ""
    source_dataset_id: str = ""
    display_name: str = ""
    requested_action: str = "metadata_only"
    acquisition_mode: str = "fixture_only"
    source_url: str = ""
    source_repository: str = ""
    license: str = "unknown"
    license_risk: str = "unknown_high"
    access_status: str = "unknown"
    estimated_size_bytes: Optional[int] = None
    disk_limit_bytes: Optional[int] = None
    expected_file_count: Optional[int] = None
    target_root: str = ""
    cache_policy: str = "no_cache_by_default"
    checksum_policy: str = "sha256_if_available"
    allow_network: bool = False
    allow_raw_data: bool = False
    dry_run: bool = True
    execution_required_flags: list[str] = field(default_factory=list)
    planned_steps: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        *,
        candidate_id: str,
        requested_action: str = "metadata_only",
        acquisition_mode: str = "fixture_only",
        target_root: str = "",
        disk_limit_bytes: Optional[int] = None,
        _now: Optional[datetime] = None,
        **kwargs: Any,
    ) -> "DatasetAcquisitionPlanV1":
        plan_id = compute_plan_id(
            candidate_id=candidate_id,
            requested_action=requested_action,
            acquisition_mode=acquisition_mode,
            target_root=target_root,
            disk_limit_bytes=disk_limit_bytes,
        )
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            plan_id=plan_id,
            candidate_id=candidate_id,
            requested_action=requested_action,
            acquisition_mode=acquisition_mode,
            target_root=target_root,
            disk_limit_bytes=disk_limit_bytes,
            created_at=ts,
            **kwargs,
        )

    def recompute_id(self) -> str:
        return compute_plan_id(
            candidate_id=self.candidate_id,
            requested_action=self.requested_action,
            acquisition_mode=self.acquisition_mode,
            target_root=self.target_root,
            disk_limit_bytes=self.disk_limit_bytes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "candidate_id": self.candidate_id,
            "source_catalog": self.source_catalog,
            "source_dataset_id": self.source_dataset_id,
            "display_name": self.display_name,
            "requested_action": self.requested_action,
            "acquisition_mode": self.acquisition_mode,
            "source_url": self.source_url,
            "source_repository": self.source_repository,
            "license": self.license,
            "license_risk": self.license_risk,
            "access_status": self.access_status,
            "estimated_size_bytes": self.estimated_size_bytes,
            "disk_limit_bytes": self.disk_limit_bytes,
            "expected_file_count": self.expected_file_count,
            "target_root": self.target_root,
            "cache_policy": self.cache_policy,
            "checksum_policy": self.checksum_policy,
            "allow_network": bool(self.allow_network),
            "allow_raw_data": bool(self.allow_raw_data),
            "dry_run": bool(self.dry_run),
            "execution_required_flags": list(self.execution_required_flags),
            "planned_steps": list(self.planned_steps),
            "blocked_reasons": list(self.blocked_reasons),
            "risks": list(self.risks),
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "created_at": self.created_at,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DatasetAcquisitionPlanV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            plan_id=d.get("plan_id", ""),
            candidate_id=d.get("candidate_id", ""),
            source_catalog=d.get("source_catalog", ""),
            source_dataset_id=d.get("source_dataset_id", ""),
            display_name=d.get("display_name", ""),
            requested_action=d.get("requested_action", "metadata_only"),
            acquisition_mode=d.get("acquisition_mode", "fixture_only"),
            source_url=d.get("source_url", ""),
            source_repository=d.get("source_repository", ""),
            license=d.get("license", "unknown"),
            license_risk=d.get("license_risk", "unknown_high"),
            access_status=d.get("access_status", "unknown"),
            estimated_size_bytes=d.get("estimated_size_bytes"),
            disk_limit_bytes=d.get("disk_limit_bytes"),
            expected_file_count=d.get("expected_file_count"),
            target_root=d.get("target_root", ""),
            cache_policy=d.get("cache_policy", "no_cache_by_default"),
            checksum_policy=d.get("checksum_policy", "sha256_if_available"),
            allow_network=bool(d.get("allow_network", False)),
            allow_raw_data=bool(d.get("allow_raw_data", False)),
            dry_run=bool(d.get("dry_run", True)),
            execution_required_flags=list(d.get("execution_required_flags") or []),
            planned_steps=list(d.get("planned_steps") or []),
            blocked_reasons=list(d.get("blocked_reasons") or []),
            risks=list(d.get("risks") or []),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            created_at=d.get("created_at", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "DatasetAcquisitionPlanV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_plan(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            from dataset_acquisition.validation import DatasetAcquisitionValidationError

            raise DatasetAcquisitionValidationError("; ".join(errors))
