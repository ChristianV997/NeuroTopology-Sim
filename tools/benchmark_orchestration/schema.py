"""Schema types for benchmark matrix orchestration."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


MATRIX_SCHEMA_VERSION = "1.0"


class CaseStatus(str, Enum):
    """Terminal / pending outcomes for one matrix case.

    Timeouts are never remapped to PASS. Missing optional deps and
    infrastructure blocks are distinct from correctness failures.
    """

    PASS = "PASS"
    CORRECTNESS_FAILURE = "CORRECTNESS_FAILURE"
    TIMEOUT = "TIMEOUT"
    CHILD_CRASH = "CHILD_CRASH"
    INFRASTRUCTURE_BLOCKED = "INFRASTRUCTURE_BLOCKED"
    OPTIONAL_DEPENDENCY_MISSING = "OPTIONAL_DEPENDENCY_MISSING"
    NOT_RUN = "NOT_RUN"


# Statuses that count as "completed" for resume (will not be re-executed).
TERMINAL_STATUSES = frozenset(
    {
        CaseStatus.PASS,
        CaseStatus.CORRECTNESS_FAILURE,
        CaseStatus.TIMEOUT,
        CaseStatus.CHILD_CRASH,
        CaseStatus.INFRASTRUCTURE_BLOCKED,
        CaseStatus.OPTIONAL_DEPENDENCY_MISSING,
    }
)


@dataclass(frozen=True)
class CaseSpec:
    """One declarative benchmark / test case."""

    case_id: str
    command: List[str]
    timeout_s: int
    max_retries: int = 0
    optional_deps: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    memory_telemetry_ref: Optional[str] = None
    cwd: Optional[str] = None
    local_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "command": list(self.command),
            "timeout_s": int(self.timeout_s),
            "max_retries": int(self.max_retries),
            "optional_deps": list(self.optional_deps),
            "config": dict(self.config),
            "tags": list(self.tags),
            "memory_telemetry_ref": self.memory_telemetry_ref,
            "cwd": self.cwd,
            "local_only": bool(self.local_only),
        }


@dataclass(frozen=True)
class MatrixSpec:
    """Validated benchmark matrix."""

    schema_version: str
    cases: List[CaseSpec]
    defaults: Dict[str, Any] = field(default_factory=dict)
    provenance_label: str = "benchmark-orchestration"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provenance_label": self.provenance_label,
            "defaults": dict(self.defaults),
            "cases": [c.to_dict() for c in self.cases],
        }


@dataclass(frozen=True)
class CampaignConfig:
    """Runtime limits for one campaign."""

    per_case_timeout_s: Optional[int] = None  # override all cases when set
    total_timeout_s: Optional[int] = None
    max_workers: int = 1
    max_retries: Optional[int] = None  # override case default when set
    dry_run: bool = False
    resume: bool = False
    local_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "per_case_timeout_s": self.per_case_timeout_s,
            "total_timeout_s": self.total_timeout_s,
            "max_workers": int(self.max_workers),
            "max_retries": self.max_retries,
            "dry_run": bool(self.dry_run),
            "resume": bool(self.resume),
            "local_only": bool(self.local_only),
        }


@dataclass
class CaseResult:
    """Captured outcome for one case attempt (final attempt recorded)."""

    case_id: str
    command: List[str]
    input_configuration: Dict[str, Any]
    status: CaseStatus
    duration_s: float
    exit_code: Optional[int]
    timed_out: bool
    stdout_ref: Optional[str]
    stderr_ref: Optional[str]
    checksum: Optional[str]
    memory_telemetry_ref: Optional[str]
    attempts: int
    retries_used: int
    error_message: Optional[str] = None
    dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "command": list(self.command),
            "input_configuration": dict(self.input_configuration),
            "status": self.status.value if isinstance(self.status, CaseStatus) else str(self.status),
            "duration_s": float(self.duration_s),
            "exit_code": self.exit_code,
            "timed_out": bool(self.timed_out),
            "stdout_ref": self.stdout_ref,
            "stderr_ref": self.stderr_ref,
            "checksum": self.checksum,
            "memory_telemetry_ref": self.memory_telemetry_ref,
            "attempts": int(self.attempts),
            "retries_used": int(self.retries_used),
            "error_message": self.error_message,
            "dry_run": bool(self.dry_run),
        }


@dataclass
class CampaignReport:
    """Deterministic campaign summary."""

    schema_version: str
    matrix_schema_version: str
    provenance_label: str
    campaign: Dict[str, Any]
    results: List[CaseResult]
    summary: Dict[str, Any]
    ordering: List[str]
    resumed_from: Optional[str] = None
    dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "matrix_schema_version": self.matrix_schema_version,
            "provenance_label": self.provenance_label,
            "campaign": dict(self.campaign),
            "ordering": list(self.ordering),
            "resumed_from": self.resumed_from,
            "dry_run": bool(self.dry_run),
            "summary": dict(self.summary),
            "results": [r.to_dict() for r in self.results],
        }
