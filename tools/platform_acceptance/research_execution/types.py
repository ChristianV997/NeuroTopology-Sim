"""Type definitions, enums, and structured models for platform acceptance testing.
"""
from __future__ import annotations

import enum
import hashlib
import json
import math
import os
import platform
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PathLike = Union[str, Path]


class AcceptanceCategory(str, enum.Enum):
    """Functional categories for cross-platform acceptance testing."""
    DATA_ACCESS = "data_access"
    CACHE_EVICTION = "cache_eviction"
    PROCESS_EXECUTION = "process_execution"
    OUTPUT_CONTAINMENT = "output_containment"
    ARTIFACT_INTEGRITY = "artifact_integrity"
    POWERSHELL_OPERATIONS = "powershell_operations"
    WINDOWS_SPECIFICS = "windows_specifics"


class TestStatus(str, enum.Enum):
    """Explicit outcome status for acceptance test cases."""
    __test__ = False

    PASS = "PASS"
    FAIL = "FAIL"
    UNSUPPORTED = "UNSUPPORTED"
    SKIPPED = "SKIPPED"


def json_safe(value: Any) -> Any:
    """Recursively convert values to strictly finite JSON-compatible structures.

    Replaces NaN, Infinity, -Infinity with None.
    Converts Enums and Dataclasses to serializable forms.
    """
    if value is None:
        return None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return json_safe(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        return json_safe(asdict(value))
    return str(value)


def write_atomic_json(path: PathLike, data: Any, *, indent: Optional[int] = 2) -> Path:
    """Write data to a file atomically via temp file in the same directory + os.replace.

    Guarantees that readers never observe partial or corrupt files.
    Enforces finite JSON serialization (allow_nan=False).
    """
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    clean_data = json_safe(data)
    encoded = json.dumps(clean_data, indent=indent, allow_nan=False)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    return target


@dataclass
class PlatformCapability:
    """Detected host system capabilities."""
    os_name: str
    platform_release: str
    is_windows: bool
    powershell_available: bool
    powershell_binary: Optional[str] = None
    powershell_version: Optional[str] = None
    symlink_supported: bool = False
    file_locking_supported: bool = True
    python_version: str = field(default_factory=lambda: sys.version)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AcceptanceCaseResult:
    """Structured result of an individual acceptance test case."""
    name: str
    category: AcceptanceCategory
    status: TestStatus
    platform: str
    elapsed_s: float
    details: str
    error: Optional[str] = None
    windows_specific: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        data["status"] = self.status.value
        return json_safe(data)


@dataclass
class PlatformMatrix:
    """Summary matrix of platform compatibility and supported feature areas."""
    os_name: str
    platform_release: str
    python_version: str
    is_windows: bool
    powershell_available: bool
    powershell_version: Optional[str]
    supported_categories: List[str]
    unsupported_categories: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AcceptanceReport:
    """Complete, tamper-evident report of the acceptance test suite execution."""
    schema_version: str
    generated_at: str
    platform_matrix: PlatformMatrix
    total_tests: int
    passed: int
    failed: int
    unsupported: int
    skipped: int
    results: List[AcceptanceCaseResult]
    all_passed: bool
    checksum: str

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "platform_matrix": self.platform_matrix.to_dict(),
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "unsupported": self.unsupported,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
            "all_passed": self.all_passed,
        }
        return {**payload, "checksum": self.checksum}


def compute_report_checksum(report_dict: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 digest of canonical report payload excluding checksum."""
    data = {k: v for k, v in report_dict.items() if k != "checksum"}
    clean = json_safe(data)
    canonical = json.dumps(clean, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
