"""Typed black-box contracts and data models for Batch 1 research-cycle infrastructure.

Defines versioned schemas for:
- Bounded chunk-cache planning
- Resumable transfer metadata
- Cache eviction tracking
- Atomic write specifications
- Simulation checkpoint/recovery states
- Acceptance scenario results and reports
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Sequence


def json_safe(val: Any) -> Any:
    """Recursively converts structures to strictly JSON-compliant types.

    Non-finite floats (NaN, +Inf, -Inf) are converted to None.
    Enums are converted to their value strings.
    """
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, (int, str, bool)) or val is None:
        return val
    if isinstance(val, dict):
        return {str(k): json_safe(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [json_safe(x) for x in val]
    return str(val)


def dumps_finite_json(obj: Any, *, indent: Optional[int] = 2) -> str:
    """Serializes an object to JSON ensuring allow_nan=False."""
    safe_obj = json_safe(obj)
    return json.dumps(safe_obj, indent=indent, allow_nan=False, sort_keys=True)


class ScenarioOutcome(str, Enum):
    """Execution outcome status for an individual scenario."""
    PASS = "PASS"
    FAIL = "FAIL"
    UNSUPPORTED = "UNSUPPORTED"
    PENDING = "PENDING"
    ERROR = "ERROR"


class PlatformStatus(str, Enum):
    """Overall platform support classification."""
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"


class FailureClassification(str, Enum):
    """Categorization of failure modes."""
    TIMEOUT = "TIMEOUT"
    PROCESS_ORPHAN = "PROCESS_ORPHAN"
    FILE_LOCK = "FILE_LOCK"
    ENCODING_ERROR = "ENCODING_ERROR"
    COMMAND_CONSTRUCTION = "COMMAND_CONSTRUCTION"
    NON_FINITE_NUMERIC = "NON_FINITE_NUMERIC"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
    SUBPROCESS_ERROR = "SUBPROCESS_ERROR"
    NONE = "NONE"


@dataclass
class BoundedChunkCachePlan:
    """Contract for planning chunked caching under a strict byte budget."""
    schema_version: str = "ResearchRuntime.ChunkCachePlan.v1"
    dataset_id: str = ""
    total_bytes: int = 0
    chunk_size_bytes: int = 1024 * 1024  # 1 MiB default
    max_cache_budget_bytes: int = 10 * 1024 * 1024  # 10 MiB default
    eviction_policy: str = "LRU"
    chunk_count: int = 0
    planned_chunks: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.chunk_size_bytes > 0 and self.total_bytes > 0:
            self.chunk_count = math.ceil(self.total_bytes / self.chunk_size_bytes)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


@dataclass
class ResumableTransferMetadata:
    """Contract for tracking resumable download/upload chunk state."""
    schema_version: str = "ResearchRuntime.ResumableTransfer.v1"
    transfer_id: str = ""
    source_uri: str = ""
    destination_path: str = ""
    total_expected_bytes: int = 0
    transferred_bytes: int = 0
    chunk_count: int = 0
    completed_chunks: List[int] = field(default_factory=list)
    active_chunk_index: Optional[int] = None
    resume_token: str = ""
    checksum_sha256: str = ""
    is_resumable: bool = True
    is_complete: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


@dataclass
class CacheEvictionPlan:
    """Contract for tracking cache eviction decisions when budget is exceeded."""
    schema_version: str = "ResearchRuntime.CacheEviction.v1"
    cache_root: str = ""
    current_size_bytes: int = 0
    budget_limit_bytes: int = 0
    target_freed_bytes: int = 0
    evicted_keys: List[str] = field(default_factory=list)
    retained_keys: List[str] = field(default_factory=list)
    resulting_size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


@dataclass
class AtomicWriteSpec:
    """Contract for atomic artifact writes avoiding partial file visibility."""
    schema_version: str = "ResearchRuntime.AtomicWrite.v1"
    destination_path: str = ""
    temp_prefix: str = ".tmp_"
    require_sync: bool = True
    strategy: str = "os.replace"
    replace_success: bool = False
    written_bytes: int = 0
    checksum_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


@dataclass
class SimulationCheckpointSpec:
    """Contract for simulation campaign state persistence and recovery."""
    schema_version: str = "ResearchRuntime.SimulationCheckpoint.v1"
    campaign_id: str = ""
    run_id: str = ""
    step_index: int = 0
    total_steps: int = 0
    rng_seed: int = 0
    rng_state_hash: str = ""
    state_payload_hash: str = ""
    checkpoint_file: str = ""
    is_recoverable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


@dataclass
class AcceptanceScenarioResult:
    """Standard result record for each acceptance scenario."""
    test_case: str
    category: str
    platform_rule: str
    status: ScenarioOutcome
    command: Optional[List[str]] = None
    exit_code: Optional[int] = None
    timeout_state: bool = False
    orphan_cleanup_state: str = "n/a"  # 'clean', 'orphans_detected', 'n/a'
    artifact_checksum: Optional[str] = None
    failure_classification: FailureClassification = FailureClassification.NONE
    unsupported_reason: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


@dataclass
class AcceptanceReport:
    """Root versioned acceptance report for cross-platform research runtime."""
    schema_version: str = "NeuroTopologySim.ResearchRuntimeAcceptanceReport.v1"
    timestamp_utc: str = ""
    host_platform: str = ""
    host_os_name: str = ""
    is_windows: bool = False
    is_posix: bool = False
    python_version: str = ""
    repo_commit: str = ""
    powershell_available: bool = False
    powershell_version: Optional[str] = None
    psutil_available: bool = False
    total_cases: int = 0
    supported_cases: int = 0
    unsupported_cases: int = 0
    failed_cases: int = 0
    pending_cases: int = 0
    platform_status: PlatformStatus = PlatformStatus.SUPPORTED
    results: List[AcceptanceScenarioResult] = field(default_factory=list)
    summary_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))
