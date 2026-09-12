"""Execution contracts for safe local work units."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


# Execution remains bounded when a caller does not provide an override. These
# are resource guardrails, not claims about the workload's scientific validity.
DEFAULT_MEMORY_BUDGET_BYTES = 512 * 1024 * 1024
DEFAULT_DISK_BUDGET_BYTES = 512 * 1024 * 1024


class ExecutionState(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    NOT_RUN = "NOT_RUN"
    BLOCKED = "BLOCKED"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


@dataclass(frozen=True)
class WorkUnit:
    """A fully declared unit; command and expected outputs are never inferred."""

    unit_id: str
    workload_id: str
    argv: tuple[str, ...]
    output_dir: Path
    expected_outputs: tuple[str, ...] = ("unit_manifest.json",)
    input_references: tuple[str, ...] = ()
    seed: int | None = None
    config: Mapping[str, Any] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()
    timeout_s: float | None = None

    @classmethod
    def make(cls, unit_id: str, workload_id: str, argv: Sequence[str], output_dir: str | Path, **kwargs: Any) -> "WorkUnit":
        return cls(unit_id=unit_id, workload_id=workload_id, argv=tuple(str(item) for item in argv), output_dir=Path(output_dir), **kwargs)


@dataclass(frozen=True)
class RunnerConfig:
    output_root: Path
    allowed_commands: Mapping[str, tuple[str, ...]]
    default_timeout_s: float = 300.0
    stdout_limit: int = 16_384
    stderr_limit: int = 16_384
    runtime_budget_s: float | None = None
    memory_budget_bytes: int | None = DEFAULT_MEMORY_BUDGET_BYTES
    disk_budget_bytes: int | None = DEFAULT_DISK_BUDGET_BYTES
    network_disabled: bool = True
    code_revision: str = "unknown"
    deterministic_seed: int | None = 0
    environment: Mapping[str, str] = field(default_factory=dict)
