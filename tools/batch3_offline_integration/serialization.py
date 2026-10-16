"""Finite JSON helpers and deterministic checksums."""
from __future__ import annotations

import hashlib
import json
import math
from enum import Enum
from typing import Any, Optional


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def contains_nonfinite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(contains_nonfinite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_nonfinite(v) for v in value)
    return False


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    return json.dumps(json_safe(obj), indent=indent, allow_nan=False, sort_keys=True)


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(json_safe(obj), sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
