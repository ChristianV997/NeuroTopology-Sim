"""Local-only migration-wave benchmark package.

Compares current origin/main with PRs #331, #344, #345, and #346 for bounded
data access, cache eviction, and resumable streaming. Synthetic fixtures only.
`evidence_class` is always `performance_only`. Production modules are not edited.
"""
from __future__ import annotations

from .schema import EVIDENCE_CLASS, SCHEMA_VERSION, TARGET_NAMES, VARIANT_NAMES

__all__ = [
    "EVIDENCE_CLASS",
    "SCHEMA_VERSION",
    "TARGET_NAMES",
    "VARIANT_NAMES",
]
