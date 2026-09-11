"""Cross-platform research runtime acceptance harness package."""
from __future__ import annotations

from .contracts import (
    AcceptanceReport,
    AcceptanceScenarioResult,
    AtomicWriteSpec,
    BoundedChunkCachePlan,
    CacheEvictionPlan,
    FailureClassification,
    PlatformStatus,
    ResumableTransferMetadata,
    ScenarioOutcome,
    SimulationCheckpointSpec,
    dumps_finite_json,
    json_safe,
)
from .harness import (
    generate_markdown_report,
    run_acceptance_suite,
)
from .platform_checks import (
    build_powershell_command,
    check_windows_file_locking,
    detect_powershell,
    has_posix_process_groups,
    is_posix,
    is_windows,
    normalize_windows_path,
    terminate_process_tree,
)

__all__ = [
    "AcceptanceReport",
    "AcceptanceScenarioResult",
    "BoundedChunkCachePlan",
    "ResumableTransferMetadata",
    "CacheEvictionPlan",
    "AtomicWriteSpec",
    "SimulationCheckpointSpec",
    "ScenarioOutcome",
    "PlatformStatus",
    "FailureClassification",
    "dumps_finite_json",
    "json_safe",
    "run_acceptance_suite",
    "generate_markdown_report",
    "is_windows",
    "is_posix",
    "detect_powershell",
    "build_powershell_command",
    "has_posix_process_groups",
    "terminate_process_tree",
    "check_windows_file_locking",
    "normalize_windows_path",
]
