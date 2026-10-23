"""Batch 3 offline integration: deterministic allowlisted fixture runner.

Composes merged-main research-cycle stages for execution-order and
failure-propagation testing. ENGINEERING_ONLY / SYNTHETIC_ONLY only.
"""
from __future__ import annotations

from tools.batch3_offline_integration.runner import run_offline_integration, write_report
from tools.batch3_offline_integration.schema import (
    EVIDENCE_CLASS,
    RESULT_LABEL_ENGINEERING,
    SCHEMA_VERSION,
)

__all__ = [
    "EVIDENCE_CLASS",
    "RESULT_LABEL_ENGINEERING",
    "SCHEMA_VERSION",
    "run_offline_integration",
    "write_report",
]
