"""Finite JSON helpers and deterministic checksums."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Optional


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    return json.dumps(json_safe(obj), indent=indent, allow_nan=False, sort_keys=True)


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(json_safe(obj), sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data
