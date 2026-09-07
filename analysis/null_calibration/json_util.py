"""Finite / null JSON helpers."""

from __future__ import annotations

import json
import math
from typing import Any


class NonFiniteJsonError(ValueError):
    """Raised when a payload contains NaN or +/-Inf."""


def assert_finite_or_null(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NonFiniteJsonError(f"non-finite number at {path}: {value!r}")
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            assert_finite_or_null(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert_finite_or_null(item, f"{path}.{key}")
        return
    raise NonFiniteJsonError(f"unsupported JSON type at {path}: {type(value).__name__}")


def dumps_strict(payload: Any, *, indent: int = 2) -> str:
    assert_finite_or_null(payload)
    return json.dumps(payload, indent=indent, sort_keys=True, allow_nan=False) + "\n"


def finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number
