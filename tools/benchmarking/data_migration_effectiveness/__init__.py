"""Measurement-only harness for bounded-access vs rejected full-object requests.

Does not modify production data-access or streaming implementations.
Evidence class is always performance_only. Missing metrics stay null.
"""
from __future__ import annotations

from tools.benchmarking.data_migration_effectiveness.schema import (
    EVIDENCE_CLASS,
    SCHEMA_VERSION,
    TARGET_NAMES,
)

__all__ = [
    "SCHEMA_VERSION",
    "EVIDENCE_CLASS",
    "TARGET_NAMES",
    "run_all",
    "run_target",
]


def __getattr__(name: str):
    if name in {"run_all", "run_target"}:
        from tools.benchmarking.data_migration_effectiveness.harness import run_all, run_target

        return run_all if name == "run_all" else run_target
    raise AttributeError(name)
