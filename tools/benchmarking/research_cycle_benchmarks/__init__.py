"""Local-only bounded benchmark harness for research-cycle infrastructure.

Measures throughput, memory (tracemalloc + optional RSS), disk usage,
determinism, budget compliance, and failure recovery for research-cycle,
artifact, cache, and simulation-runtime *contracts* -- using deterministic local
fixtures and protocol adapters only. It imports no simulation kernels,
performance-policy, process-runner, streaming, orchestrator, or database code,
and depends on no files another agent is producing in this wave.

Nothing here downloads datasets, runs real simulations, or calls external APIs.
Synthetic output is performance evidence only and makes no scientific claims.
"""
from __future__ import annotations

from .telemetry import (
    ChildResult,
    MemoryTelemetry,
    dir_size_bytes,
    dumps,
    execute_child,
    json_safe,
    measure,
)
from .budgets import ResourceBudgets, compare_budget
from .fixtures import make_fixture
from .workloads import TARGETS, TargetSpec
from .harness import (
    SCHEMA_VERSION,
    run_all,
    run_target,
)

__all__ = [
    "ChildResult",
    "MemoryTelemetry",
    "dir_size_bytes",
    "dumps",
    "execute_child",
    "json_safe",
    "measure",
    "ResourceBudgets",
    "compare_budget",
    "make_fixture",
    "TARGETS",
    "TargetSpec",
    "SCHEMA_VERSION",
    "run_all",
    "run_target",
]
