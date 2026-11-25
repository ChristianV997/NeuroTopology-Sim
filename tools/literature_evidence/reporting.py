"""Strict finite-JSON serialization for records and validation results."""
from __future__ import annotations

import json
import math
from typing import Any


class NonFiniteValueError(ValueError):
    """Raised when a payload contains a NaN/Infinity value that would
    otherwise silently leak into JSON output."""


def _check_finite(obj: Any, path: str = "$") -> None:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise NonFiniteValueError(f"non-finite float at {path}: {obj!r}")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            _check_finite(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            _check_finite(value, f"{path}[{index}]")


def to_finite_json(payload: dict, *, indent: int = 2) -> str:
    _check_finite(payload)
    return json.dumps(payload, indent=indent, allow_nan=False, sort_keys=False)
