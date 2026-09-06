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

CLASSIFICATIONS = frozenset({
    "local_optional_dependency",
    "external_desktop_toolchain",
    "remote_service_mcp",
    "research_reference_only",
    "unsupported",
})
CATEGORIES = frozenset({
    "eeg_ingestion", "meg_ingestion", "streaming", "tda", "signal_filtering",
    "spike_sorting", "neural_decoding", "notebook_document_research",
    "artifact_mining", "experiment_control",
})
NETWORK_REQUIREMENTS = frozenset({"none", "optional", "required"})
MEMORY_RISKS = frozenset({"low", "medium", "high", "unknown"})
AVAILABILITY_STATES = frozenset({
    "available", "missing", "unsupported", "incompatible_version",
    "offline_blocked", "opt_in_required", "error", "reference_only", "external_only",
})
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


def _parse_tool(raw: Mapping[str, Any], index: int) -> ToolSpec:
    path = f"tools[{index}]"
    if not isinstance(raw, Mapping):
        raise CapabilityRegistryError(f"{path} must be a mapping")
    tool_id = str(_require(raw, "id", path)).strip()
    if not tool_id:
        raise CapabilityRegistryError(f"{path}.id must be non-empty")
    classification = str(_require(raw, "classification", path))
    category = str(_require(raw, "capability_category", path))
    network = str(_require(raw, "network_requirement", path))
    memory = str(_require(raw, "memory_risk", path))
    if classification not in CLASSIFICATIONS:
        raise CapabilityRegistryError(f"{path}.classification {classification!r} is invalid")
    if category not in CATEGORIES:
        raise CapabilityRegistryError(f"{path}.capability_category {category!r} is invalid")
    if network not in NETWORK_REQUIREMENTS:
        raise CapabilityRegistryError(f"{path}.network_requirement {network!r} is invalid")
    if memory not in MEMORY_RISKS:
        raise CapabilityRegistryError(f"{path}.memory_risk {memory!r} is invalid")
    also = _as_tuple(raw.get("also_categories", []), f"{path}.also_categories")
    for extra in also:
        if extra not in CATEGORIES:
            raise CapabilityRegistryError(f"{path}.also_categories contains invalid {extra!r}")
    import_name = raw.get("import_name")
    if import_name is not None:
        import_name = str(import_name)
        if not import_name:
            raise CapabilityRegistryError(f"{path}.import_name must be null or non-empty")
    minimum_version = raw.get("minimum_version")
    if minimum_version is not None:
        minimum_version = str(minimum_version)
    units = raw.get("units", {})
    shapes = raw.get("shapes", {})
    if not isinstance(units, dict) or not isinstance(shapes, dict):
        raise CapabilityRegistryError(f"{path}.units and shapes must be mappings")
    return ToolSpec(
        id=tool_id,
        display_name=str(_require(raw, "display_name", path)),
        package_name=str(_require(raw, "package_name", path)),
        import_name=import_name,
        minimum_version=minimum_version,
        classification=classification,
        capability_category=category,
        also_categories=also,
        purposes=_as_tuple(raw.get("purposes", []), f"{path}.purposes"),
        input_contract=str(_require(raw, "input_contract", path)),
        output_contract=str(_require(raw, "output_contract", path)),
        units={str(k): str(v) for k, v in units.items()},
        shapes=shapes,
        license=str(_require(raw, "license", path)),
        provenance=str(_require(raw, "provenance", path)),
        network_requirement=network,
        deterministic_offline=bool(_require(raw, "deterministic_offline", path)),
        memory_risk=memory,
        scientific_support=str(raw.get("scientific_support", "not_claimed")),
        notes=str(raw.get("notes", "")),
    )


def load_registry(path: str | Path | None = None, *, reload: bool = False) -> RegistryDocument:
    """Load and validate the YAML registry. Does not probe backends."""
    global _LOADED
    registry_path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
    if _LOADED is not None and path is None and not reload:
        return _LOADED
    if not registry_path.is_file():
        raise CapabilityRegistryError(f"registry file is missing: {registry_path}")
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    document = parse_registry_document(raw)
    if path is None:
        _LOADED = document
    return document


def parse_registry_document(raw: Any) -> RegistryDocument:
    if not isinstance(raw, Mapping):
        raise CapabilityRegistryError("registry root must be a mapping")
    schema_version = str(_require(raw, "schema_version", "root"))
    registry_id = str(_require(raw, "registry_id", "root"))
    if registry_id != REGISTRY_SCHEMA:
        raise CapabilityRegistryError(
            f"registry_id must be {REGISTRY_SCHEMA!r}, got {registry_id!r}"
        )
    defaults = raw.get("defaults", {})
    if not isinstance(defaults, Mapping):
        raise CapabilityRegistryError("defaults must be a mapping")
    if defaults.get("allow_install") is True:
        raise CapabilityRegistryError("allow_install must remain false")
    if defaults.get("silent_fallback") is True:
        raise CapabilityRegistryError("silent_fallback must remain false")
    tools_raw = _require(raw, "tools", "root")
    if not isinstance(tools_raw, list) or not tools_raw:
        raise CapabilityRegistryError("tools must be a non-empty list")
    tools: dict[str, ToolSpec] = {}
    for index, item in enumerate(tools_raw):
        spec = _parse_tool(item, index)
        if spec.id in tools:
            raise CapabilityRegistryError(f"duplicate tool id {spec.id!r}")
        tools[spec.id] = spec
    return RegistryDocument(
        schema_version=schema_version,
        registry_id=registry_id,
        description=str(raw.get("description", "")),
        defaults=dict(defaults),
        tools=tools,
    )


def list_tools(path: str | Path | None = None) -> tuple[ToolSpec, ...]:
    document = load_registry(path)
    return tuple(document.tools[key] for key in sorted(document.tools))


def get_tool(tool_id: str, path: str | Path | None = None) -> ToolSpec:
    document = load_registry(path)
    try:
        return document.tools[tool_id]
    except KeyError as exc:
        raise CapabilityRegistryError(f"unknown tool id {tool_id!r}") from exc


def parse_version(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    match = _VERSION_RE.search(str(value))
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def version_satisfies(installed: str | None, minimum: str | None) -> bool:
    if minimum is None:
        return True
    have = parse_version(installed)
    need = parse_version(minimum)
    if have is None or need is None:
        return False
    return have >= need


def _distribution_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def _module_version(module: Any) -> str | None:
    value = getattr(module, "__version__", None)
    return str(value) if value is not None else None


def _find_spec(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _import_module(name: str) -> Any:
    return importlib.import_module(name)


def probe_tool(
    tool_id: str,
    *,
    offline: bool = True,
    allow_remote: bool = False,
    registry_path: str | Path | None = None,
    import_module: Callable[[str], Any] = _import_module,
    find_spec: Callable[[str], bool] = _find_spec,
    distribution_version: Callable[[str], str | None] = _distribution_version,
) -> ProbeResult:
    """Probe one tool without installing or downloading anything."""
    spec = get_tool(tool_id, registry_path)
    cache_key = (spec.id, bool(offline), bool(allow_remote))
    if (
        registry_path is None
        and import_module is _import_module
        and find_spec is _find_spec
        and cache_key in _PROBE_CACHE
    ):
        return _PROBE_CACHE[cache_key]
    result = _probe_uncached(
        spec,
        offline=offline,
        allow_remote=allow_remote,
        import_module=import_module,
        find_spec=find_spec,
        distribution_version=distribution_version,
    )
    if registry_path is None and import_module is _import_module and find_spec is _find_spec:
        _PROBE_CACHE[cache_key] = result
    return result


def _probe_uncached(
    spec: ToolSpec,
    *,
    offline: bool,
    allow_remote: bool,
    import_module: Callable[[str], Any],
    find_spec: Callable[[str], bool],
    distribution_version: Callable[[str], str | None],
) -> ProbeResult:
    def finish(availability: str, detail: str, version: str | None = None) -> ProbeResult:
        return ProbeResult(
            tool_id=spec.id,
            availability=availability,
            classification=spec.classification,
            capability_category=spec.capability_category,
            purposes=spec.purposes,
            installed_version=version,
            minimum_version=spec.minimum_version,
            network_requirement=spec.network_requirement,
            deterministic_offline=spec.deterministic_offline,
            memory_risk=spec.memory_risk,
            scientific_support=spec.scientific_support,
            selected=False,
            detail=detail,
        )

    if spec.classification == "unsupported":
        return finish("unsupported", "classified as unsupported")
    if spec.classification == "research_reference_only":
        return finish("reference_only", "research reference only; not an admitted backend")
    if spec.classification == "external_desktop_toolchain":
        return finish("external_only", "external desktop/toolchain; not importable here")
    if spec.classification == "remote_service_mcp":
        if offline or spec.network_requirement == "required" and not allow_remote:
            return finish("opt_in_required", "remote MCP/service remains opt-in and offline-blocked")
        if not allow_remote:
            return finish("opt_in_required", "remote MCP/service requires allow_remote=true")
        return finish("opt_in_required", "remote service is opt-in; this registry does not connect")
    if spec.network_requirement == "required" and (offline or not allow_remote):
        return finish("offline_blocked", "network-required backend blocked in offline mode")
    if spec.network_requirement == "optional" and offline and not spec.deterministic_offline:
        return finish(
            "offline_blocked",
            "optional-network backend is not deterministic-offline compatible",
        )
    if spec.classification != "local_optional_dependency":
        return finish("unsupported", f"classification {spec.classification} is not locally selectable")
    if not spec.import_name:
        return finish("missing", "no import_name configured")
    root_name = spec.import_name.split(".", 1)[0]
    if not find_spec(root_name) and not find_spec(spec.import_name):
        return finish("missing", f"import {spec.import_name!r} is not installed")
    try:
        module = import_module(spec.import_name)
    except Exception as exc:
        return finish("error", f"{type(exc).__name__}: {exc}")
    version = _module_version(module) or distribution_version(spec.package_name)
    if not version_satisfies(version, spec.minimum_version):
        return finish(
            "incompatible_version",
            f"installed {version!r} does not satisfy minimum {spec.minimum_version!r}",
            version,
        )
    return finish("available", "local optional dependency is importable", version)


def probe_all(
    *,
    offline: bool = True,
    allow_remote: bool = False,
    registry_path: str | Path | None = None,
    **hooks: Any,
) -> dict[str, ProbeResult]:
    return {
        spec.id: probe_tool(
            spec.id,
            offline=offline,
            allow_remote=allow_remote,
            registry_path=registry_path,
            **hooks,
        )
        for spec in list_tools(registry_path)
    }


def tools_for_purpose(purpose: str, path: str | Path | None = None) -> tuple[ToolSpec, ...]:
    if purpose not in CATEGORIES:
        raise CapabilityRegistryError(f"unknown purpose {purpose!r}")
    return tuple(spec for spec in list_tools(path) if purpose in spec.purposes)


def select_backend(
    tool_id: str,
    *,
    purpose: str,
    offline: bool = True,
    allow_remote: bool = False,
    registry_path: str | Path | None = None,
    **hooks: Any,
) -> ProbeResult:
    """Admit one compatible tool. Never falls back to a different method."""
    spec = get_tool(tool_id, registry_path)
    if purpose not in spec.purposes:
        raise CapabilityAdmissionError(
            f"{tool_id} is not registered for purpose {purpose!r}; "
            "unavailable tools cannot silently fall back to another method"
        )
    result = probe_tool(
        tool_id,
        offline=offline,
        allow_remote=allow_remote,
        registry_path=registry_path,
        **hooks,
    )
    if result.availability not in SELECTABLE_STATES:
        raise CapabilityAdmissionError(
            f"{tool_id} is not selectable ({result.availability}: {result.detail})"
        )
    return ProbeResult(**{**result.to_dict(), "selected": True, "purposes": result.purposes})


def capability_metadata(
    *,
    offline: bool = True,
    allow_remote: bool = False,
    selected: Mapping[str, str] | None = None,
    registry_path: str | Path | None = None,
    **hooks: Any,
) -> dict[str, Any]:
    """Serializable capability state for run metadata. Does not mutate RunRecordV1."""
    probes = probe_all(
        offline=offline,
        allow_remote=allow_remote,
        registry_path=registry_path,
        **hooks,
    )
    selected_records: dict[str, dict[str, Any]] = {}
    for purpose, tool_id in dict(selected or {}).items():
        admitted = select_backend(
            tool_id,
            purpose=purpose,
            offline=offline,
            allow_remote=allow_remote,
            registry_path=registry_path,
            **hooks,
        )
        selected_records[purpose] = admitted.to_dict()
    payload = {
        "schema": "NeuroTopologySim.CapabilityState.v1",
        "registry_id": REGISTRY_SCHEMA,
        "offline": bool(offline),
        "allow_remote": bool(allow_remote),
        "allow_install": False,
        "silent_fallback": False,
        "scientific_support": "not_claimed",
        "probes": {key: probes[key].to_dict() for key in sorted(probes)},
        "selected": selected_records,
    }
    return json.loads(json.dumps(payload, sort_keys=True))


def serialize_capability_state(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def reset_registry_cache() -> None:
    """Test helper: drop loaded document and probe cache."""
    global _LOADED
    _LOADED = None
    _PROBE_CACHE.clear()


def imported_backend_modules() -> tuple[str, ...]:
    """Names this module might import during a probe. Used by import-time tests."""
    return tuple(
        spec.import_name.split(".", 1)[0]
        for spec in list_tools()
        if spec.import_name
    )
