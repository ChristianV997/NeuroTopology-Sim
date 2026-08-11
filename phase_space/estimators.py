"""Transparent estimators mapping TransitionRecordV1 -> PhaseSpaceCoordinateV1.

No black-box models, no fitted parameters, no imputation. An axis is
estimated **only** from features actually named in the record's own
`feature_names`, using the record's own `delta_summary`. Anything else
returns `insufficient_data` with the missing features listed explicitly.

The estimator reads only the transition layer. Raw EEG/fMRI pipeline output
must be converted to a `TransitionRecordV1` first -- see
`docs/phase_space_coordinates.md`.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from phase_space import normalization
from phase_space.axes import AXES, Axis, get_axis
from phase_space.coordinate import (
    ESTIMATOR_VERSION,
    PhaseSpaceCoordinateV1,
)
from phase_space.uncertainty import assign_confidence, confidence_rationale

ESTIMATOR_NAME = "delta_share_v1"

_BASE_LIMITATIONS: tuple[str, ...] = (
    "A phase-space coordinate is an operational summary of named, measurable "
    "transition features. It is not a measure of consciousness, awareness, "
    "wakefulness, anesthetic depth, contemplative attainment, or health.",
    "Derived from an existing TransitionRecordV1 only; no raw recording data "
    "were read or reprocessed by this layer.",
    "Axis membership is a convention defined in phase_space/axes.py, not a "
    "validated construct; a feature belongs to an axis because this "
    "repository grouped it there, not because that grouping is established.",
    "Sign and magnitude are descriptive only and carry no valence: neither "
    "direction indicates a better, healthier, deeper, or more conscious state.",
)

_TWO_POINT_LIMITATION = (
    "Two-point condition-summary trajectory; coordinate reflects endpoint "
    "contrast rather than continuous dynamics."
)


def _is_two_point(record: Any) -> bool:
    """True when the source trajectory has only two sampled points."""
    time_axis = getattr(record, "time_axis", None) or {}
    if time_axis.get("n_samples") == 2:
        return True
    if time_axis.get("unit") == "condition_summary":
        return True
    delta_summary = getattr(record, "delta_summary", None) or {}
    return delta_summary.get("n_timepoints") == 2


def _deltas_by_feature(record: Any) -> tuple[dict[str, float], list[float], Optional[str]]:
    """Align `delta_summary.delta_per_feature` with `feature_names`.

    Returns `(mapping, all_deltas, error_reason)`. A misaligned or missing
    delta summary is an explicit error, never silently zero-filled.
    """
    names = list(getattr(record, "feature_names", None) or [])
    delta_summary = getattr(record, "delta_summary", None) or {}
    per_feature = delta_summary.get("delta_per_feature")

    if not names:
        return {}, [], "transition record carries no feature_names"
    if per_feature is None:
        return {}, [], "transition record carries no delta_summary.delta_per_feature"
    if not isinstance(per_feature, (list, tuple)):
        return {}, [], "delta_summary.delta_per_feature is not a list"
    if len(per_feature) != len(names):
        return {}, [], (
            f"delta_summary.delta_per_feature has {len(per_feature)} entries but "
            f"feature_names has {len(names)}; refusing to guess the alignment"
        )

    mapping: dict[str, float] = {}
    all_deltas: list[float] = []
    for name, raw in zip(names, per_feature):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return {}, [], f"non-numeric delta for feature '{name}'"
        mapping[name] = value
        all_deltas.append(value)
    return mapping, all_deltas, None


def _record_identity(record: Any) -> dict[str, Any]:
    return {
        "transition_id": getattr(record, "transition_id", ""),
        "dataset_id": getattr(record, "dataset_id", None),
        "subject_id": getattr(record, "subject_id", None),
        "session_id": getattr(record, "session_id", None),
        "record_level": getattr(record, "record_level", "subject"),
        "modality": getattr(record, "modality", None),
    }


def _provenance(record: Any, axis: Axis, reason: Optional[str] = None) -> dict[str, Any]:
    prov: dict[str, Any] = {
        "source": "transitions.TransitionRecordV1",
        "source_transition_id": getattr(record, "transition_id", ""),
        "source_transition_class": getattr(record, "transition_class", None),
        "source_state": getattr(record, "source_state", None),
        "target_state": getattr(record, "target_state", None),
        "source_feature_names": list(getattr(record, "feature_names", None) or []),
        "source_artifact_paths": dict(getattr(record, "artifact_paths", None) or {}),
        "source_null_control_status": (
            getattr(record, "null_control_summary", None) or {}
        ).get("status", "not_provided"),
        "axis_features_expected": list(axis.features),
        "estimator": ESTIMATOR_NAME,
        "estimator_version": ESTIMATOR_VERSION,
    }
    if reason:
        prov["reason"] = reason
    return prov


def _insufficient(
    record: Any,
    axis: Axis,
    normalization_mode: str,
    *,
    reason: str,
    missing_features: Sequence[str],
    status: str = "insufficient_data",
) -> PhaseSpaceCoordinateV1:
    return PhaseSpaceCoordinateV1.make(
        transition_id=getattr(record, "transition_id", ""),
        axis=axis.name,
        normalization_mode=normalization_mode,
        estimator=ESTIMATOR_NAME,
        input_claim_scope=getattr(record, "claim_scope", "computational_artifact"),
        input_evidence_level=getattr(
            record, "evidence_level", "L0_computational_artifact"
        ),
        value=None,
        status=status,
        confidence="none",
        source_features=[],
        missing_features=list(missing_features),
        limitations=list(_BASE_LIMITATIONS)
        + [f"No coordinate was estimated for axis '{axis.name}': {reason}"],
        provenance=_provenance(record, axis, reason=reason),
        metadata={"axis_notes": list(axis.notes)},
        **_record_identity_without_transition(record),
    )


def _record_identity_without_transition(record: Any) -> dict[str, Any]:
    identity = _record_identity(record)
    identity.pop("transition_id", None)
    return identity


def estimate_axis(
    record: Any,
    axis: str,
    normalization_mode: str = "within_record",
) -> PhaseSpaceCoordinateV1:
    """Estimate one axis coordinate from one TransitionRecordV1.

    Fails closed: any missing, misaligned, or unnormalizable input yields an
    `insufficient_data` coordinate carrying the explicit reason and the list
    of features that would have been required.
    """
    axis_obj = get_axis(axis)

    if normalization_mode not in normalization.MODES:
        raise normalization.NormalizationError(
            f"unknown normalization mode '{normalization_mode}'; "
            f"choose one of {list(normalization.MODES)}"
        )

    mapping, all_deltas, error = _deltas_by_feature(record)
    if error is not None:
        return _insufficient(
            record, axis_obj, normalization_mode,
            reason=error, missing_features=list(axis_obj.features),
        )

    contributing_names = [f for f in axis_obj.features if f in mapping]
    if not contributing_names:
        return _insufficient(
            record, axis_obj, normalization_mode,
            reason=(
                "the transition record carries none of this axis's source "
                "features"
            ),
            missing_features=list(axis_obj.features),
        )

    contributing_deltas = [mapping[name] for name in contributing_names]
    reference_stats = (getattr(record, "metadata", None) or {}).get(
        "feature_reference_stats"
    )

    value, norm_reason = normalization.apply(
        normalization_mode,
        contributing_deltas=contributing_deltas,
        all_deltas=all_deltas,
        reference_stats=reference_stats,
        contributing_names=contributing_names,
    )

    if value is None:
        return _insufficient(
            record, axis_obj, normalization_mode,
            reason=(
                f"normalization mode '{normalization_mode}' could not produce a "
                f"value: {norm_reason}"
            ),
            missing_features=[
                f for f in axis_obj.features if f not in mapping
            ] or list(axis_obj.features),
        )

    null_control = getattr(record, "null_control_summary", None) or {}
    confidence = assign_confidence(
        status="estimated",
        n_source_features=len(contributing_names),
        null_control_summary=null_control,
        axis_max_confidence=axis_obj.max_confidence,
    )

    limitations = list(_BASE_LIMITATIONS)
    limitations.append(
        f"Axis '{axis_obj.name}' was estimated from "
        f"{len(contributing_names)} of {len(axis_obj.features)} mapped source "
        "feature(s); absent features did not contribute and were not imputed."
    )
    if normalization_mode == normalization.WITHIN_RECORD:
        limitations.append(
            "normalization_mode 'within_record' expresses the value as a signed "
            "share of this record's own total absolute feature change; it is "
            "bounded to [-1, 1] and is NOT comparable across records with "
            "different feature sets."
        )
    elif normalization_mode == normalization.RAW:
        limitations.append(
            "normalization_mode 'raw' returns an unnormalized mean in the "
            "source features' own mixed units; it is not comparable across "
            "features or datasets."
        )
    if _is_two_point(record):
        limitations.append(_TWO_POINT_LIMITATION)
    limitations.extend(axis_obj.notes)

    return PhaseSpaceCoordinateV1.make(
        transition_id=getattr(record, "transition_id", ""),
        axis=axis_obj.name,
        normalization_mode=normalization_mode,
        estimator=ESTIMATOR_NAME,
        input_claim_scope=getattr(record, "claim_scope", "computational_artifact"),
        input_evidence_level=getattr(
            record, "evidence_level", "L0_computational_artifact"
        ),
        value=float(value),
        status="estimated",
        confidence=confidence,
        source_features=list(contributing_names),
        missing_features=[f for f in axis_obj.features if f not in mapping],
        limitations=limitations,
        provenance=_provenance(record, axis_obj),
        metadata={
            "contributing_deltas": {
                name: mapping[name] for name in contributing_names
            },
            "confidence_rationale": confidence_rationale(
                status="estimated",
                n_source_features=len(contributing_names),
                null_control_summary=null_control,
                axis_max_confidence=axis_obj.max_confidence,
            ),
            "axis_description": axis_obj.description,
            "axis_notes": list(axis_obj.notes),
        },
        **_record_identity_without_transition(record),
    )


def estimate_coordinates(
    record: Any,
    axes: Optional[Sequence[str]] = None,
    normalization_mode: str = "within_record",
) -> list[PhaseSpaceCoordinateV1]:
    """Estimate every requested axis (default: all registered axes)."""
    names = list(axes) if axes is not None else list(AXES)
    return [estimate_axis(record, name, normalization_mode) for name in names]
