"""Awareness Studio research-cycle orchestrator.

Deterministically connects literature evidence, hypotheses, experiment
plans, simulation/analysis execution, null/surrogate validation, evidence
updates, theory revision, and a paper-ready draft -- without ever
discovering or executing arbitrary code, and without ever letting an
unsupported claim present itself as a scientific conclusion.

Self-contained: does not import tools.awareness_studio_research (the
literature registry, owned by Claude A), tools.research_cycle (owned by
Antigravity C), or tools.research_record / tools.release_manifest (other
agents' owned packages elsewhere in this repo). Those systems are
consumed only through the explicit JSON/YAML/CSV contracts documented in
docs/awareness_studio/research_cycle_orchestration.md.

See that document for the full contract, the 14 cycle states, the 9
mandatory gates, and the forbidden-language policy.
"""
from __future__ import annotations

from tools.awareness_studio_research_loop.versions import (
    COMPILER_VERSION,
    INPUT_CONTRACT_VERSION,
    REPORT_SCHEMA_VERSION,
)

__all__ = ["COMPILER_VERSION", "INPUT_CONTRACT_VERSION", "REPORT_SCHEMA_VERSION"]
