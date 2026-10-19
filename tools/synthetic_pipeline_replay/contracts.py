"""Data models and schemas for synthetic pipeline replay and boundary conformance.

Strictly separates structural interface compatibility from scientific validity,
statistical significance, or evidence promotion. Never emits VALIDATED or claims states.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


class BoundaryStatus(str, Enum):
    """Explicit outcome status for an inter-stage artifact boundary."""
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    NOT_COMPARABLE = "not_comparable"
    MISSING_REQUIRED_FIELD = "missing_required_field"


class ReplayStatus(str, Enum):
    """Overall pipeline replay evaluation status."""
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"


def safe_json_dict(val: Any) -> Any:
    """Recursively converts structures to JSON-safe representations.

    Strictly rejects non-finite floats (NaN, +Inf, -Inf) fail-closed by raising ValueError.
    Ensures invalid non-finite values cannot be silently coerced to null.
    """
    if val is None or isinstance(val, (str, bool, int)):
        return val
    if isinstance(val, float):
        if not math.isfinite(val):
            raise ValueError(
                f"Non-finite float value '{val}' rejected by serializer contract. "
                "NaN and Inf are strictly forbidden in serialized pipeline artifacts."
            )
        return val
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, Path):
        return val.as_posix()
    if dataclasses.is_dataclass(val):
        return safe_json_dict(dataclasses.asdict(val))
    if isinstance(val, Mapping):
        return {str(k): safe_json_dict(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [safe_json_dict(x) for x in val]
    try:
        import numpy as np
        if isinstance(val, np.ndarray):
            if not np.all(np.isfinite(val)):
                raise ValueError(
                    "Non-finite float value in numpy array rejected by serializer contract. "
                    "NaN and Inf are strictly forbidden in serialized pipeline artifacts."
                )
            return val.tolist()
        if isinstance(val, np.generic):
            item = val.item()
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError(
                    f"Non-finite float value '{item}' rejected by serializer contract. "
                    "NaN and Inf are strictly forbidden in serialized pipeline artifacts."
                )
            return safe_json_dict(item)
    except ImportError:
        pass
    return str(val)


@dataclass
class StageMetadata:
    """Declared metadata and contract expectations for a pipeline stage."""
    stage_id: str
    stage_name: str
    backend: str
    backend_version: str
    schema_version: str
    config_identity: str
    required_inputs: list[str] = field(default_factory=list)
    produced_outputs: list[str] = field(default_factory=list)
    channel_ordering: list[str] = field(default_factory=list)
    expected_units: str | list[str] = ""
    sampling_rate_hz: float | None = None
    expected_shape: list[int] = field(default_factory=list)
    coordinate_status: str = "missing"
    montage_coordinates: list[list[float]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return safe_json_dict(dataclasses.asdict(self))


@dataclass
class BoundaryReport:
    """Detailed structural audit report for an artifact boundary between two stages."""
    boundary_id: str
    producer_stage_id: str
    consumer_stage_id: str
    status: str  # BoundaryStatus value
    input_artifact_ref: str
    output_artifact_ref: str
    expected_contract: dict[str, Any]
    observed_contract: dict[str, Any]
    mismatches: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return safe_json_dict(dataclasses.asdict(self))


@dataclass
class ReplayReport:
    """Comprehensive report emitted by the synthetic pipeline replay checker."""
    replay_id: str
    pipeline_name: str
    status: str  # ReplayStatus value
    timestamp_utc: str
    seed: int | None
    total_boundaries: int
    compatible_boundaries: int
    incompatible_boundaries: int
    boundaries: list[BoundaryReport] = field(default_factory=list)
    stages_executed: list[str] = field(default_factory=list)
    system_environment: dict[str, Any] = field(default_factory=dict)
    disclaimer: str = (
        "Structural replay verifies offline artifact schema, shape, unit, ordering, and timing "
        "conformance between stages. Structural compatibility is an engineering check and does "
        "not constitute scientific validity, biological validation, or evidence promotion."
    )

    def to_dict(self) -> dict[str, Any]:
        return safe_json_dict(dataclasses.asdict(self))

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)
