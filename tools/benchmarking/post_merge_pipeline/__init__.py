"""Post-merge pipeline measurement package.

Measures current ``origin/main`` planning and recovery paths with synthetic
local fixtures after the streaming-ingest merge. Performance evidence only.
Does not modify production modules.
"""
from __future__ import annotations

from .adapters import probe_all, production_available
from tools.benchmarking.pipeline_efficiency.budgets import ResourceBudgets, compare_budget
from .fixtures import make_fixture
from .harness import SCHEMA_VERSION, run_all, run_target
from .schema import EVIDENCE_CLASS, TARGET_NAMES
from tools.benchmarking.pipeline_efficiency.telemetry import dumps, execute_child, json_safe, measure
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
