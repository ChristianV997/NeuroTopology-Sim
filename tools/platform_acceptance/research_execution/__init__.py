"""Cross-platform acceptance harness for research execution.

Verifies bounded data access, cache eviction, process-isolated execution, output containment,
timeout handling, PowerShell operations, and platform-specific guarantees.
"""
from __future__ import annotations

from tools.platform_acceptance.research_execution.harness import (
    ResearchExecutionAcceptanceHarness,
)
from tools.platform_acceptance.research_execution.probes import (
    build_powershell_command,
    detect_platform_capability,
    probe_file_locking_support,
    probe_powershell,
    probe_symlink_support,
    ps_single_quote,
)
from tools.platform_acceptance.research_execution.types import (
    AcceptanceCaseResult,
    AcceptanceCategory,
    AcceptanceReport,
    PlatformCapability,
    PlatformMatrix,
    TestStatus,
    compute_report_checksum,
    json_safe,
    write_atomic_json,
)

__all__ = [
    "AcceptanceCategory",
    "TestStatus",
    "PlatformCapability",
    "AcceptanceCaseResult",
    "PlatformMatrix",
    "AcceptanceReport",
    "compute_report_checksum",
    "json_safe",
    "write_atomic_json",
    "ps_single_quote",
    "build_powershell_command",
    "probe_powershell",
    "probe_symlink_support",
    "probe_file_locking_support",
    "detect_platform_capability",
    "ResearchExecutionAcceptanceHarness",
]
