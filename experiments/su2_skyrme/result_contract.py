"""Result contract for SU(2)/Skyrme experiment artifacts.

Encodes units/dimensionless status, missing-data handling, failure/convergence
status, and epistemic tags (computed / assumed / speculative). Explicitly
forbids consciousness-score implications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Optional, Sequence

RESULT_SCHEMA_VERSION = "su2_skyrme.experiment.result.v1"
ALGORITHM_ID = "su2-skyrme-experiment-runner-v1"

EpistemicTag = Literal["computed", "assumed", "speculative"]
DiagnosticAvailability = Literal["available", "unavailable", "failed", "not_requested"]
RunStatus = Literal[
    "completed",
    "completed_with_unavailable_solver",
    "failed",
    "invalid_config",
    "converged",
    "iteration_limit",
    "line_search_stalled",
    "numerical_failure",
]

ALLOWED_EPISTEMIC = frozenset({"computed", "assumed", "speculative"})
ALLOWED_AVAILABILITY = frozenset({"available", "unavailable", "failed", "not_requested"})
FORBIDDEN_KEYS = frozenset(
    {
        "consciousness_score",
        "awareness_score",
        "sentience_metric",
        "phi_score",
    }
)


class ResultContractError(ValueError):
    """Raised when a result envelope violates the contract."""


@dataclass(frozen=True)
class TaggedValue:
    """Numeric or structured value with epistemic and availability metadata."""

    value: Any
    availability: DiagnosticAvailability
    epistemic_tag: EpistemicTag
    units: str = "dimensionless"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "availability": self.availability,
            "epistemic_tag": self.epistemic_tag,
            "units": self.units,
            "note": self.note,
        }


def unavailable(
    name: str,
    *,
    reason: str,
    epistemic_tag: EpistemicTag = "assumed",
    units: str = "dimensionless",
) -> TaggedValue:
    return TaggedValue(
        value=None,
        availability="unavailable",
        epistemic_tag=epistemic_tag,
        units=units,
        note=f"{name}: {reason}",
    )


def computed(
    value: Any,
    *,
    units: str = "dimensionless",
    note: str = "",
) -> TaggedValue:
    return TaggedValue(
        value=value,
        availability="available",
        epistemic_tag="computed",
        units=units,
        note=note,
    )


@dataclass
class ExperimentResult:
    """Versioned result envelope written by the experiment runner."""

    schema_version: str
    algorithm_id: str
    run_id: str
    experiment_id: str
    status: str
    provenance: dict[str, Any]
    config: dict[str, Any]
    solver_backend_requested: str
    solver_backend_resolved: str
    solver_available: bool
    convergence: dict[str, Any]
    diagnostics: dict[str, Any]
    missing_data: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    points: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    viz_handoff: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "algorithm_id": self.algorithm_id,
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "status": self.status,
            "provenance": self.provenance,
            "config": self.config,
            "solver_backend_requested": self.solver_backend_requested,
            "solver_backend_resolved": self.solver_backend_resolved,
            "solver_available": self.solver_available,
            "convergence": self.convergence,
            "diagnostics": self.diagnostics,
            "missing_data": list(self.missing_data),
            "failures": list(self.failures),
            "points": list(self.points),
            "artifacts": dict(self.artifacts),
            "viz_handoff": dict(self.viz_handoff),
            "limitations": list(self.limitations),
            "units_policy": {
                "default": "dimensionless",
                "physical_unit_conversion": "not_assessed",
                "epistemic_tag": "assumed",
            },
            "evidence_class": "engineering_numerical_output",
            "scientific_status": "NOT_ASSESSED",
            "convergence_claim": "NOT_ESTABLISHED",
            "consciousness_implication": "none",
            "consciousness_score": None,
        }
        validate_result_dict(payload)
        return payload


def _validate_tagged(name: str, raw: Mapping[str, Any]) -> None:
    if "availability" not in raw or raw["availability"] not in ALLOWED_AVAILABILITY:
        raise ResultContractError(f"{name}.availability must be one of {sorted(ALLOWED_AVAILABILITY)}")
    if "epistemic_tag" not in raw or raw["epistemic_tag"] not in ALLOWED_EPISTEMIC:
        raise ResultContractError(f"{name}.epistemic_tag must be one of {sorted(ALLOWED_EPISTEMIC)}")
    if "units" not in raw or not isinstance(raw["units"], str):
        raise ResultContractError(f"{name}.units must be a string")
    if raw["availability"] != "available" and raw.get("value") is not None:
        # Allow structured unavailable notes but not fake numeric success.
        if isinstance(raw["value"], (int, float)) and raw["value"] == raw["value"]:
            raise ResultContractError(
                f"{name}: unavailable/failed diagnostics must not carry finite numeric values"
            )


def validate_result_dict(payload: Mapping[str, Any]) -> None:
    """Validate a result envelope against the public contract."""
    if not isinstance(payload, Mapping):
        raise ResultContractError("result must be a mapping")
    if payload.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise ResultContractError(
            f"unsupported result schema_version {payload.get('schema_version')!r}"
        )
    if payload.get("algorithm_id") != ALGORITHM_ID:
        raise ResultContractError("algorithm_id mismatch")
    for key in FORBIDDEN_KEYS:
        if key in payload and payload[key] not in (None, "none"):
            raise ResultContractError(
                f"result must not imply {key}; got {payload[key]!r}"
            )
    if payload.get("consciousness_implication") != "none":
        raise ResultContractError("consciousness_implication must be 'none'")
    if "diagnostics" not in payload or not isinstance(payload["diagnostics"], Mapping):
        raise ResultContractError("diagnostics must be a mapping")
    for name, diagnostic in payload["diagnostics"].items():
        if not isinstance(diagnostic, Mapping):
            raise ResultContractError(f"diagnostics.{name} must be a mapping")
        _validate_tagged(f"diagnostics.{name}", diagnostic)
    if "convergence" not in payload or not isinstance(payload["convergence"], Mapping):
        raise ResultContractError("convergence must be a mapping")
    if "missing_data" not in payload or not isinstance(payload["missing_data"], list):
        raise ResultContractError("missing_data must be a list")
    if "failures" not in payload or not isinstance(payload["failures"], list):
        raise ResultContractError("failures must be a list")


def default_limitations(*, solver_available: bool) -> list[str]:
    limitations = [
        "This experiment runner does not implement Skyrme energy, topology charge, "
        "or evolution mathematics; it orchestrates an optional solver adapter.",
        "Outputs are engineering reproducibility artifacts, not scientific validation.",
        "No consciousness, awareness, or biological claim is implied by any diagnostic.",
        "Physical unit conversion is not assessed; quantities are treated as dimensionless "
        "unless a caller-supplied length_unit is recorded as metadata only.",
    ]
    if not solver_available:
        limitations.append(
            "Solver package field_theory.su2 was unavailable; diagnostics are labeled "
            "unavailable rather than fabricated."
        )
    return limitations


def default_viz_handoff(run_dir: str, *, status: str) -> dict[str, Any]:
    """Stable handoff payload for a separate visualization owner."""
    return {
        "owner": "visualization_contributor",
        "status": "pending_external_viz",
        "run_dir": run_dir,
        "expected_inputs": [
            "result.json",
            "provenance.json",
            "config.canonical.json",
        ],
        "notes": (
            "Visualization UI is intentionally out of scope for this experiment layer. "
            "Consume result.json diagnostics only when availability=='available'."
        ),
        "run_status": status,
        "epistemic_tag": "assumed",
    }


def build_convergence_block(
    *,
    status: str,
    termination: Optional[str],
    iterations: Optional[int],
    reason: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "termination": termination,
        "iterations": {
            "value": iterations,
            "availability": "available" if iterations is not None else "unavailable",
            "epistemic_tag": "computed" if iterations is not None else "assumed",
            "units": "count",
            "note": reason,
        },
        "first_order_stationarity": "not_established",
        "minimum_certified": False,
        "convergence_claim": "NOT_ESTABLISHED",
        "epistemic_tag": "computed" if termination is not None else "assumed",
    }
