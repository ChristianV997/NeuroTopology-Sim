"""Deterministic local-only research-cycle end-to-end smoke harness."""
from __future__ import annotations

from tools.release_readiness.research_cycle_smoke.schema import (
    SCHEMA_VERSION,
    SMOKE_EVIDENCE_CLASS,
    ScenarioId,
)

__all__ = [
    "SCHEMA_VERSION",
    "SMOKE_EVIDENCE_CLASS",
    "ScenarioId",
    "run_smoke_suite",
]


def __getattr__(name: str):
    if name == "run_smoke_suite":
        from tools.release_readiness.research_cycle_smoke.runner import run_smoke_suite

        return run_smoke_suite
    raise AttributeError(name)
