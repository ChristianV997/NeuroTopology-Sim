"""Data structures, schemas, and outcome classifications for simulation campaign runtime.
"""
from __future__ import annotations

import os
import platform
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence


class Outcome(str, Enum):
    """Mutually exclusive terminal outcomes for a work unit.

    Guarantees that every completed or attempted unit has an unambiguous,
    categorized outcome rather than a generic pass/fail boolean.
    """
    PASS = "PASS"
    CORRECTNESS_FAILURE = "CORRECTNESS_FAILURE"
    TIMEOUT = "TIMEOUT"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    DISK_FAILURE = "DISK_FAILURE"
    MEMORY_FAILURE = "MEMORY_FAILURE"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"
    NOT_RUN = "NOT_RUN"


def is_retryable_outcome(outcome: Outcome) -> bool:
    """Classify whether a failure outcome is an infrastructure failure eligible for retry.

    Correctness failures, missing dependencies, and un-run units must never be retried.
    """
    return outcome in {
        Outcome.NETWORK_FAILURE,
        Outcome.DISK_FAILURE,
        Outcome.MEMORY_FAILURE,
    }


@dataclass
class ResourcePolicy:
    """Resource constraints and concurrency controls for campaign execution."""
    max_workers: int = 1
    concurrency_cap: int = 8
    min_disk_free_mb: float = 500.0
    max_memory_mb: float = 4096.0
    max_retries_per_unit: int = 2
    default_timeout_s: float = 60.0

    def effective_workers(self) -> int:
        """Return worker count clamped by concurrency cap and physical CPU limit."""
        cpu_count = os.cpu_count() or 1
        return max(1, min(self.max_workers, self.concurrency_cap, cpu_count))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ResourcePolicy:
        return cls(
            max_workers=int(data.get("max_workers", 1)),
            concurrency_cap=int(data.get("concurrency_cap", 8)),
            min_disk_free_mb=float(data.get("min_disk_free_mb", 500.0)),
            max_memory_mb=float(data.get("max_memory_mb", 4096.0)),
            max_retries_per_unit=int(data.get("max_retries_per_unit", 2)),
            default_timeout_s=float(data.get("default_timeout_s", 60.0)),
        )


@dataclass
class WorkUnit:
    """Specification of an independent unit of work within a simulation campaign."""
    unit_id: str
    command: List[str]
    subject_id: Optional[str] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    window_id: Optional[str] = None
    parameter_case: Dict[str, Any] = field(default_factory=dict)
    expected_outputs: List[str] = field(default_factory=list)
    timeout_s: float = 60.0
    dependencies: List[str] = field(default_factory=list)
    estimated_disk_mb: float = 10.0
    estimated_memory_mb: float = 128.0
    retryable: bool = True
    max_retries: int = 2

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkUnit:
        return cls(
            unit_id=str(data["unit_id"]),
            command=[str(c) for c in data.get("command", [])],
            subject_id=data.get("subject_id"),
            session_id=data.get("session_id"),
            run_id=data.get("run_id"),
            window_id=data.get("window_id"),
            parameter_case=dict(data.get("parameter_case", {})),
            expected_outputs=[str(p) for p in data.get("expected_outputs", [])],
            timeout_s=float(data.get("timeout_s", 60.0)),
            dependencies=[str(d) for d in data.get("dependencies", [])],
            estimated_disk_mb=float(data.get("estimated_disk_mb", 10.0)),
            estimated_memory_mb=float(data.get("estimated_memory_mb", 128.0)),
            retryable=bool(data.get("retryable", True)),
            max_retries=int(data.get("max_retries", 2)),
        )


@dataclass
class UnitResult:
    """Execution result for a single work unit."""
    unit_id: str
    outcome: Outcome
    status: str
    exit_code: Optional[int]
    elapsed_s: float
    retry_count: int
    stdout: str
    stderr: str
    error_message: Optional[str]
    peak_memory_bytes: Optional[int]
    output_checksums: Dict[str, str]
    metrics: Optional[Dict[str, Any]]
    started_at: str
    completed_at: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UnitResult:
        return cls(
            unit_id=str(data["unit_id"]),
            outcome=Outcome(data["outcome"]),
            status=str(data.get("status", "COMPLETED")),
            exit_code=data.get("exit_code"),
            elapsed_s=float(data.get("elapsed_s", 0.0)),
            retry_count=int(data.get("retry_count", 0)),
            stdout=str(data.get("stdout", "")),
            stderr=str(data.get("stderr", "")),
            error_message=data.get("error_message"),
            peak_memory_bytes=data.get("peak_memory_bytes"),
            output_checksums=dict(data.get("output_checksums", {})),
            metrics=data.get("metrics"),
            started_at=str(data.get("started_at", "")),
            completed_at=str(data.get("completed_at", "")),
        )


@dataclass
class CampaignManifest:
    """Input manifest defining the entire campaign workload."""
    schema_version: str
    campaign_id: str
    created_at: str
    code_commit: str
    configuration_hash: str
    seed: int
    units: List[WorkUnit]
    environment: Dict[str, Any]
    resource_policy: ResourcePolicy

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "created_at": self.created_at,
            "code_commit": self.code_commit,
            "configuration_hash": self.configuration_hash,
            "seed": self.seed,
            "units": [u.to_dict() for u in self.units],
            "environment": self.environment,
            "resource_policy": self.resource_policy.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CampaignManifest:
        units = [WorkUnit.from_dict(u) for u in data.get("units", [])]
        policy = ResourcePolicy.from_dict(data.get("resource_policy", {}))
        return cls(
            schema_version=str(data.get("schema_version", "simulation_campaign_manifest_v1")),
            campaign_id=str(data["campaign_id"]),
            created_at=str(data.get("created_at", "")),
            code_commit=str(data.get("code_commit", "unknown")),
            configuration_hash=str(data.get("configuration_hash", "")),
            seed=int(data.get("seed", 0)),
            units=units,
            environment=dict(data.get("environment", {})),
            resource_policy=policy,
        )


@dataclass
class CampaignState:
    """Checkpointable state of an executing or completed campaign."""
    schema_version: str
    campaign_id: str
    manifest_hash: str
    completed_units: Dict[str, UnitResult]
    active_unit: Optional[str]
    is_complete: bool
    is_partial: bool
    cancelled: bool
    summary: Dict[str, int]
    last_checkpoint_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "manifest_hash": self.manifest_hash,
            "completed_units": {k: v.to_dict() for k, v in self.completed_units.items()},
            "active_unit": self.active_unit,
            "is_complete": self.is_complete,
            "is_partial": self.is_partial,
            "cancelled": self.cancelled,
            "summary": dict(self.summary),
            "last_checkpoint_at": self.last_checkpoint_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CampaignState:
        completed = {
            k: UnitResult.from_dict(v)
            for k, v in data.get("completed_units", {}).items()
        }
        return cls(
            schema_version=str(data.get("schema_version", "simulation_campaign_state_v1")),
            campaign_id=str(data["campaign_id"]),
            manifest_hash=str(data.get("manifest_hash", "")),
            completed_units=completed,
            active_unit=data.get("active_unit"),
            is_complete=bool(data.get("is_complete", False)),
            is_partial=bool(data.get("is_partial", True)),
            cancelled=bool(data.get("cancelled", False)),
            summary=dict(data.get("summary", {})),
            last_checkpoint_at=str(data.get("last_checkpoint_at", "")),
        )


def capture_environment_metadata() -> Dict[str, Any]:
    """Capture host and runtime environment details for campaign provenance."""
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "os": os.name,
        "hostname": platform.node(),
    }
