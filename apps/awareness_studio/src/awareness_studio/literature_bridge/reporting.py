"""Strict finite-JSON serialization for a `BridgeOutcome`.

Independently implemented for this package's own wrapper shape
(`BridgeOutcome.to_dict()`), even though `research_cycle.models.json_safe`
already sanitizes non-finite floats inside a bridged record's own
fields -- this guards the outer `preserved_state`/`reason` wrapper too.
"""
from __future__ import annotations

import json
import math
from typing import Any

from .mapping import BridgeOutcome


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


def to_finite_json(outcome: BridgeOutcome, *, indent: int = 2) -> str:
    payload = outcome.to_dict()
    _check_finite(payload)
    return json.dumps(payload, indent=indent, allow_nan=False, sort_keys=False)
