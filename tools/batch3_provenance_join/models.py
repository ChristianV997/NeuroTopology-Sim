"""Small JSON-safe report types and the repository's documented hash rules."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping


REPORT_SCHEMA_VERSION = "NeuroTopologySim.Batch3ProvenanceJoin.v1"
LEDGER_SCHEMA_VERSION = "awareness-studio-research-cycle.v1"
LEDGER_EVENT_SCHEMA_VERSION = "awareness-studio-research-cycle-event.v1"
RUN_RECORD_SCHEMA_VERSIONS = frozenset({"0.1", "1"})
INTEGRATION_MANIFEST_SCHEMA = "NTS.IntegrationArtifactManifest.v1"
SIMULATION_LINEAGE_SCHEMA = "NeuroTopologySim.SimulationArtifactLineage.v1"
SOURCE_MANIFEST_SCHEMA = "NeuroTopologySim.EmpiricalSourceManifest.v1"


@dataclass(frozen=True)
class AuditLimits:
    """Hard ceilings applied before reading or hashing any supplied content."""

    max_manifest_bytes: int = 2 * 1024 * 1024
    max_artifact_bytes: int = 64 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_files: int = 10_000

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in values.values()):
            raise ValueError("all audit limits must be positive integers")


@dataclass(frozen=True, order=True)
class Finding:
    code: str
    subject: str
    detail: str
    severity: str = "warning"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class ReferenceKey:
    """Typed identity used for contract-defined joins only.

    Equal identifier text in different record types or namespaces must not
    create a relationship by itself.
    """

    record_type: str
    namespace: str
    identifier: str


def _assert_finite(value: Any, path: str = "$") -> None:
    stack = [(value, path)]
    while stack:
        current, current_path = stack.pop()
        if isinstance(current, float) and not math.isfinite(current):
            raise ValueError(f"{current_path} contains a non-finite number")
        if isinstance(current, Mapping):
            stack.extend((item, f"{current_path}.{key}") for key, item in current.items())
        elif isinstance(current, list):
            stack.extend((item, f"{current_path}[{index}]") for index, item in enumerate(current))


def canonical_json(value: Any, *, ensure_ascii: bool = False) -> str:
    """ResearchCycleLedger.canonical_json-compatible compact serialization."""
    _assert_finite(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=ensure_ascii,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the serializer limit") from exc


def sha256_json(value: Any, *, ensure_ascii: bool = False) -> str:
    return hashlib.sha256(canonical_json(value, ensure_ascii=ensure_ascii).encode("utf-8")).hexdigest()


def run_configuration_fingerprint(value: Any) -> str:
    """Match tools.simulation_artifacts.extractor._canonical_hash exactly."""
    return sha256_json(value, ensure_ascii=True)


def simulation_report_checksum(value: Mapping[str, Any]) -> str:
    """Match tools.simulation_artifacts.models.dumps_finite (indent=2 + LF)."""
    _assert_finite(value)
    try:
        encoded = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the serializer limit") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
