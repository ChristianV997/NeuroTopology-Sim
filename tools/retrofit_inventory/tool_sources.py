"""Offline Phase 2 tool-source registry loader.

Reads ``configs/retrofit_inventory/tool_sources.yaml`` from a local
repository root. No network, no credential reads, no dataset downloads,
and no live API calls.

The YAML is the source of truth. This module only loads, fail-closed
validates required fields / allowed enums, and returns deterministic
``id``-sorted dicts. It does not import the Phase 1 scanner and does
not call ``build_inventory_snapshot``.

Entries are research classifications only. They are not scientific
evidence, license opinions, or ontology promotions.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

try:
    import yaml
except ImportError as exc:  # pragma: no cover - PyYAML is declared in requirements.txt
    raise ImportError(
        "PyYAML is required to load tool_sources.yaml "
        "(declared as 'pyyaml' in requirements.txt)"
    ) from exc

Pathish = Union[str, Path]

TOOL_SOURCES_RELATIVE = "configs/retrofit_inventory/tool_sources.yaml"

REQUIRED_KEYS: Sequence[str] = (
    "id",
    "name",
    "official_source",
    "license",
    "role",
    "integration_mode",
    "optional_dependency",
    "offline_behavior",
    "network_risk",
    "privacy_risk",
    "provenance_capability",
    "adoption_recommendation",
    "notes",
)

INTEGRATION_MODES = frozenset(
    {
        "optional_adapter",
        "external_tool_record",
        "docs_only",
        "experimental",
        "do_not_vendor",
    }
)
OFFLINE_BEHAVIORS = frozenset(
    {
        "fully_offline",
        "offline_with_local_data",
        "requires_network",
        "unknown",
    }
)
RISK_LEVELS = frozenset({"none", "low", "medium", "high"})
ADOPTION_RECOMMENDATIONS = frozenset(
    {
        "consider",
        "defer",
        "reject",
        "experimental_only",
    }
)

_STRING_KEYS = frozenset(REQUIRED_KEYS) - {"optional_dependency"}


def _as_root(repo_root: Pathish) -> Path:
    root = Path(repo_root)
    if not root.exists():
        raise FileNotFoundError(f"repo_root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"repo_root is not a directory: {root}")
    return root


def _discover_repo_root() -> Path:
    """Walk from this file and cwd until ``TOOL_SOURCES_RELATIVE`` exists."""

    anchors = (Path(__file__).resolve().parent, Path.cwd().resolve())
    seen: set[str] = set()
    for anchor in anchors:
        for candidate in (anchor, *anchor.parents):
            key = candidate.as_posix()
            if key in seen:
                continue
            seen.add(key)
            if (candidate / TOOL_SOURCES_RELATIVE).is_file():
                return candidate
    raise FileNotFoundError(
        f"could not locate {TOOL_SOURCES_RELATIVE} from package path or cwd; "
        "pass repo_root explicitly"
    )


def resolve_tool_sources_path(repo_root: Optional[Pathish] = None) -> Path:
    """Return the YAML path under ``repo_root`` (discovered when omitted)."""

    root = _as_root(repo_root) if repo_root is not None else _discover_repo_root()
    path = root / TOOL_SOURCES_RELATIVE
    if not path.is_file():
        raise FileNotFoundError(f"tool sources YAML not found: {path.as_posix()}")
    return path


def validate_tool_source_entry(entry: Mapping) -> List[str]:
    """Return error strings for one registry row (empty list means ok).

    Light, fail-closed checks for required keys and allowed enums. QA owns
    deeper validators later.
    """

    errors: List[str] = []
    if not isinstance(entry, Mapping):
        return ["entry must be a mapping"]

    for key in REQUIRED_KEYS:
        if key not in entry:
            errors.append(f"missing required field: {key}")

    for key in _STRING_KEYS:
        if key not in entry:
            continue
        value = entry[key]
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key} must be a non-empty string")

    source = entry.get("official_source")
    if isinstance(source, str) and source.strip():
        if not (source.startswith("https://") or source.startswith("http://")):
            errors.append("official_source must be an http(s) URL")

    mode = entry.get("integration_mode")
    if isinstance(mode, str) and mode and mode not in INTEGRATION_MODES:
        errors.append(
            "integration_mode must be one of: " + ", ".join(sorted(INTEGRATION_MODES))
        )

    offline = entry.get("offline_behavior")
    if isinstance(offline, str) and offline and offline not in OFFLINE_BEHAVIORS:
        errors.append(
            "offline_behavior must be one of: " + ", ".join(sorted(OFFLINE_BEHAVIORS))
        )

    for risk_key in ("network_risk", "privacy_risk"):
        risk = entry.get(risk_key)
        if isinstance(risk, str) and risk and risk not in RISK_LEVELS:
            errors.append(
                f"{risk_key} must be one of: " + ", ".join(sorted(RISK_LEVELS))
            )

    adoption = entry.get("adoption_recommendation")
    if (
        isinstance(adoption, str)
        and adoption
        and adoption not in ADOPTION_RECOMMENDATIONS
    ):
        errors.append(
            "adoption_recommendation must be one of: "
            + ", ".join(sorted(ADOPTION_RECOMMENDATIONS))
        )

    if "optional_dependency" in entry and not isinstance(
        entry["optional_dependency"], bool
    ):
        errors.append("optional_dependency must be a boolean")

    return errors


def _plain_entry(entry: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(key): value for key, value in entry.items()}


def _load_yaml_mapping(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(text)
    if payload is None:
        raise ValueError(f"tool sources YAML is empty: {path.as_posix()}")
    if not isinstance(payload, Mapping):
        raise ValueError(
            f"tool sources YAML must be a mapping with a 'tools' list: {path.as_posix()}"
        )
    return payload


def load_tool_sources(repo_root: Optional[Pathish] = None) -> List[Dict[str, Any]]:
    """Load and return tool-source dicts, sorted by ``id``.

    Raises ``ValueError`` if any row fails ``validate_tool_source_entry`` or
    if ``id`` values are duplicated. Default output has no mtime / clock
    fields.
    """

    path = resolve_tool_sources_path(repo_root)
    payload = _load_yaml_mapping(path)
    raw_tools = payload.get("tools")
    if not isinstance(raw_tools, list):
        raise ValueError(
            f"tool sources YAML 'tools' must be a list: {path.as_posix()}"
        )

    errors: List[str] = []
    entries: List[Dict[str, Any]] = []
    seen_ids: Dict[str, int] = {}
    for index, raw in enumerate(raw_tools):
        prefix = f"tools[{index}]"
        row_errors = validate_tool_source_entry(raw if isinstance(raw, Mapping) else {})
        if not isinstance(raw, Mapping):
            errors.append(f"{prefix}: entry must be a mapping")
            continue
        for message in row_errors:
            errors.append(f"{prefix}: {message}")
        if row_errors:
            continue
        entry = _plain_entry(raw)
        tool_id = entry["id"]
        if tool_id in seen_ids:
            errors.append(
                f"{prefix}: duplicate id {tool_id!r} (first at tools[{seen_ids[tool_id]}])"
            )
            continue
        seen_ids[tool_id] = index
        entries.append(entry)

    if errors:
        raise ValueError("tool sources YAML failed validation:\n" + "\n".join(errors))

    return sorted(entries, key=lambda row: row["id"])


def tool_sources_by_id(
    repo_root: Optional[Pathish] = None,
    entries: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return ``{id: entry}`` from ``entries`` or a fresh load."""

    rows = (
        [_plain_entry(item) for item in entries]
        if entries is not None
        else load_tool_sources(repo_root)
    )
    by_id: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        tool_id = row["id"]
        if tool_id in by_id:
            raise ValueError(f"duplicate tool source id: {tool_id!r}")
        by_id[tool_id] = row
    return dict(sorted(by_id.items(), key=lambda item: item[0]))


def summarize_tool_sources(
    repo_root: Optional[Pathish] = None,
    entries: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return sorted counts by adoption_recommendation and integration_mode.

    No clock fields. Intended for a later reporting phase.
    """

    rows: Sequence[Mapping[str, Any]]
    if entries is None:
        rows = load_tool_sources(repo_root)
    else:
        rows = entries
    adoption = Counter(str(row.get("adoption_recommendation", "")) for row in rows)
    modes = Counter(str(row.get("integration_mode", "")) for row in rows)
    return {
        "count": len(rows),
        "by_adoption_recommendation": {key: adoption[key] for key in sorted(adoption)},
        "by_integration_mode": {key: modes[key] for key in sorted(modes)},
    }
