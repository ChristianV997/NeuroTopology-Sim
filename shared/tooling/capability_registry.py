"""Lazy optional-backend capability registry.

This module describes and probes optional tools. It does not install packages,
download data, use credentials, open sockets, or import backends at import time.
A listed package name is not a support claim.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
import importlib
import importlib.metadata
import importlib.util
import json
import re

try:
    import yaml
except ImportError as exc:  # pragma: no cover - pyyaml is a repo dependency
    raise ImportError("capability_registry requires pyyaml") from exc

REGISTRY_SCHEMA = "NeuroTopologySim.OptionalBackends.v1"
DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "tools" / "optional_backends.yaml"
)

CLASSIFICATIONS = frozenset(
    {
        "local_optional_dependency",
        "external_desktop_toolchain",
        "remote_service_mcp",
        "research_reference_only",
        "unsupported",
    }
)
CATEGORIES = frozenset(
    {
        "eeg_ingestion",
        "meg_ingestion",
        "streaming",
        "tda",
        "signal_filtering",
        "spike_sorting",
        "neural_decoding",
        "notebook_document_research",
        "artifact_mining",
        "experiment_control",
    }
)
NETWORK_REQUIREMENTS = frozenset({"none", "optional", "required"})
MEMORY_RISKS = frozenset({"low", "medium", "high", "unknown"})
AVAILABILITY_STATES = frozenset(
    {
        "available",
        "missing",
        "unsupported",
        "incompatible_version",
        "offline_blocked",
        "opt_in_required",
        "error",
        "reference_only",
        "external_only",
    }
)
SELECTABLE_STATES = frozenset({"available"})
_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


class CapabilityRegistryError(ValueError):
    """Malformed registry or illegal admission request."""


class CapabilityAdmissionError(RuntimeError):
    """A tool was requested that is not admissible under current policy."""


@dataclass(frozen=True)
class ToolSpec:
    id: str
    display_name: str
    package_name: str
    import_name: str | None
    minimum_version: str | None
    classification: str
    capability_category: str
    also_categories: tuple[str, ...]
    purposes: tuple[str, ...]
    input_contract: str
    output_contract: str
    units: dict[str, str]
    shapes: dict[str, list[Any]]
    license: str
    provenance: str
    network_requirement: str
    deterministic_offline: bool
    memory_risk: str
    scientific_support: str
    notes: str

    @property
    def categories(self) -> tuple[str, ...]:
        return (self.capability_category, *self.also_categories)


@dataclass(frozen=True)
class ProbeResult:
    tool_id: str
    availability: str
    classification: str
    capability_category: str
    purposes: tuple[str, ...]
    installed_version: str | None
    minimum_version: str | None
    network_requirement: str
    deterministic_offline: bool
    memory_risk: str
    scientific_support: str
    selected: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["purposes"] = list(self.purposes)
        return payload


@dataclass
class RegistryDocument:
    schema_version: str
    registry_id: str
    description: str
    defaults: dict[str, Any]
    tools: dict[str, ToolSpec] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "registry_id": self.registry_id,
            "defaults": dict(self.defaults),
            "tool_ids": sorted(self.tools),
        }


_LOADED: RegistryDocument | None = None
_PROBE_CACHE: dict[tuple[str, bool, bool], ProbeResult] = {}


def _require(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise CapabilityRegistryError(f"{path} missing required field {key!r}")
    return mapping[key]


def _as_tuple(value: Any, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise CapabilityRegistryError(f"{path} must be a list of strings")
    return tuple(value)
