"""Local-only Batch-2 pipeline performance benchmark package.

Measures synthetic streaming/simulation bottleneck patterns without modifying
production code. Performance evidence only — never scientific evidence.
"""
from __future__ import annotations

from .budgets import ResourceBudgets, compare_budget
from .fixtures import make_fixture
from .harness import SCHEMA_VERSION, TOOLING_AVAILABILITY, run_all, run_target
from .schema import EVIDENCE_CLASS, TARGET_NAMES
from .telemetry import dumps, execute_child, json_safe, measure
from .workloads import TARGETS, TargetSpec

__all__ = [
    "EVIDENCE_CLASS",
    "SCHEMA_VERSION",
    "TARGET_NAMES",
    "TARGETS",
    "TOOLING_AVAILABILITY",
    "TargetSpec",
    "ResourceBudgets",
    "compare_budget",
    "make_fixture",
    "run_all",
    "run_target",
    "dumps",
    "execute_child",
    "json_safe",
    "measure",
]
