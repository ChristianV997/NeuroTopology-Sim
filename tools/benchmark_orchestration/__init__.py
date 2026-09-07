"""Deterministic benchmark orchestration for NeuroTopology-Sim.

Reads a declarative benchmark matrix, validates every case, runs each case in
an isolated subprocess under per-case / campaign timeouts and worker caps, and
emits finite JSON + Markdown reports. Timeouts are never converted to PASS;
retries are bounded; resume skips already-recorded terminal outcomes.

This package does not modify streaming, telemetry, checkpoint, or performance-
policy modules. Synthetic fixtures and dry-run plans are engineering scaffolding
only — never scientific evidence.
"""
from __future__ import annotations

from tools.benchmark_orchestration.schema import (
    MATRIX_SCHEMA_VERSION,
    CaseResult,
    CaseSpec,
    CaseStatus,
    CampaignConfig,
    CampaignReport,
    MatrixSpec,
)
from tools.benchmark_orchestration.matrix import load_matrix, validate_matrix
from tools.benchmark_orchestration.orchestrator import run_campaign
from tools.benchmark_orchestration.report import dumps_json, render_markdown, write_reports

__all__ = [
    "MATRIX_SCHEMA_VERSION",
    "CaseResult",
    "CaseSpec",
    "CaseStatus",
    "CampaignConfig",
    "CampaignReport",
    "MatrixSpec",
    "load_matrix",
    "validate_matrix",
    "run_campaign",
    "dumps_json",
    "render_markdown",
    "write_reports",
]

__version__ = "1.0.0"
