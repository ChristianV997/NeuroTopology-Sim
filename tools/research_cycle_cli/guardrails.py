"""Shared vocabularies, diagnostics, and finite-value helpers.

Vocabularies mirror the real, read-only Batch 1 modules exactly (see the
package docstring) so this CLI's own validation can tell "a value this
schema doesn't recognize" (worth a diagnostic) from "a value this schema
does recognize" without guessing at either system's intent.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# --- Ledger vocabulary (apps/awareness_studio/.../research_cycle/models.py) -

LEDGER_STATUSES = {"PENDING", "IN_PROGRESS", "COMPLETED", "INCONCLUSIVE", "BLOCKED", "FAILED", "REVIEW_REQUIRED", "FINALIZED"}

LEDGER_RECORD_TYPES = {
    "source_snapshot", "evidence_record", "claim", "hypothesis", "experiment_spec",
    "run_record", "artifact_manifest", "validation_report", "theory_revision",
}

#: The nine-way evidence classification. Identical across the ledger
#: (EvidenceClass), the claim gate (CLAIM_CLASSES), and this repo's own
#: earlier compilers -- a genuinely converged, shared vocabulary.
EVIDENCE_CLASSES = {
    "engineering_fact", "benchmark_result", "synthetic_demonstration", "descriptive_empirical",
    "proxy_inference", "formal_statistical_evidence", "hypothesis", "speculation", "unsupported_claim",
}

# --- Claim gate vocabulary (tools/research_claim_gate/gate.py) -------------

CLAIM_GATE_DECISIONS = {
    "CLAIM_ADMISSIBLE", "CLAIM_REQUIRES_REVIEW", "CLAIM_DOWNGRADED", "CLAIM_REJECTED",
    "CLAIM_INCOMPLETE", "CLAIM_SYNTHETIC_ONLY", "CLAIM_PROVENANCE_INVALID", "CLAIM_NOT_COMPARABLE",
}
CLAIM_GATE_SEVERITIES = {"info", "warning", "error", "critical"}

# --- Simulation-artifact extractor vocabulary (tools/simulation_artifacts/extractor.py) -

ARTIFACT_RUN_STATUSES = {"COMPLETE", "INCOMPLETE", "PARTIAL", "FAILED", "CONFLICTING", "BLOCKED"}

# --- This CLI's own operator-facing groupings -------------------------------

#: How a ledger cycle's (status, finalized) pair maps onto the operator
#: question "which cycles are frozen/active/blocked/failed/incomplete" --
#: a cycle can be both e.g. FINALIZED and (independently) "frozen" via the
#: finalized flag, so this mapping is many-to-one on purpose (a cycle may
#: appear in more than one bucket only when that is what the data says).
CYCLE_GROUP_ACTIVE = {"IN_PROGRESS"}
CYCLE_GROUP_BLOCKED = {"BLOCKED"}
CYCLE_GROUP_FAILED = {"FAILED"}
CYCLE_GROUP_INCOMPLETE = {"PENDING", "REVIEW_REQUIRED", "INCONCLUSIVE"}
# "frozen" is derived from the ledger's own `finalized` flag, not `status`.

# --- Diagnostics -------------------------------------------------------------

MISSING_SOURCE = "missing_source"
INVALID_JSON = "invalid_json"
INVALID_DATABASE = "invalid_database"
UNKNOWN_VOCABULARY_VALUE = "unknown_vocabulary_value"
UNCORRELATED_REFERENCE = "uncorrelated_reference"
NON_FINITE_VALUE = "non_finite_value"

DIAGNOSTIC_KINDS = {MISSING_SOURCE, INVALID_JSON, INVALID_DATABASE, UNKNOWN_VOCABULARY_VALUE, UNCORRELATED_REFERENCE, NON_FINITE_VALUE}


@dataclass(frozen=True)
class Diagnostic:
    kind: str
    source: str
    detail: str
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "source": self.source, "detail": self.detail, "record_id": self.record_id}


def safe_number(value: Any) -> float | None:
    """Finite float, or None. Rejects NaN/Infinity in any spelling."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "inf", "-inf", "+inf", "infinity", "-infinity", "+infinity"}:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def contains_non_finite(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(contains_non_finite(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_non_finite(v) for v in value)
    return False
