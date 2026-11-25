"""INDEPENDENT ORACLE — Batch 2 Cursor C Round 6 finite chain-complex audit.

This package is **not** a production engine and is **not** the Round 6 candidate.
No Round 6 finite chain-complex implementation was present on ``origin/main`` at
audit base SHA; this oracle exists solely for algebraic cross-checks on small
synthetic complexes.

Status: HOLD / SYNTHETIC_ONLY. No scientific VALIDATED/PASS claims.
"""

from __future__ import annotations

ORACLE_LABEL = "INDEPENDENT_ORACLE_BATCH2_CURSOR_C"
AUDIT_STATUS = "HOLD"
DATA_MODE = "SYNTHETIC_ONLY"

__all__ = [
    "ORACLE_LABEL",
    "AUDIT_STATUS",
    "DATA_MODE",
]
