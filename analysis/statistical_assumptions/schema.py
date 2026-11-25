"""Closed vocabularies for the assumption audit."""
from __future__ import annotations

SCHEMA_ID = "NeuroTopology.StatisticalAssumptionAudit.v1"
AUDITOR_ID = "statistical_assumption_audit"
AUDITOR_VERSION = "1.0.0"
EVIDENCE_CLASS = "statistical_assumption_audit"

AUDIT_STATES: tuple[str, ...] = (
    "AUDIT_CLEAN",
    "AUDIT_INCOMPLETE",
    "AUDIT_INVALID_INPUT",
    "AUDIT_INSUFFICIENT_POWER",
    "AUDIT_MULTIPLICITY_UNRESOLVED",
    "AUDIT_NULL_MODEL_UNRESOLVED",
    "AUDIT_SYNTHETIC_ONLY",
    "AUDIT_SCIENTIFIC_REVIEW_REQUIRED",
)

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}

METRIC_FAMILIES = ("graph_beta1", "spatial_winding_q", "scalar_chirality", "other")
KNOWN_NULL_MODELS = (
    "flat", "gaussian", "phase_shuffle", "label_permutation",
    "circular_shift", "block_shuffle", "matched_variance", "matched_autocorrelation",
)
KNOWN_CORRECTIONS = ("none", "bonferroni", "holm")
MIN_PAIRS_WARN = 8
MIN_NULL_REPLICATES = 100
