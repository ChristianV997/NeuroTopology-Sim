"""Strict finite JSON and atomic report persistence."""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


class FiniteJSONError(ValueError):
    pass


def finite_value(value: Any, path: str = "$") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FiniteJSONError(f"{path} contains NaN or Infinity")
        return value
    if isinstance(value, (list, tuple)):
        return [finite_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        return {str(key): finite_value(item, f"{path}.{key}") for key, item in value.items()}
    raise FiniteJSONError(f"{path} contains unsupported type {type(value).__name__}")


def dumps_finite(value: Mapping[str, Any]) -> str:
    return json.dumps(finite_value(value), sort_keys=True, indent=2, allow_nan=False) + "\n"


def load_finite_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(FiniteJSONError(f"non-finite token {token}")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, FiniteJSONError) as exc:
        raise FiniteJSONError(f"invalid finite JSON {path}: {exc}") from exc


def write_atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(dumps_finite(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
