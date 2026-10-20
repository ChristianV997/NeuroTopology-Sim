"""Validation helpers for in-memory signal-block inputs and results."""

from __future__ import annotations

import math
import numbers
from typing import Any, Mapping, Sequence

from adapters.mne_signal_blocks.schema import (
    DEFAULT_SUPPORTED_CHANNEL_TYPES,
    BlockStatus,
    ReasonCode,
)


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return None


def inspect_array(data: Any) -> tuple[tuple[int, ...] | None, bool, list[str]]:
    """Return (shape, all_finite, reasons) without requiring NumPy when possible."""
    reasons: list[str] = []
    if data is None:
        return None, True, reasons
    try:
        import numpy as np

        arr = np.asarray(data)
        shape = tuple(int(x) for x in arr.shape)
        if arr.size == 0 or any(dim <= 0 for dim in shape):
            reasons.append(ReasonCode.EMPTY_BLOCK.value)
            return shape, True, reasons
        finite = bool(np.all(np.isfinite(arr)))
        if not finite:
            reasons.append(ReasonCode.NON_FINITE_VALUES.value)
        return shape, finite, reasons
    except ImportError:
        # Pure-Python nested lists
        if not isinstance(data, (list, tuple)) or not data:
            reasons.append(ReasonCode.EMPTY_BLOCK.value)
            return None, True, reasons
        if not isinstance(data[0], (list, tuple)):
            reasons.append(ReasonCode.SHAPE_MISMATCH.value)
            return (len(data),), True, reasons
        n_ch = len(data)
        n_samp = len(data[0]) if data[0] is not None else 0
        if n_ch <= 0 or n_samp <= 0:
            reasons.append(ReasonCode.EMPTY_BLOCK.value)
            return (n_ch, n_samp), True, reasons
        finite = True
        for row in data:
            if not isinstance(row, (list, tuple)) or len(row) != n_samp:
                reasons.append(ReasonCode.SHAPE_MISMATCH.value)
                return (n_ch, n_samp), finite, reasons
            for value in row:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    finite = False
                elif isinstance(value, float) and not math.isfinite(value):
                    finite = False
        if not finite:
            reasons.append(ReasonCode.NON_FINITE_VALUES.value)
        return (n_ch, n_samp), finite, reasons


def validate_block_fields(
    *,
    channel_names: Sequence[str] | None,
    channel_types: Sequence[str | None] | None,
    units: Sequence[str | None] | None,
    sample_rate_hz: float | None,
    data: Any,
    events: Sequence[Mapping[str, Any]] | None,
    allow_channel_types: frozenset[str] | None = None,
    reference: Any = None,
    montage_name: Any = None,
    montage_coordinates: Any = None,
    block_start_sample: Any = None,
    block_end_sample: Any = None,
    declared_data_shape: Any = None,
) -> tuple[BlockStatus, list[str], list[str]]:
    """Return status, reason_codes, warnings. Never invents missing values."""
    reasons: list[str] = []
    warnings: list[str] = []
    allowed = allow_channel_types or DEFAULT_SUPPORTED_CHANNEL_TYPES

    shape, finite, array_reasons = inspect_array(data)
    reasons.extend(array_reasons)
    if data is None and declared_data_shape is not None:
        if (
            isinstance(declared_data_shape, (list, tuple))
            and len(declared_data_shape) == 2
            and all(isinstance(dim, int) and not isinstance(dim, bool) and dim > 0 for dim in declared_data_shape)
        ):
            shape = tuple(declared_data_shape)
        else:
            reasons.append(ReasonCode.SHAPE_MISMATCH.value)

    names = _as_list(channel_names)
    types = _as_list(channel_types)
    unit_list = _as_list(units)

    if names is None or len(names) == 0:
        reasons.append(ReasonCode.AMBIGUOUS_METADATA.value)
        warnings.append("channel_names absent or empty")
    elif any(not isinstance(name, str) or not name.strip() for name in names):
        reasons.append(ReasonCode.AMBIGUOUS_METADATA.value)
        warnings.append("channel_names contains a missing or non-string name")
    if shape is not None and len(shape) != 2:
        reasons.append(ReasonCode.SHAPE_MISMATCH.value)
    if shape is not None and names is not None and len(shape) == 2 and len(names) != shape[0]:
        reasons.append(ReasonCode.CHANNEL_ORDER_MISMATCH.value)

    if unit_list is None or any(u is None or str(u).strip() == "" for u in unit_list):
        reasons.append(ReasonCode.MISSING_UNITS.value)
    elif any(
        not isinstance(unit, str)
        or unit.strip().lower() in {"unknown", "unspecified", "none", "null", "n/a"}
        for unit in unit_list
    ):
        reasons.append(ReasonCode.MISSING_UNITS.value)
    elif names is not None and len(unit_list) not in {1, len(names)}:
        reasons.append(ReasonCode.SHAPE_MISMATCH.value)
        warnings.append("units length must be 1 or equal to channel count")

    if types is not None:
        for item in types:
            if item is None or str(item).strip().lower() in {"unknown", "unspecified", "none", "null", "n/a"}:
                reasons.append(ReasonCode.AMBIGUOUS_METADATA.value)
                continue
            token = str(item).strip().lower()
            if token not in allowed:
                reasons.append(ReasonCode.UNSUPPORTED_CHANNEL_TYPE.value)
                break
        if names is not None and len(types) != len(names):
            reasons.append(ReasonCode.CHANNEL_ORDER_MISMATCH.value)
    else:
        reasons.append(ReasonCode.AMBIGUOUS_METADATA.value)
        warnings.append("channel_types absent; left unknown")

    if sample_rate_hz is not None:
        try:
            if isinstance(sample_rate_hz, bool) or not isinstance(sample_rate_hz, numbers.Real):
                raise ValueError("sample rate must be a numeric value, not a boolean or string")
            rate = float(sample_rate_hz)
            if not math.isfinite(rate) or rate <= 0:
                reasons.append(ReasonCode.AMBIGUOUS_METADATA.value)
                warnings.append("sample_rate_hz is not a finite positive number")
            else:
                sample_rate_hz = rate
        except (TypeError, ValueError, OverflowError):
            reasons.append(ReasonCode.AMBIGUOUS_METADATA.value)
            warnings.append("sample_rate_hz is not a finite positive numeric value")

    if (
        reference is None
        or not isinstance(reference, str)
        or reference.strip().lower() in {"", "unknown", "unspecified", "none", "null", "n/a"}
    ):
        reasons.append(ReasonCode.MISSING_REFERENCE.value)
    montage_name_present = (
        isinstance(montage_name, str)
        and montage_name.strip().lower() not in {"", "unknown", "unspecified", "none", "null", "n/a"}
    )
    complete_coordinates = False
    if montage_coordinates is not None:
        try:
            coordinate_rows = list(montage_coordinates)
        except TypeError:
            coordinate_rows = None
        if coordinate_rows is None or (names is not None and len(coordinate_rows) != len(names)):
            reasons.append(ReasonCode.SHAPE_MISMATCH.value)
        else:
            complete_coordinates = bool(coordinate_rows)
            for point in coordinate_rows:
                if point is None:
                    complete_coordinates = False
                    continue
                if not isinstance(point, (list, tuple)) or len(point) != 3:
                    reasons.append(ReasonCode.SHAPE_MISMATCH.value)
                    complete_coordinates = False
                    break
                try:
                    finite_point = all(
                        not isinstance(value, bool)
                        and isinstance(value, numbers.Real)
                        and math.isfinite(float(value))
                        for value in point
                    )
                except (TypeError, ValueError, OverflowError):
                    finite_point = False
                if not finite_point:
                    reasons.append(ReasonCode.NON_FINITE_VALUES.value)
                    complete_coordinates = False
                    break
    if not montage_name_present and not complete_coordinates:
        reasons.append(ReasonCode.MISSING_MONTAGE.value)

    if block_start_sample is not None or block_end_sample is not None:
        valid_bounds = (
            isinstance(block_start_sample, int)
            and not isinstance(block_start_sample, bool)
            and block_start_sample >= 0
            and isinstance(block_end_sample, int)
            and not isinstance(block_end_sample, bool)
            and block_end_sample > block_start_sample
        )
        if valid_bounds and shape is not None and len(shape) == 2:
            valid_bounds = block_end_sample - block_start_sample == shape[1]
        if not valid_bounds:
            reasons.append(ReasonCode.INVALID_SAMPLE_BOUNDS.value)

    if events is not None:
        event_list = _as_list(events)
        if event_list is None:
            reasons.append(ReasonCode.MALFORMED_INPUT.value)
            warnings.append("events must be a list or tuple of event mappings")
        else:
            for event in event_list:
                if not isinstance(event, Mapping):
                    reasons.append(ReasonCode.MALFORMED_INPUT.value)
                    warnings.append("event entries must be mappings")
                    break
                sample = event.get("sample")
                if sample is None:
                    reasons.append(ReasonCode.EVENT_ALIGNMENT_MISMATCH.value)
                    break
                if not isinstance(sample, int) or isinstance(sample, bool) or sample < 0:
                    reasons.append(ReasonCode.EVENT_ALIGNMENT_MISMATCH.value)
                    break
                if shape is not None and len(shape) == 2 and sample >= shape[1]:
                    reasons.append(ReasonCode.EVENT_ALIGNMENT_MISMATCH.value)
                    break

    hard = {
        ReasonCode.EMPTY_BLOCK.value,
        ReasonCode.SHAPE_MISMATCH.value,
        ReasonCode.NON_FINITE_VALUES.value,
        ReasonCode.CHANNEL_ORDER_MISMATCH.value,
        ReasonCode.UNSUPPORTED_CHANNEL_TYPE.value,
        ReasonCode.EVENT_ALIGNMENT_MISMATCH.value,
        ReasonCode.INVALID_SAMPLE_BOUNDS.value,
        ReasonCode.MALFORMED_INPUT.value,
    }
    soft = {
        ReasonCode.MISSING_UNITS.value,
        ReasonCode.MISSING_REFERENCE.value,
        ReasonCode.MISSING_MONTAGE.value,
        ReasonCode.AMBIGUOUS_METADATA.value,
    }
    codes = list(dict.fromkeys(reasons))
    if any(code in hard for code in codes):
        status = BlockStatus.REJECTED
    elif any(code in soft for code in codes):
        status = BlockStatus.INCONCLUSIVE
    else:
        status = BlockStatus.CONVERTED
        codes = [ReasonCode.OK.value]
    return status, codes, warnings


def validate_block(block_metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a serialized block metadata mapping."""
    if not isinstance(block_metadata, Mapping):
        return {
            "status": BlockStatus.ERROR.value,
            "reason_codes": [ReasonCode.MALFORMED_INPUT.value],
            "warnings": ["block metadata must be a mapping"],
            "scientific_pass": False,
        }
    status, codes, warnings = validate_block_fields(
        channel_names=block_metadata.get("channel_names"),
        channel_types=block_metadata.get("channel_types"),
        units=block_metadata.get("units"),
        sample_rate_hz=block_metadata.get("sample_rate_hz"),
        data=block_metadata.get("data"),
        events=block_metadata.get("events"),
        reference=block_metadata.get("reference"),
        montage_name=block_metadata.get("montage_name"),
        montage_coordinates=block_metadata.get("montage_coordinates"),
        block_start_sample=block_metadata.get("block_start_sample"),
        block_end_sample=block_metadata.get("block_end_sample"),
        declared_data_shape=block_metadata.get("data_shape"),
    )
    declared_n_channels = block_metadata.get("n_channels")
    declared_n_samples = block_metadata.get("n_samples")
    declared_shape = block_metadata.get("data_shape")
    data = block_metadata.get("data")
    observed_shape, _, _ = inspect_array(data)
    if data is None:
        shape = declared_shape
        valid_shape = (
            isinstance(shape, (list, tuple))
            and len(shape) == 2
            and all(isinstance(dim, int) and not isinstance(dim, bool) and dim > 0 for dim in shape)
        )
        if not valid_shape:
            status = BlockStatus.REJECTED
            if ReasonCode.SHAPE_MISMATCH.value not in codes:
                codes.append(ReasonCode.SHAPE_MISMATCH.value)
            warnings.append("serialized signal is omitted and data_shape is missing or invalid")
        else:
            warnings.append("signal data absent; finite-value validation was not performed")
    else:
        shape = observed_shape
        if declared_shape is not None and (
            not isinstance(declared_shape, (list, tuple))
            or tuple(declared_shape) != observed_shape
        ):
            status = BlockStatus.REJECTED
            if ReasonCode.SHAPE_MISMATCH.value not in codes:
                codes.append(ReasonCode.SHAPE_MISMATCH.value)
            warnings.append("declared data_shape does not match signal data")
    if isinstance(shape, (list, tuple)) and len(shape) == 2:
        valid_count_fields = (
            isinstance(declared_n_channels, int)
            and not isinstance(declared_n_channels, bool)
            and isinstance(declared_n_samples, int)
            and not isinstance(declared_n_samples, bool)
            and declared_n_channels == shape[0]
            and declared_n_samples == shape[1]
        )
        if not valid_count_fields:
            status = BlockStatus.REJECTED
            if ReasonCode.SHAPE_MISMATCH.value not in codes:
                codes.append(ReasonCode.SHAPE_MISMATCH.value)
            warnings.append("declared channel/sample counts are missing or inconsistent")
    elif data is not None:
        status = BlockStatus.REJECTED
        if ReasonCode.SHAPE_MISMATCH.value not in codes:
            codes.append(ReasonCode.SHAPE_MISMATCH.value)
        warnings.append("signal data does not have a valid two-dimensional shape")
    if block_metadata.get("schema_version") != "MNE.InMemorySignalBlock.v1":
        status = BlockStatus.ERROR
        codes.append(ReasonCode.MALFORMED_INPUT.value)
        warnings.append("unsupported or missing schema_version")
    declared_status = block_metadata.get("status")
    severity = {
        BlockStatus.CONVERTED.value: 0,
        BlockStatus.INCONCLUSIVE.value: 1,
        BlockStatus.REJECTED.value: 2,
        BlockStatus.ERROR.value: 3,
    }
    if not isinstance(declared_status, str) or declared_status not in severity:
        status = BlockStatus.ERROR
        codes.append(ReasonCode.MALFORMED_INPUT.value)
        warnings.append("missing or unsupported declared status")
    elif severity[declared_status] > severity[status.value]:
        # Never upgrade a producer's more restrictive state based on a
        # partial metadata re-check.
        status = BlockStatus(declared_status)
    if block_metadata.get("scientific_pass") is True:
        status = BlockStatus.ERROR
        codes.append(ReasonCode.MALFORMED_INPUT.value)
        warnings.append("scientific_pass must remain false")
    return {
        "status": status.value,
        "reason_codes": codes,
        "warnings": warnings,
        "scientific_pass": False,
    }
