"""Deterministic local-only research-cycle end-to-end smoke harness.

Consumes canonical Batch 1 / release-evidence interfaces without modifying them.
Synthetic fixtures are engineering acceptance evidence only — never scientific PASS.
"""
from __future__ import annotations

from tools.release_readiness.research_cycle_smoke.schema import (
    SCHEMA_VERSION,
    SMOKE_EVIDENCE_CLASS,
    ScenarioId,
)
from tools.release_readiness.research_cycle_smoke.runner import run_smoke_suite

__all__ = [
    "SCHEMA_VERSION",
    "SMOKE_EVIDENCE_CLASS",
    "ScenarioId",
    "run_smoke_suite",
]
