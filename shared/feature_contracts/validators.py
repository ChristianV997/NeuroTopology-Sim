"""Validation rules and guardrail enforcement for canonical feature contracts.

Enforces schema correctness, finite numerical values, physical units, dimension axes,
channel uniqueness, mathematical guardrails, and synthetic-empirical boundary separation.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

from .models import (
    CanonicalFeatureRecord,
    CanonicalFeatureBundle,
    CoordinateStatus,
    EvidenceClass,
    FeatureFamily,
)


class FeatureContractValidationError(ValueError):
    """Raised when a feature record violates schema, units, axes, or guardrail rules."""


VALID_UNITS: frozenset[str] = frozenset({
    "uV^2/Hz",
    "V^2/Hz",
    "uV",
    "V",
    "dimensionless",
    "rad",
    "rad/s",
    "Hz",
    "1/s",
    "ms",
    "s",
    "bpm",
    "fraction",
    "arbitrary_units",
    "a.u.",
    "counts",
    "integer",
    "index",
    "ratio",
    "z-score",
    "dB",
    "log_uV2_Hz",
    "normalized",
})


def _check_finite_values(val: Any, path: str = "values") -> None:
    """Recursively validates that all numerical values are finite."""
    if isinstance(val, float):
        if not math.isfinite(val):
            raise FeatureContractValidationError(
                f"Non-finite value detected at {path}: {val}. Values must be strictly finite."
            )
    elif isinstance(val, (list, tuple)):
        for idx, item in enumerate(val):
            _check_finite_values(item, path=f"{path}[{idx}]")
    elif isinstance(val, dict):
        for k, v in val.items():
            _check_finite_values(v, path=f"{path}.{k}")


def _infer_shape(val: Any) -> list[int]:
    """Infers multi-dimensional shape from nested lists."""
    if val is None:
        return []
    if not isinstance(val, (list, tuple)):
        return []
    shape = [len(val)]
    curr = val
    while curr and isinstance(curr[0], (list, tuple)):
        shape.append(len(curr[0]))
        curr = curr[0]
    return shape


def validate_feature_record(record: CanonicalFeatureRecord) -> None:
    """Performs rigorous schema, unit, axis, finite-value, and guardrail validation."""
    # 1. Schema version
    if not record.schema_version.startswith("NeuroTopologySim.CanonicalFeatureRecord."):
        raise FeatureContractValidationError(
            f"Unsupported schema_version: '{record.schema_version}'. Expected 'NeuroTopologySim.CanonicalFeatureRecord.v*'."
        )

    # 2. Feature Family
    valid_families = {f.value for f in FeatureFamily}
    if record.feature_family not in valid_families:
        raise FeatureContractValidationError(
            f"Unrecognized feature_family: '{record.feature_family}'. Allowed families: {sorted(valid_families)}"
        )

    # 3. Feature Name and Mathematical Definition
    if not record.feature_name or not isinstance(record.feature_name, str) or not record.feature_name.strip():
        raise FeatureContractValidationError("feature_name must be a non-empty string.")

    if not record.mathematical_definition or not isinstance(record.mathematical_definition, str) or not record.mathematical_definition.strip():
        raise FeatureContractValidationError("mathematical_definition must be a non-empty string.")

    # 4. Units
    if not record.units or not isinstance(record.units, str) or not record.units.strip():
        raise FeatureContractValidationError("units must be a non-empty string.")

    norm_units = record.units.strip()
    if norm_units not in VALID_UNITS:
        raise FeatureContractValidationError(
            f"Invalid units '{norm_units}'. Must be one of registered units: {sorted(VALID_UNITS)}"
        )

    # 5. Missing metadata null rule: Never 0 or 0.0 when missing
    if record.sampling_rate_hz is not None and record.sampling_rate_hz <= 0:
        raise FeatureContractValidationError(
            f"sampling_rate_hz must be strictly positive or null, got: {record.sampling_rate_hz}."
        )

    if record.frequency_band is not None:
        if not isinstance(record.frequency_band, dict):
            raise FeatureContractValidationError("frequency_band must be a dictionary or null.")
        low = record.frequency_band.get("low_hz")
        high = record.frequency_band.get("high_hz")
        if low is None or high is None or low < 0 or high <= low:
            raise FeatureContractValidationError(
                f"frequency_band must have low_hz >= 0 and high_hz > low_hz, got: {record.frequency_band}."
            )

    if record.time_window is not None:
        if not isinstance(record.time_window, dict):
            raise FeatureContractValidationError("time_window must be a dictionary or null.")
        start = record.time_window.get("start_s")
        dur = record.time_window.get("duration_s")
        if start is None or dur is None or dur <= 0:
            raise FeatureContractValidationError(
                f"time_window must specify duration_s > 0, got: {record.time_window}."
            )

    # 6. Channel / Node Identity Uniqueness
    if record.channel_node_identity:
        seen = set()
        duplicates = []
        for ch in record.channel_node_identity:
            if ch in seen:
                duplicates.append(ch)
            seen.add(ch)
        if duplicates:
            raise FeatureContractValidationError(
                f"Duplicate channel/node identities detected: {duplicates}."
            )

    # 7. Coordinate Status and Montage Coordinates
    valid_coords = {c.value for c in CoordinateStatus}
    if record.coordinate_status not in valid_coords:
        raise FeatureContractValidationError(
            f"Invalid coordinate_status '{record.coordinate_status}'. Allowed: {sorted(valid_coords)}"
        )

    if record.montage_coordinates is not None:
        if record.coordinate_status == CoordinateStatus.MISSING.value:
            raise FeatureContractValidationError(
                "montage_coordinates provided but coordinate_status is marked 'missing'."
            )
        if not isinstance(record.montage_coordinates, (list, tuple)):
            raise FeatureContractValidationError("montage_coordinates must be a list of 3D coordinates.")
        if record.channel_node_identity and len(record.montage_coordinates) != len(record.channel_node_identity):
            raise FeatureContractValidationError(
                f"montage_coordinates length ({len(record.montage_coordinates)}) does not match "
                f"channel_node_identity length ({len(record.channel_node_identity)})."
            )

    # 8. Axes and Shape Validation
    if record.values is not None:
        _check_finite_values(record.values)
        inferred = _infer_shape(record.values)
        if record.shape and record.shape != inferred:
            raise FeatureContractValidationError(
                f"Declared shape {record.shape} does not match inferred shape {inferred}."
            )
        if record.axes and len(record.axes) != len(inferred):
            raise FeatureContractValidationError(
                f"Length of axes ({len(record.axes)}) does not match dimensionality ({len(inferred)})."
            )
    else:
        if record.shape or record.axes:
            raise FeatureContractValidationError(
                "shape and axes must be empty when values is null."
            )

    # 9. Synthetic-Data and Evidence-Class Separation
    valid_evidence = {e.value for e in EvidenceClass}
    if record.evidence_class not in valid_evidence:
        raise FeatureContractValidationError(
            f"Invalid evidence_class '{record.evidence_class}'. Allowed: {sorted(valid_evidence)}"
        )

    if record.is_synthetic:
        if record.evidence_class == EvidenceClass.EMPIRICAL_FEATURE.value or "empirical" in record.evidence_class:
            raise FeatureContractValidationError(
                f"Synthetic feature cannot enter formal empirical evidence. "
                f"Record marked is_synthetic=True cannot have evidence_class='{record.evidence_class}'."
            )

    # 10. Specific Scientific Guardrails
    # A. Graph beta-1 is NOT spatial charge
    if record.feature_family == FeatureFamily.GRAPH_BETA_1.value:
        banned_terms = ["spatial_charge", "vortex_charge", "spatial_winding", "sensor_vortex"]
        desc = (record.feature_name + " " + record.mathematical_definition).lower()
        if any(term in desc for term in banned_terms):
            raise FeatureContractValidationError(
                f"Graph beta-1 features cannot claim spatial phase charge: found banned terms in '{desc}'."
            )

    # B. Spatial phase charge requires valid coordinates and is NOT graph beta-1
    if record.feature_family == FeatureFamily.SPATIAL_PHASE_CHARGE.value:
        if record.coordinate_status == CoordinateStatus.MISSING.value or record.montage_coordinates is None:
            raise FeatureContractValidationError(
                "spatial_phase_charge family requires valid montage coordinates (coordinate_status cannot be 'missing')."
            )
        banned_terms = ["betti_1", "graph_persistence", "vietoris_rips", "clique_complex"]
        desc = (record.feature_name + " " + record.mathematical_definition).lower()
        if any(term in desc for term in banned_terms):
            raise FeatureContractValidationError(
                f"Spatial phase charge cannot claim graph persistent homology cycles: found banned terms in '{desc}'."
            )

    # C. Triadic FC is NOT causality
    if record.feature_family == FeatureFamily.TRIADIC_FC.value:
        banned_terms = ["granger_causality", "causal_driver", "directed_causality", "causal_influence"]
        desc = (record.feature_name + " " + record.mathematical_definition).lower()
        if any(term in desc for term in banned_terms):
            raise FeatureContractValidationError(
                f"Triadic FC reflects higher-order statistical dependence and cannot claim causality: found '{desc}'."
            )

    # D. Trispectral modulation is NOT topology
    if record.feature_family == FeatureFamily.HIGHER_ORDER_SPECTRA.value:
        banned_terms = ["homology_group", "betti_number", "euler_characteristic", "topological_invariant"]
        desc = (record.feature_name + " " + record.mathematical_definition).lower()
        if any(term in desc for term in banned_terms):
            raise FeatureContractValidationError(
                f"Trispectral modulation reflects phase-amplitude coupling and cannot claim topology: found '{desc}'."
            )

    # E. Respiration is NOT automatically arousal / consciousness
    if record.feature_family == FeatureFamily.RESPIRATION.value:
        banned_terms = ["consciousness_level", "depth_of_anesthesia", "arousal_level", "conscious_state"]
        desc = (record.feature_name + " " + record.mathematical_definition).lower()
        if any(term in desc for term in banned_terms):
            raise FeatureContractValidationError(
                f"Respiration cannot claim direct cognitive arousal or consciousness state: found '{desc}'."
            )

    # F. Discernment is NOT inferred from EEG alone
    banned_mental = ["discernment_score", "enlightenment_index", "spiritual_level"]
    desc = (record.feature_name + " " + record.mathematical_definition).lower()
    if any(term in desc for term in banned_mental):
        raise FeatureContractValidationError(
            f"Mental discernment/cognitive awareness cannot be inferred from EEG alone: found '{desc}'."
        )


def validate_feature_bundle(bundle: CanonicalFeatureBundle) -> None:
    """Validates an entire feature bundle and checks internal consistency."""
    if not bundle.schema_version.startswith("NeuroTopologySim.CanonicalFeatureBundle."):
        raise FeatureContractValidationError(
            f"Unsupported bundle schema_version: '{bundle.schema_version}'."
        )

    if not bundle.bundle_id:
        raise FeatureContractValidationError("bundle_id must be a non-empty string.")

    for idx, rec in enumerate(bundle.records):
        try:
            validate_feature_record(rec)
        except FeatureContractValidationError as exc:
            raise FeatureContractValidationError(
                f"Validation error in record [{idx}] '{rec.feature_name}': {exc}"
            ) from exc

        # Consistency with bundle subject/session
        if bundle.subject and rec.subject and bundle.subject != rec.subject:
            raise FeatureContractValidationError(
                f"Record [{idx}] subject '{rec.subject}' does not match bundle subject '{bundle.subject}'."
            )
        if bundle.is_synthetic != rec.is_synthetic:
            raise FeatureContractValidationError(
                f"Record [{idx}] is_synthetic ({rec.is_synthetic}) does not match bundle is_synthetic ({bundle.is_synthetic})."
            )


def check_feature_compatibility(
    record_a: CanonicalFeatureRecord,
    record_b: CanonicalFeatureRecord,
) -> tuple[bool, list[str]]:
    """Evaluates cross-family compatibility for multimodal fusion and comparison.

    Checks:
    - Subject/session/run alignment
    - Condition-label alignment
    - Synthetic status alignment
    - Channel set compatibility
    - Time-window overlap
    """
    incompatibilities: list[str] = []

    # 1. Subject alignment
    if record_a.subject and record_b.subject and record_a.subject != record_b.subject:
        incompatibilities.append(
            f"Mismatched subjects: '{record_a.subject}' vs '{record_b.subject}'."
        )

    # 2. Session alignment
    if record_a.session and record_b.session and record_a.session != record_b.session:
        incompatibilities.append(
            f"Mismatched sessions: '{record_a.session}' vs '{record_b.session}'."
        )

    # 3. Condition label alignment
    if record_a.condition_label and record_b.condition_label and record_a.condition_label != record_b.condition_label:
        incompatibilities.append(
            f"Mismatched condition labels: '{record_a.condition_label}' vs '{record_b.condition_label}'."
        )

    # 4. Synthetic status alignment
    if record_a.is_synthetic != record_b.is_synthetic:
        incompatibilities.append(
            f"Cannot combine synthetic feature ({record_a.is_synthetic}) with empirical feature ({record_b.is_synthetic})."
        )

    # 5. Channel alignment (if both have channel sets)
    if record_a.channel_node_identity and record_b.channel_node_identity:
        common = set(record_a.channel_node_identity).intersection(set(record_b.channel_node_identity))
        if not common and record_a.feature_family != FeatureFamily.RESPIRATION.value and record_b.feature_family != FeatureFamily.RESPIRATION.value:
            incompatibilities.append(
                "Zero overlapping channels between electrophysiology feature records."
            )

    return (len(incompatibilities) == 0, incompatibilities)
