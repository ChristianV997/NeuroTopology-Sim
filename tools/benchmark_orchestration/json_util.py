"""Finite JSON helpers for orchestration artifacts."""
from __future__ import annotations

import json
import math
from typing import Any, Optional


def json_safe(value: Any) -> Any:
    """Recursively convert ``value`` to a JSON-safe form (no NaN/Inf)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    """Serialize with ``allow_nan=False`` after sanitizing non-finite floats."""
    return json.dumps(json_safe(obj), indent=indent, sort_keys=True, allow_nan=False)
