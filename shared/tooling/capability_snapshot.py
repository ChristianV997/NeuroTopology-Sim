"""Additive capability snapshot for run sidecars.

Calls the existing optional-backend registry. Does not install packages,
download data, mutate RunRecordV1, or treat a listed name as installed support.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
import json
import math

from shared.tooling import capability_registry as registry

SNAPSHOT_SCHEMA = "NeuroTopologySim.CapabilitySnapshot.v1"
ATTACHMENT_KEY = "capability_snapshot"
_RECORD_KEYS = (
    "tool_name",
    "availability",
    "version",
    "capability_category",
    "provenance",
    "network_requirement",
    "determinism_state",
    "shapes",
    "units",
    "memory_risk",
    "unavailability_reason",
    "classification",
    "scientific_support",
)
_ROOT_KEYS = (
    "schema",
    "registry_id",
    "offline",
    "allow_remote",
    "allow_install",
    "scientific_support",
    "tools",
)


class CapabilitySnapshotError(ValueError):
    """Malformed snapshot input or output."""


@dataclass(frozen=True)
class ToolCapabilityRecord:
    tool_name: str
    availability: str
    version: str | None
    capability_category: str
    provenance: str
    network_requirement: str
    determinism_state: str
    shapes: dict[str, Any]
    units: dict[str, str]
    memory_risk: str
    unavailability_reason: str | None
    classification: str
    scientific_support: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "availability": self.availability,
            "version": self.version,
            "capability_category": self.capability_category,
            "provenance": self.provenance,
            "network_requirement": self.network_requirement,
            "determinism_state": self.determinism_state,
            "shapes": self.shapes,
            "units": self.units,
            "memory_risk": self.memory_risk,
            "unavailability_reason": self.unavailability_reason,
            "classification": self.classification,
            "scientific_support": "not_claimed",
        }


@dataclass(frozen=True)
class RunCapabilityAttachment:
    """Typed sidecar adapter. This is not a RunRecordV1 field."""

    snapshot: dict[str, Any]
    key: str = ATTACHMENT_KEY

    def to_sidecar(self, existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(existing or {})
        if "schema_version" in payload or "run_kind" in payload:
            raise CapabilitySnapshotError(
                "refusing to write into a RunRecordV1-shaped mapping; use a sidecar"
            )
        payload[self.key] = validate_snapshot(self.snapshot)
        return json_safe(payload)


def json_safe(value: Any, path: str = "$") -> Any:
    """Reject non-finite numbers. Preserve JSON null. Sort object keys."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CapabilitySnapshotError(f"{path} is not a finite JSON number")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, tuple):
        return [json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        return {
            str(key): json_safe(item, f"{path}.{key}")
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    raise CapabilitySnapshotError(f"{path} is not JSON-serializable ({type(value).__name__})")


def validate_snapshot(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CapabilitySnapshotError("snapshot must be a mapping")
    for key in _ROOT_KEYS:
        if key not in raw:
            raise CapabilitySnapshotError(f"snapshot missing {key!r}")
    if raw["schema"] != SNAPSHOT_SCHEMA:
        raise CapabilitySnapshotError(f"unsupported snapshot schema {raw['schema']!r}")
    if raw.get("allow_install") is True:
        raise CapabilitySnapshotError("allow_install must remain false")
    if raw.get("scientific_support") != "not_claimed":
        raise CapabilitySnapshotError("scientific_support must remain not_claimed")
    tools = raw["tools"]
    if not isinstance(tools, Mapping) or not tools:
        raise CapabilitySnapshotError("snapshot.tools must be a non-empty mapping")
    cleaned: dict[str, Any] = {}
    for tool_id, record in tools.items():
        if not isinstance(tool_id, str) or not tool_id:
            raise CapabilitySnapshotError("tool ids must be non-empty strings")
        if not isinstance(record, Mapping):
            raise CapabilitySnapshotError(f"tools.{tool_id} must be a mapping")
        missing = [key for key in _RECORD_KEYS if key not in record]
        if missing:
            raise CapabilitySnapshotError(f"tools.{tool_id} missing {missing}")
        if record.get("scientific_support") != "not_claimed":
            raise CapabilitySnapshotError(
                f"tools.{tool_id} listed name is not installed support"
            )
        cleaned[tool_id] = json_safe(dict(record), f"tools.{tool_id}")
    payload = {
        "schema": SNAPSHOT_SCHEMA,
        "registry_id": raw["registry_id"],
        "offline": bool(raw["offline"]),
        "allow_remote": bool(raw["allow_remote"]),
        "allow_install": False,
        "scientific_support": "not_claimed",
        "tools": {key: cleaned[key] for key in sorted(cleaned)},
    }
    return json_safe(payload)


def _determinism_state(spec: registry.ToolSpec) -> str:
    if spec.deterministic_offline and spec.network_requirement == "none":
        return "deterministic_offline"
    if spec.deterministic_offline:
        return "deterministic_when_offline_inputs"
    return "non_deterministic"


def _record_for(spec: registry.ToolSpec, probe: registry.ProbeResult) -> ToolCapabilityRecord:
    available = probe.availability == "available"
    return ToolCapabilityRecord(
        tool_name=spec.id,
        availability=probe.availability,
        version=probe.installed_version,
        capability_category=spec.capability_category,
        provenance=spec.provenance,
        network_requirement=spec.network_requirement,
        determinism_state=_determinism_state(spec),
        shapes=dict(spec.shapes),
        units=dict(spec.units),
        memory_risk=spec.memory_risk,
        unavailability_reason=None if available else probe.detail,
        classification=spec.classification,
        scientific_support="not_claimed",
    )


def capture_snapshot(
    *,
    offline: bool = True,
    allow_remote: bool = False,
    tool_ids: Iterable[str] | None = None,
    registry_path: str | Path | None = None,
    import_module: Callable[[str], Any] | None = None,
    find_spec: Callable[[str], bool] | None = None,
    distribution_version: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Probe the existing registry and return deterministic snapshot JSON."""
    document = registry.load_registry(registry_path)
    requested = list(tool_ids) if tool_ids is not None else [spec.id for spec in registry.list_tools(registry_path)]
    if not requested:
        raise CapabilitySnapshotError("tool_ids must not be empty")
    unknown = [tool_id for tool_id in requested if tool_id not in document.tools]
    if unknown:
        raise CapabilitySnapshotError(f"unknown registry tool ids: {unknown}")
    hooks: dict[str, Any] = {"registry_path": registry_path}
    if import_module is not None:
        hooks["import_module"] = import_module
    if find_spec is not None:
        hooks["find_spec"] = find_spec
    if distribution_version is not None:
        hooks["distribution_version"] = distribution_version
    records: dict[str, dict[str, Any]] = {}
    for tool_id in requested:
        spec = registry.get_tool(tool_id, registry_path)
        probe = registry.probe_tool(
            tool_id,
            offline=offline,
            allow_remote=allow_remote,
            **hooks,
        )
        records[tool_id] = _record_for(spec, probe).to_dict()
    return validate_snapshot(
        {
            "schema": SNAPSHOT_SCHEMA,
            "registry_id": document.registry_id,
            "offline": bool(offline),
            "allow_remote": bool(allow_remote),
            "allow_install": False,
            "scientific_support": "not_claimed",
            "tools": records,
        }
    )


def serialize_snapshot(snapshot: Mapping[str, Any]) -> str:
    return json.dumps(validate_snapshot(snapshot), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def attach_capability_snapshot(
    existing_sidecar: Mapping[str, Any] | None = None,
    *,
    snapshot: Mapping[str, Any] | None = None,
    **capture_kwargs: Any,
) -> dict[str, Any]:
    """Attach a snapshot to a sidecar mapping. Does not modify RunRecordV1."""
    payload = snapshot if snapshot is not None else capture_snapshot(**capture_kwargs)
    return RunCapabilityAttachment(snapshot=dict(payload)).to_sidecar(existing_sidecar)


def local_capabilities(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    validated = validate_snapshot(snapshot)
    return tuple(
        tool_id
        for tool_id, record in validated["tools"].items()
        if record["availability"] == "available"
        and record["classification"] == "local_optional_dependency"
    )


def optional_capabilities(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    validated = validate_snapshot(snapshot)
    return tuple(
        tool_id
        for tool_id, record in validated["tools"].items()
        if record["classification"] == "local_optional_dependency"
    )


def remote_capabilities(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    validated = validate_snapshot(snapshot)
    return tuple(
        tool_id
        for tool_id, record in validated["tools"].items()
        if record["classification"] == "remote_service_mcp"
        or record["network_requirement"] == "required"
    )
