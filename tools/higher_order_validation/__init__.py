"""Adversarial synthetic validation for the higher-order signal stack.

Engineering evidence only — never empirical neuroscience, never a scientific
PASS, never a formal Bayes factor. Higher-order feature / forecasting /
null-calibration implementations are consumed read-only when present.
"""
from __future__ import annotations

from tools.higher_order_validation.schema import (
    SCHEMA_VERSION,
    EVIDENCE_CLASS,
    CaseOutcome,
    ValidationCaseResult,
)
from tools.higher_order_validation.suite import run_validation_suite
from tools.higher_order_validation.report import dumps, render_markdown, write_reports

__all__ = [
    "SCHEMA_VERSION",
    "EVIDENCE_CLASS",
    "CaseOutcome",
    "ValidationCaseResult",
    "run_validation_suite",
    "dumps",
    "render_markdown",
    "write_reports",
]

__version__ = "1.0.0"
