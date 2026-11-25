"""Mobile-compatible research-record compiler.

See docs/reporting/research_record_contract.md for the input/output
contract. This package is deliberately self-contained: it does not import
tools/research_report or tools/mobile_report (two prior, still-unmerged
compilers doing an overlapping job -- see the collision note at the top
of the contract doc) or any other release/reconciliation tooling.
"""
from __future__ import annotations

from tools.research_record.versions import COMPILER_VERSION, REPORT_SCHEMA_VERSION

__all__ = ["COMPILER_VERSION", "REPORT_SCHEMA_VERSION"]
