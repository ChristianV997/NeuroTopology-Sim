"""Strict finite JSON helpers for signal-block manifests."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping


class NonFiniteError(ValueError):
    """Raised when a payload contains NaN or Infinity."""


def _check_finite(obj: Any, path: str = "$") -> None:
    if isinstance(obj, float) and not math.isfinite(obj):
        raise NonFiniteError(f"non-finite float at {path}: {obj!r}")
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            _check_finite(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            _check_finite(value, f"{path}[{index}]")


def serialize_json(payload: Mapping[str, Any], *, indent: int | None = 2) -> str:
    _check_finite(payload)
    return json.dumps(payload, allow_nan=False, sort_keys=True, indent=indent) + "\n"


def fingerprint_mapping(payload: Mapping[str, Any]) -> str:
    text = serialize_json(payload, indent=None)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
