"""Closed vocabularies for null calibration."""

from __future__ import annotations

SCHEMA_ID = "NeuroTopology.NullCalibration.v1"
AUDITOR_ID = "null_calibration_audit"
AUDITOR_VERSION = "1.0.0"

NULL_MODELS: tuple[str, ...] = (
    "flat",
    "gaussian",
    "phase_shuffle",
    "label_permutation",
    "circular_shift",
    "block_shuffle",
    "matched_variance",
    "matched_autocorrelation",
)

METRIC_FAMILIES: tuple[str, ...] = (
    "graph_beta1",
    "spatial_winding_q",
    "scalar_chirality",
    "other",
)

CORRECTION_METHODS: tuple[str, ...] = (
    "none",
    "bonferroni",
    "holm",
)

CALIBRATION_STATUS: tuple[str, ...] = (
    "CALIBRATION_ONLY",
    "INSUFFICIENT",
    "ERROR",
    "NOT_SUPPORTED",
)

MIN_REPLICATES_WARN = 100
MIN_REPLICATES_HARD = 2

SCIENTIFIC_PASS_FORBIDDEN = True
