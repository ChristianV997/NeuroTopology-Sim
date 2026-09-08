"""Deterministic research-state and evidence-report compiler.

See docs/research/report_contract.md for the input/output contract.
"""
from __future__ import annotations

from tools.research_report.versions import COMPILER_VERSION, REPORT_SCHEMA_VERSION

__all__ = ["COMPILER_VERSION", "REPORT_SCHEMA_VERSION"]
