"""Compact machine-readable result contract for SU(2)/Skyrme experiment runs.

Visualization consumers should read this envelope, not raw solver objects.
Quantities are tagged as ``computed``, ``assumed``, or ``speculative``.
Missing values use explicit ``null`` with ``availability`` metadata — never
silently omitted as if measured.

No field in this contract is a consciousness score or clinical metric.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

EvidenceTag = Literal["computed", "assumed", "speculative", "unavailable"]
RunStatus = Literal[
    "completed",
    "converged",
    "iteration_limit",
    "line_search_stalled",
    "failed",
    "solver_unavailable",
    "invalid_config",
    "numerical_failure",
]

RESULT_SCHEMA_VERSION = "0.1.0"
UNITS_STATUS = "dimensionless_unless_noted"


@dataclass(frozen=True)
class QuantityRecord:
    """One scalar or short vector diagnostic with explicit epistemology."""

    name: str
    value: Any
    evidence: EvidenceTag
    units: str = UNITS_STATUS
    notes: str = ""
    availability: Literal["present", "null", "unavailable"] = "present"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "evidence": self.evidence,
            "units": self.units,
            "notes": self.notes,
            "availability": self.availability,
        }


def quantity(
    name: str,
    value: Any,
    *,
    evidence: EvidenceTag,
    units: str = UNITS_STATUS,
    notes: str = "",
) -> QuantityRecord:
    if value is None:
        return QuantityRecord(
            name=name,
            value=None,
            evidence=evidence if evidence == "unavailable" else evidence,
            units=units,
            notes=notes or "value not available for this run",
            availability="null" if evidence != "unavailable" else "unavailable",
        )
    return QuantityRecord(
        name=name,
        value=value,
        evidence=evidence,
        units=units,
        notes=notes,
        availability="present",
    )


def unavailable_quantity(name: str, reason: str) -> QuantityRecord:
    return QuantityRecord(
        name=name,
        value=None,
        evidence="unavailable",
        units=UNITS_STATUS,
        notes=reason,
        availability="unavailable",
    )


@dataclass
class ExperimentResultV1:
    """Viz-facing experiment / sweep result envelope."""

    result_id: str
    experiment_id: str
    mode: str
    status: RunStatus
    config: Mapping[str, Any]
    provenance: Mapping[str, Any]
    discretization: Mapping[str, Any]
    boundary_conditions: Mapping[str, Any]
    initial_condition: Mapping[str, Any]
    model_settings: Mapping[str, Any]
    solver_settings: Mapping[str, Any]
    diagnostics: list[QuantityRecord] = field(default_factory=list)
    points: list[Mapping[str, Any]] = field(default_factory=list)
    solver_backend: str = "unavailable"
    solver_api_status: str = "unavailable"
    failure_message: str | None = None
    claim_tags: Mapping[str, str] = field(
        default_factory=lambda: {
            "scientific_status": "NOT_ASSESSED",
            "convergence_claim": "NOT_ESTABLISHED",
            "evidence_class": "engineering_numerical_output",
            "consciousness_interpretation": "forbidden",
            "clinical_interpretation": "forbidden",
        }
    )
    missing_data_semantics: str = (
        "Absent or null diagnostics mean unavailable/not-computed for this run; "
        "they are not zero measurements."
    )
    schema_version: str = RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "experiment_id": self.experiment_id,
            "mode": self.mode,
            "status": self.status,
            "config": dict(self.config),
            "provenance": dict(self.provenance),
            "discretization": dict(self.discretization),
            "boundary_conditions": dict(self.boundary_conditions),
            "initial_condition": dict(self.initial_condition),
            "model_settings": dict(self.model_settings),
            "solver_settings": dict(self.solver_settings),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "points": list(self.points),
            "solver_backend": self.solver_backend,
            "solver_api_status": self.solver_api_status,
            "failure_message": self.failure_message,
            "claim_tags": dict(self.claim_tags),
            "missing_data_semantics": self.missing_data_semantics,
            "units_policy": {
                "default": UNITS_STATUS,
                "physical_unit_conversion": "not_assessed",
            },
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    def write_json(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json() + "\n", encoding="utf-8", newline="\n")
        return target


def validate_result_dict(payload: Mapping[str, Any]) -> list[str]:
    """Return a list of structural problems; empty means acceptable for consumers."""
    problems: list[str] = []
    required = [
        "schema_version",
        "result_id",
        "experiment_id",
        "mode",
        "status",
        "provenance",
        "diagnostics",
        "claim_tags",
        "missing_data_semantics",
    ]
    for key in required:
        if key not in payload:
            problems.append(f"missing key: {key}")
    if payload.get("schema_version") != RESULT_SCHEMA_VERSION:
        problems.append(
            f"schema_version mismatch: {payload.get('schema_version')!r}"
        )
    claim_tags = payload.get("claim_tags")
    if isinstance(claim_tags, Mapping):
        if claim_tags.get("consciousness_interpretation") != "forbidden":
            problems.append("consciousness_interpretation must be forbidden")
        if claim_tags.get("clinical_interpretation") != "forbidden":
            problems.append("clinical_interpretation must be forbidden")
    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, Sequence):
        for index, item in enumerate(diagnostics):
            if not isinstance(item, Mapping):
                problems.append(f"diagnostics[{index}] must be a mapping")
                continue
            for key in ("name", "value", "evidence", "availability"):
                if key not in item:
                    problems.append(f"diagnostics[{index}] missing {key}")
            evidence = item.get("evidence")
            if evidence not in {"computed", "assumed", "speculative", "unavailable"}:
                problems.append(f"diagnostics[{index}] invalid evidence={evidence!r}")
    return problems
