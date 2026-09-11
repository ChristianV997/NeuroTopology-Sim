"""Read-only research-cycle operator pack.

Wraps existing repository CLIs. Does not invent validators, download data,
run solvers, or treat infrastructure PASS as scientific PASS.
"""

from __future__ import annotations

PACK_ID = "research_cycle_operator_pack"
PACK_VERSION = "1.0.0"
SCHEMA_VERSION = "ResearchCycleOperatorReport.v1"
CATALOG_SCHEMA = "ResearchCycleOperatorCatalog.v1"

__all__ = ["PACK_ID", "PACK_VERSION", "SCHEMA_VERSION", "CATALOG_SCHEMA"]
