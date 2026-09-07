"""Null-safe finite JSON serialization utilities.

Guarantees:
- Strict rejection of NaN, Infinity, and -Infinity by default.
- Optional sanitization mapping non-finite values to null (None).
- Recursive conversion of Paths, dataclasses, and Enums into JSON primitives.
"""
from __future__ import annotations

import json
import math
from typing import Any, TextIO

from .types import sanitize_val_for_json


def contains_non_finite(data: Any) -> bool:
    """Check whether a data structure contains any NaN or Infinity floats."""
    if isinstance(data, float):
        return math.isnan(data) or math.isinf(data)
    if isinstance(data, dict):
        return any(contains_non_finite(k) or contains_non_finite(v) for k, v in data.items())
    if isinstance(data, (list, tuple, set)):
        return any(contains_non_finite(item) for item in data)
    return False


def dumps_finite_json(
    data: Any,
    indent: int | None = 2,
    replace_non_finite: bool = False,
) -> str:
    """Serialize data to a JSON string, enforcing finite values.

    Args:
        data: Object to serialize.
        indent: Indentation level.
        replace_non_finite: If True, replaces NaN and Infinity with null (None).
                            If False (default), raises ValueError on any non-finite float.

    Raises:
        ValueError: If replace_non_finite=False and any NaN or Infinity is present.
    """
    if replace_non_finite:
        clean_data = sanitize_val_for_json(data)
        return json.dumps(clean_data, indent=indent, allow_nan=False)

    if contains_non_finite(data):
        raise ValueError("JSON serialization rejected: non-finite float value detected (NaN or Infinity).")

    # Clean non-float objects (like Paths and Enums) before strict dump
    cleaned = sanitize_val_for_json(data)
    return json.dumps(cleaned, indent=indent, allow_nan=False)


def dump_finite_json(
    data: Any,
    fp: TextIO,
    indent: int | None = 2,
    replace_non_finite: bool = False,
) -> None:
    """Write finite JSON data directly to a text stream."""
    serialized = dumps_finite_json(data, indent=indent, replace_non_finite=replace_non_finite)
    fp.write(serialized)
