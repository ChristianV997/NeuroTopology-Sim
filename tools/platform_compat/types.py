"""Type definitions, enums, dataclasses, and structured states for platform compatibility.

Guarantees:
- Structured capability states: available, unavailable, unsupported, permission_denied, failed.
- Typed process results with child termination telemetry.
- Null-safe serialization without NaN or Infinity.
- Deterministic checksum computation.
"""
from __future__ import annotations

import enum
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence


class CapabilityStatus(str, enum.Enum):
    """Structured platform capability states."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    PERMISSION_DENIED = "permission_denied"
    FAILED = "failed"


class DependencyStatus(str, enum.Enum):
    """Structured optional dependency status states."""
    AVAILABLE = "available"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    IMPORT_ERROR = "import_error"


def sanitize_val_for_json(val: Any) -> Any:
    """Recursively sanitize values to ensure strict JSON compatibility without NaN/Inf."""
    if val is None:
        return None
    if isinstance(val, (bool, int, str)):
        return val
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if isinstance(val, enum.Enum):
        return val.value
    if isinstance(val, dict):
        return {str(k): sanitize_val_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [sanitize_val_for_json(item) for item in val]
    if hasattr(val, "to_dict") and callable(val.to_dict):
        return sanitize_val_for_json(val.to_dict())
    return str(val)


@dataclass(frozen=True)
class CapabilityResult:
    """Structured result of probing a specific platform capability."""
    name: str
    status: CapabilityStatus
    details: str = ""
    error_type: Optional[str] = None
    platform_specific: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "details": self.details,
            "error_type": self.error_type,
            "platform_specific": self.platform_specific,
            "metadata": sanitize_val_for_json(self.metadata),
        }


@dataclass(frozen=True)
class DependencyClassification:
    """Structured assessment of an optional library dependency."""
    name: str
    status: DependencyStatus
    version: Optional[str] = None
    import_path: Optional[str] = None
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "version": self.version,
            "import_path": self.import_path,
            "details": self.details,
        }


@dataclass(frozen=True)
class ProcessResult:
    """Result of running a guarded subprocess."""
    command: list[str]
    returncode: Optional[int]
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    terminated_children: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": sanitize_val_for_json(self.duration_seconds),
            "timed_out": self.timed_out,
            "terminated_children": self.terminated_children,
        }


@dataclass(frozen=True)
class PlatformTestDecision:
    """Actionable decision for running or handling a capability-dependent test."""
    can_run: bool
    status: CapabilityStatus
    reason: str
    mitigation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_run": self.can_run,
            "status": self.status.value,
            "reason": self.reason,
            "mitigation": self.mitigation,
        }


def compute_audit_checksum(
    os_name: str,
    python_version: str,
    capabilities: dict[str, CapabilityResult],
    dependencies: dict[str, DependencyClassification],
) -> str:
    """Compute deterministic SHA-256 over platform capabilities and dependencies."""
    sorted_caps = sorted((k, v.status.value) for k, v in capabilities.items())
    sorted_deps = sorted((k, v.status.value) for k, v in dependencies.items())
    payload = f"os={os_name}|py={python_version}|caps={sorted_caps}|deps={sorted_deps}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class PlatformAuditReport:
    """Comprehensive, deterministic platform capability report."""
    timestamp: str
    platform: str
    os_name: str
    os_release: str
    python_version: str
    is_windows: bool
    is_posix: bool
    capabilities: dict[str, CapabilityResult]
    dependencies: dict[str, DependencyClassification]
    deterministic_checksum: str = ""

    def __post_init__(self) -> None:
        if not self.deterministic_checksum:
            self.deterministic_checksum = compute_audit_checksum(
                self.os_name, self.python_version, self.capabilities, self.dependencies
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "platform": self.platform,
            "os_name": self.os_name,
            "os_release": self.os_release,
            "python_version": self.python_version,
            "is_windows": self.is_windows,
            "is_posix": self.is_posix,
            "deterministic_checksum": self.deterministic_checksum,
            "capabilities": {k: v.to_dict() for k, v in self.capabilities.items()},
            "dependencies": {k: v.to_dict() for k, v in self.dependencies.items()},
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, allow_nan=False)
