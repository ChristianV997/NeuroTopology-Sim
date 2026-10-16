"""Validation helpers for in-memory signal-block inputs and results."""

from __future__ import annotations

import math
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
) -> tuple[BlockStatus, list[str], list[str]]:
    """Return status, reason_codes, warnings. Never invents missing values."""
    reasons: list[str] = []
    warnings: list[str] = []
    allowed = allow_channel_types or DEFAULT_SUPPORTED_CHANNEL_TYPES

    shape, finite, array_reasons = inspect_array(data)
    reasons.extend(array_reasons)

    names = _as_list(channel_names)
    types = _as_list(channel_types)
    unit_list = _as_list(units)

    if names is None or len(names) == 0:
        reasons.append(ReasonCode.AMBIGUOUS_METADATA.value)
        warnings.append("channel_names absent or empty")
    if shape is not None and len(shape) != 2:
        reasons.append(ReasonCode.SHAPE_MISMATCH.value)
    if shape is not None and names is not None and len(shape) == 2 and len(names) != shape[0]:
        reasons.append(ReasonCode.CHANNEL_ORDER_MISMATCH.value)

    if unit_list is None or any(u is None or str(u).strip() == "" for u in unit_list):
        reasons.append(ReasonCode.MISSING_UNITS.value)
    elif names is not None and len(unit_list) not in {1, len(names)}:
        reasons.append(ReasonCode.SHAPE_MISMATCH.value)
        warnings.append("units length must be 1 or equal to channel count")

    if types is not None:
        for item in types:
            if item is None:
                continue
            token = str(item).strip().lower()
            if token not in allowed:
                reasons.append(ReasonCode.UNSUPPORTED_CHANNEL_TYPE.value)
                break
        if names is not None and len(types) != len(names):
            reasons.append(ReasonCode.CHANNEL_ORDER_MISMATCH.value)

    if sample_rate_hz is not None:
        try:
            rate = float(sample_rate_hz)
            if not math.isfinite(rate) or rate <= 0:
                reasons.append(ReasonCode.AMBIGUOUS_METADATA.value)
                warnings.append("sample_rate_hz is not a finite positive number")
        except (TypeError, ValueError):
            reasons.append(ReasonCode.AMBIGUOUS_METADATA.value)

    if events:
        for event in events:
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
    status, codes, warnings = validate_block_fields(
        channel_names=block_metadata.get("channel_names"),
        channel_types=block_metadata.get("channel_types"),
        units=block_metadata.get("units"),
        sample_rate_hz=block_metadata.get("sample_rate_hz"),
        data=block_metadata.get("data"),
        events=block_metadata.get("events"),
    )
    return {
        "status": status.value,
        "reason_codes": codes,
        "warnings": warnings,
        "scientific_pass": False,
    }
