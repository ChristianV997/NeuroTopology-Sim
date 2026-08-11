"""ExternalToolRegistry -- load/validate/query/rank over an external tool
integration registry JSON file.

Library only; the CLI lives in `external_tools.export_registry`
(``python -m external_tools.export_registry ...``), mirroring
`benchmarks.export_registry.BenchmarkRegistry`'s split between registry
object and command-line entry point.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from external_tools.tool_record import ExternalToolRecordV1

_SCHEMA = "NeuroTopologySim.ExternalToolRegistry.v1"

# Tools excluded from --recommended-next regardless of priority: these
# integration modes/license risks/statuses are never an automatic "build
# this adapter next" candidate, only a manually-reviewed one (mission
# Phase E).
_RECOMMENDED_EXCLUDED_INTEGRATION_MODES: frozenset[str] = frozenset({"reference_only", "avoid_core"})
_RECOMMENDED_EXCLUDED_LICENSE_RISK: frozenset[str] = frozenset({"proprietary_high", "unknown_high"})
_RECOMMENDED_EXCLUDED_CURRENT_STATUS: frozenset[str] = frozenset({"blocked_pending_license_review", "blocked_proprietary"})

_PRIORITY_RANK: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "reference": 8, "avoid": 9}
_FAVORED_INTEGRATION_MODES: frozenset[str] = frozenset(
    {"metadata_import", "adapter_only", "optional_backend", "dependency"}
)


class RegistryError(ValueError):
    """Raised for registry-file-level problems (missing file, bad JSON shape, ...)."""


class ExternalToolRegistry:
    def __init__(self, tools: Optional[dict[str, ExternalToolRecordV1]] = None) -> None:
        self.tools: dict[str, ExternalToolRecordV1] = dict(tools or {})

    # ── load/save ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ExternalToolRegistry":
        path = Path(path)
        if not path.exists():
            raise RegistryError(f"registry file does not exist: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        tools = {t["tool_id"]: ExternalToolRecordV1.from_dict(t) for t in data.get("tools") or []}
        return cls(tools)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": _SCHEMA,
            "tools": [self.tools[k].to_dict() for k in sorted(self.tools)],
        }

    def save(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n", encoding="utf-8")
        return path

    # ── validation ───────────────────────────────────────────────────────

    def validate(self) -> dict[str, list[str]]:
        """Return {tool_id: [errors]} for every record that fails validation."""
        errors: dict[str, list[str]] = {}
        for tool_id, record in self.tools.items():
            record_errors = record.validate()
            if record_errors:
                errors[tool_id] = record_errors
        return errors

    # ── query ────────────────────────────────────────────────────────────

    def get(self, tool_id: str) -> ExternalToolRecordV1:
        if tool_id not in self.tools:
            raise RegistryError(f"no tool record with id '{tool_id}'")
        return self.tools[tool_id]

    def list_tools(
        self,
        *,
        priority: Optional[str] = None,
        integration_mode: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[ExternalToolRecordV1]:
        out = list(self.tools.values())
        if priority is not None:
            out = [r for r in out if r.priority == priority]
        if integration_mode is not None:
            out = [r for r in out if r.integration_mode == integration_mode]
        if category is not None:
            out = [r for r in out if r.category == category]
        return sorted(out, key=lambda r: r.tool_id)

    # ── ranking ──────────────────────────────────────────────────────────

    def recommended_next(self, *, limit: Optional[int] = None) -> list[ExternalToolRecordV1]:
        """Rank safe, high-leverage adapter candidates.

        Favors (in order): P0 over P1 over P2/P3; permissive_low license
        risk or an explicit adapter_only_recommended commercial-use status;
        an integration_mode that plugs directly into an existing artifact
        pipeline (metadata_import/adapter_only/optional_backend/dependency);
        tools that already declare artifact_outputs/feature_namespaces
        (a concrete fit with this repo's existing artifact contracts).
        Always excludes reference_only, avoid_core, proprietary_high,
        unknown_high, and blocked_pending_license_review/blocked_proprietary
        tools -- these are never an automatic "build this next" candidate.
        """
        candidates = [
            t
            for t in self.tools.values()
            if t.integration_mode not in _RECOMMENDED_EXCLUDED_INTEGRATION_MODES
            and t.license_risk not in _RECOMMENDED_EXCLUDED_LICENSE_RISK
            and t.current_status not in _RECOMMENDED_EXCLUDED_CURRENT_STATUS
        ]

        def _rank(t: ExternalToolRecordV1) -> tuple[int, int, int, int, str]:
            priority_rank = _PRIORITY_RANK.get(t.priority, 9)
            license_rank = 0 if (
                t.license_risk == "permissive_low" or t.commercial_use_status == "adapter_only_recommended"
            ) else 1
            mode_rank = 0 if t.integration_mode in _FAVORED_INTEGRATION_MODES else 1
            fit_rank = 0 if (t.artifact_outputs or t.feature_namespaces) else 1
            return (priority_rank, license_rank, mode_rank, fit_rank, t.tool_id)

        ranked = sorted(candidates, key=_rank)
        return ranked[:limit] if limit is not None else ranked
