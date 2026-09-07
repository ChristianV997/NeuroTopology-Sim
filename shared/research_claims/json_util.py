"""Finite / null JSON helpers.

Audit output must be JSON-serializable with ``allow_nan=False``. Non-finite
floats are rejected rather than coerced into scientific numbers.
"""

from __future__ import annotations

import json
import math
from typing import Any


class NonFiniteJsonError(ValueError):
    """Raised when a payload contains NaN or \u00b1Inf."""


def assert_finite_or_null(value: Any, path: str = "$") -> None:
    if value is None:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NonFiniteJsonError(f"non-finite number at {path}: {value!r}")
        return
    if isinstance(value, str):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            assert_finite_or_null(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert_finite_or_null(item, f"{path}.{key}")
        return
    raise NonFiniteJsonError(f"unsupported JSON type at {path}: {type(value).__name__}")


def dumps_strict(payload: Any, *, indent: int = 2) -> str:
    assert_finite_or_null(payload)
    return json.dumps(payload, indent=indent, sort_keys=True, allow_nan=False) + "\n"


def loads_strict(text: str) -> Any:
    payload = json.loads(text)
    assert_finite_or_null(payload)
    return payload
