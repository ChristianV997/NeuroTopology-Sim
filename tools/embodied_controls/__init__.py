"""Embodied-control alignment layer for multimodal physiology and neural windows.

Embodied variables are candidate explanatory features, moderators, covariates,
or possible intervention targets; they are not proven causal mechanisms.
"""
from __future__ import annotations

from tools.embodied_controls.types import (
    AlignmentMetadata,
    AlignmentQualityState,
    AutonomicProxyFeatures,
    CardiacWindowFeatures,
    ClockDriftDiagnostics,
    ConfoundControlResult,
    ConfoundControlType,
    EmbodiedControlAlignmentReport,
    EvidenceClass,
    InterpolationMethod,
    LagCandidate,
    NeuralWindowFeatures,
    ResamplingRecord,
    RespiratoryWindowFeatures,
    VariableRole,
)
from tools.embodied_controls.aligner import EmbodiedControlAligner

__all__ = [
    "AlignmentMetadata",
    "AlignmentQualityState",
    "AutonomicProxyFeatures",
    "CardiacWindowFeatures",
    "ClockDriftDiagnostics",
    "ConfoundControlResult",
    "ConfoundControlType",
    "EmbodiedControlAlignmentReport",
    "EmbodiedControlAligner",
    "EvidenceClass",
    "InterpolationMethod",
    "LagCandidate",
    "NeuralWindowFeatures",
    "ResamplingRecord",
    "RespiratoryWindowFeatures",
    "VariableRole",
]
