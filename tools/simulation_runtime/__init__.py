"""Reliable, bounded, and resumable simulation campaign runtime.

Provides manifest-first campaign execution, atomic per-unit result recording,
cross-platform process-tree cleanup, disk and memory guards, retryable infrastructure
classification, and explicit terminal outcomes without silent partial success.
"""
from __future__ import annotations

from tools.simulation_runtime.types import (
    Outcome,
    WorkUnit,
    UnitResult,
    CampaignManifest,
    ResourcePolicy,
    CampaignState,
    capture_environment_metadata,
    is_retryable_outcome,
)
from tools.simulation_runtime.checkpoint import (
    CampaignCheckpointManager,
    CheckpointMismatchError,
    CheckpointCorruptError,
)
from tools.simulation_runtime.guards import (
    check_disk_budget,
    check_memory_budget,
    check_dependencies,
)
from tools.simulation_runtime.atomic_io import (
    write_atomic_json,
    load_json,
    json_safe,
    compute_sha256,
    compute_config_hash,
    get_git_commit,
)
from tools.simulation_runtime.runner import (
    SimulationCampaignRunner,
    run_campaign_manifest,
)
from tools.simulation_runtime.process_cleanup import (
    ProcessExecutionResult,
    run_isolated_process,
)

__all__ = [
    "Outcome",
    "WorkUnit",
    "UnitResult",
    "CampaignManifest",
    "ResourcePolicy",
    "CampaignState",
    "capture_environment_metadata",
    "is_retryable_outcome",
    "CampaignCheckpointManager",
    "CheckpointMismatchError",
    "CheckpointCorruptError",
    "check_disk_budget",
    "check_memory_budget",
    "check_dependencies",
    "write_atomic_json",
    "load_json",
    "json_safe",
    "compute_sha256",
    "compute_config_hash",
    "get_git_commit",
    "ProcessExecutionResult",
    "run_isolated_process",
    "SimulationCampaignRunner",
    "run_campaign_manifest",
]
