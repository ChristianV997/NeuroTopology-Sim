"""Small immutable-ish data helpers and finite serialization for reports."""
from __future__ import annotations

import json
import math
from typing import Any, Mapping

SCHEMA_VERSION = "NeuroTopologySim.SimulationArtifactLineage.v1"


class ArtifactContractError(ValueError):
    """Raised when a report cannot satisfy its finite JSON contract."""


def finite_value(value: Any, path: str = "$") -> Any:
    """Return JSON-safe values and reject NaN/Infinity explicitly."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ArtifactContractError(f"{path} contains non-finite value")
        return value
    if isinstance(value, (list, tuple)):
        return [finite_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        return {str(key): finite_value(item, f"{path}.{key}") for key, item in value.items()}
    raise ArtifactContractError(f"{path} contains unsupported value type {type(value).__name__}")


def dumps_finite(value: Mapping[str, Any], *, indent: int = 2) -> str:
    """Serialize a mapping with stable key ordering and no non-finite tokens."""
    return json.dumps(finite_value(value), sort_keys=True, indent=indent, allow_nan=False) + "\n"
