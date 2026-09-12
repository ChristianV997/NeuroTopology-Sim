"""Local-only pipeline-efficiency benchmark package.

Measures research-cycle, bounded-cache, artifact-lineage, and simulation-planning
paths with synthetic fixtures. Performance evidence only.
"""
from __future__ import annotations

from .adapters import probe_all, production_available
from .budgets import ResourceBudgets, compare_budget
from .fixtures import make_fixture
from .harness import SCHEMA_VERSION, run_all, run_target
from .schema import EVIDENCE_CLASS, TARGET_NAMES
from .telemetry import dumps, execute_child, json_safe, measure
from .workloads import TARGETS, TargetSpec

__all__ = [
    "EVIDENCE_CLASS",
    "SCHEMA_VERSION",
    "TARGET_NAMES",
    "TARGETS",
    "TargetSpec",
    "ResourceBudgets",
    "compare_budget",
    "make_fixture",
    "probe_all",
    "production_available",
    "run_all",
    "run_target",
    "dumps",
    "execute_child",
    "json_safe",
    "measure",
]
