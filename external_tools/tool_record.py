"""ExternalToolRecordV1 -- a single external tool/library/platform's
integration classification.

Tracks WHICH external tools this repository has assessed and HOW each one
may be integrated (safe dependency, adapter-only target, reference-only
competitor, paid API/hardware, ...), not scientific results and not an
actual adapter implementation. See
docs/external_tool_integration_strategy.md for the full rationale.
Structural validation lives in `external_tools.validation`; the registry
store + CLI lives in `external_tools.registry` /
`external_tools.export_registry` -- this module defines only the record
shape and its serialization, mirroring
`benchmarks.dataset_registry.DatasetRecordV1`'s relationship to
`benchmarks.validation` / `benchmarks.export_registry`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from external_tools.validation import ExternalToolValidationError, slugify_tool_id, validate_tool_record

_SCHEMA_VERSION = "1"


def compute_tool_id(name: str) -> str:
    """Deterministic tool_id: a stable slug of `name`.

    Unlike `TransitionRecordV1`/`ArtifactRecordV1` (generated at pipeline
    scale, identified by a content hash), this registry's entries are a
    small, hand-curated catalog -- a human-readable, deterministic slug is
    the more useful identity than an opaque hash, while remaining just as
    tamper-checkable via `.validate()` (rule 3: tool_id must match this
    function's output for the record's `name`).
    """
    return slugify_tool_id(name)


@dataclass
class ExternalToolRecordV1:
    schema_version: str = _SCHEMA_VERSION
    tool_id: str = ""
    name: str = ""
    category: str = ""
    public_url: str = ""
    repository_url: str = ""
    documentation_url: str = ""
    license: str = ""
    license_risk: str = ""
    commercial_use_status: str = ""
    integration_mode: str = ""
    priority: str = ""
    current_status: str = ""
    supported_modalities: list[str] = field(default_factory=list)
    artifact_inputs: list[str] = field(default_factory=list)
    artifact_outputs: list[str] = field(default_factory=list)
    feature_namespaces: list[str] = field(default_factory=list)
    planned_adapter: str = ""
    allowed_uses: list[str] = field(default_factory=list)
    forbidden_uses: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(cls, *, name: str, tool_id: Optional[str] = None, **kwargs: Any) -> "ExternalToolRecordV1":
        resolved_id = tool_id or compute_tool_id(name)
        return cls(tool_id=resolved_id, name=name, **kwargs)

    def recompute_id(self) -> str:
        return compute_tool_id(self.name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_id": self.tool_id,
            "name": self.name,
            "category": self.category,
            "public_url": self.public_url,
            "repository_url": self.repository_url,
            "documentation_url": self.documentation_url,
            "license": self.license,
            "license_risk": self.license_risk,
            "commercial_use_status": self.commercial_use_status,
            "integration_mode": self.integration_mode,
            "priority": self.priority,
            "current_status": self.current_status,
            "supported_modalities": list(self.supported_modalities),
            "artifact_inputs": list(self.artifact_inputs),
            "artifact_outputs": list(self.artifact_outputs),
            "feature_namespaces": list(self.feature_namespaces),
            "planned_adapter": self.planned_adapter,
            "allowed_uses": list(self.allowed_uses),
            "forbidden_uses": list(self.forbidden_uses),
            "risks": list(self.risks),
            "limitations": list(self.limitations),
            "provenance": self.provenance,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExternalToolRecordV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            tool_id=d.get("tool_id", ""),
            name=d.get("name", ""),
            category=d.get("category", ""),
            public_url=d.get("public_url", ""),
            repository_url=d.get("repository_url", ""),
            documentation_url=d.get("documentation_url", ""),
            license=d.get("license", ""),
            license_risk=d.get("license_risk", ""),
            commercial_use_status=d.get("commercial_use_status", ""),
            integration_mode=d.get("integration_mode", ""),
            priority=d.get("priority", ""),
            current_status=d.get("current_status", ""),
            supported_modalities=list(d.get("supported_modalities") or []),
            artifact_inputs=list(d.get("artifact_inputs") or []),
            artifact_outputs=list(d.get("artifact_outputs") or []),
            feature_namespaces=list(d.get("feature_namespaces") or []),
            planned_adapter=d.get("planned_adapter", ""),
            allowed_uses=list(d.get("allowed_uses") or []),
            forbidden_uses=list(d.get("forbidden_uses") or []),
            risks=list(d.get("risks") or []),
            limitations=list(d.get("limitations") or []),
            provenance=d.get("provenance", ""),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "ExternalToolRecordV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_tool_record(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise ExternalToolValidationError("; ".join(errors))
