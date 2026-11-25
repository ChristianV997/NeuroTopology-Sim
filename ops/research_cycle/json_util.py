"""Finite JSON helpers.

Prefers ``tools.streaming.memory_telemetry.json_safe`` / ``dumps``. Falls back
to a local RFC-8259 implementation if that module is missing (the catalog
probe then records NOT_AVAILABLE for the shared helper).
"""

from __future__ import annotations

import json
import math
from typing import Any

_SHARED_AVAILABLE = False
_shared_json_safe = None
_shared_dumps = None

try:
    from tools.streaming.memory_telemetry import dumps as _shared_dumps
    from tools.streaming.memory_telemetry import json_safe as _shared_json_safe

    _SHARED_AVAILABLE = True
except Exception:  # pragma: no cover - probe records unavailability
    _SHARED_AVAILABLE = False


def shared_json_helper_available() -> bool:
    return bool(_SHARED_AVAILABLE and _shared_json_safe is not None and _shared_dumps is not None)


def json_safe(value: Any) -> Any:
    """Replace non-finite floats with null. Recurse through mappings and sequences."""
    if _SHARED_AVAILABLE and _shared_json_safe is not None:
        return _shared_json_safe(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def dumps(obj: Any, *, indent: int | None = 2) -> str:
    """Serialize with ``allow_nan=False``. Shared helper when available."""
    if _SHARED_AVAILABLE and _shared_dumps is not None:
        return _shared_dumps(json_safe(obj), indent=indent)
    return json.dumps(json_safe(obj), indent=indent, sort_keys=True, allow_nan=False)


def text_has_nonfinite_tokens(text: str) -> bool:
    """True if JSON text contains NaN / Infinity tokens (RFC-8259 violations)."""
    lowered = text.replace(" ", "")
    tokens = (":NaN", ":Infinity", ":-Infinity", "[NaN", "[Infinity", "[-Infinity")
    if any(token in lowered for token in tokens):
        return True
    # Also catch quoted-free JSON dumps that emit the literals as values.
    return any(part in text.split() for part in ("NaN", "Infinity", "-Infinity"))


def load_finite_json(text: str) -> Any:
    def _reject(token: str) -> float:
        raise ValueError(f"non-finite JSON token {token!r}")

    return json.loads(text, parse_constant=_reject)
