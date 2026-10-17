"""Fail-closed synthetic benchmark grid plan (schema ``grid_plan_v1``).

This module plans a finite parameter grid and refuses to launch it.
It does not download data, call the network, import nuisance-scenario
generators, or mark a run completed because a config parsed.

CampaignManifest v1 (``simulation_campaign_manifest_v1``) is reused for
expanded work units only. It has no planned/blocked/running/completed/failed
field and no gate-evidence field, so those live on this wrapper. v1 is not
bumped. ``Outcome.PASS`` is a runtime process outcome and is never a gate
or a scientific status.

Config hashes are ``tools.simulation_runtime.atomic_io.compute_config_hash``.
Per-cell sample floors are ``analysis.binomial_planning.plan_sample_size``.
Gate decisions are read from ``tools.evidence_promotion_gate.schema``.
Only decisions whose names start with ``ADMISSIBLE_`` open a gate check.
Opening that check does not launch the grid and does not complete the run.
"""

from __future__ import annotations

import copy
import itertools
import math
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from analysis.binomial_planning.planner import SampleSizePlanResult, plan_sample_size
from tools.evidence_promotion_gate.schema import (
    PROMOTION_DECISIONS,
    SCHEMA_VERSION as EVIDENCE_SCHEMA_VERSION,
)
from tools.simulation_runtime.atomic_io import compute_config_hash
from tools.simulation_runtime.types import (
    CampaignManifest,
    Outcome,
    ResourcePolicy,
    WorkUnit,
)

GRID_PLAN_SCHEMA_VERSION = "grid_plan_v1"
CAMPAIGN_MANIFEST_SCHEMA_VERSION = "simulation_campaign_manifest_v1"
HOLD_STATUS = "HOLD_SYNTHETIC_ONLY"
SPLIT_ALGORITHM = "disjoint_fixed_seed_blocks"

# Closed planning labels. These name synthetic controls; they are not
# generators and they are not a claim that a null or source model has been run.
NULL_MODEL_IDS: tuple[str, ...] = (
    "synthetic_phase_shuffle",
    "synthetic_iaaft",
    "synthetic_time_reverse",
)
SOURCE_MODEL_IDS: tuple[str, ...] = (
    "synthetic_single_dipole",
    "synthetic_patch",
    "synthetic_noise_only",
)

REQUIRED_GATE_IDS: tuple[str, ...] = (
    "four_sphere_forward_model",
    "planar_geometry_winding_hodge",
    "csd",
    "phase_surrogate",
)

# Read from the evidence schema. Do not hand-maintain a second copy.
ADMISSIBLE_GATE_DECISIONS: tuple[str, ...] = tuple(
    decision for decision in PROMOTION_DECISIONS if str(decision).startswith("ADMISSIBLE_")
)

RUN_STATES: tuple[str, ...] = (
    "planned",
    "blocked",
    "running",
    "completed",
    "failed",
)
# grid_plan_v1 can emit only the first two. The other three are reserved
# vocabulary and are rejected if a caller writes them onto a document.
EMITTED_RUN_STATES: frozenset[str] = frozenset({"planned", "blocked"})

ABSOLUTE_MAX_CELLS = 4096
ABSOLUTE_MAX_TRIALS = 1_000_000

_CREATED_AT = "1970-01-01T00:00:00+00:00"
_AXIS_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUISANCE_ID = re.compile(r"^[A-Za-z0-9_.:+-]{1,200}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_CONFIG_KEYS = frozenset(
    {
        "schema_version",
        "axes",
        "null_model_ids",
        "source_model_ids",
        "master_seed",
        "calibration_seed",
        "evaluation_seed",
        "calibration_samples",
        "evaluation_samples",
        "wilson_confidence_level",
        "wilson_target_full_width",
        "wilson_design_p",
        "max_cells",
        "max_trials",
        "max_compute_units",
        "compute_units_per_trial",
        "max_evidence_age_s",
        "nuisance_scenario_id",
    }
)
_REQUIRED_CONFIG_KEYS = _CONFIG_KEYS - {"wilson_design_p", "nuisance_scenario_id"}
_AXIS_KEYS = frozenset({"name", "unit", "values", "minimum", "maximum"})
_EVIDENCE_KEYS = frozenset(
    {
        "gate_id",
        "promotion_decision",
        "artifact_sha256",
        "log_pointer",
        "verifier",
        "verified_at",
    }
)
_RUNTIME_OUTCOMES = frozenset(item.value for item in Outcome)

_PLAN_ONLY_REASON = (
    "ADMISSIBLE gate records opened the planning check. "
    "grid_plan_v1 does not launch the simulation grid and does not mark the run completed."
)
_REFUSAL_REASON = (
    "execution refused; one or more required gates are missing, not ADMISSIBLE, "
    "stale, unverified, or not a structured evidence record"
)


class GridPlanError(ValueError):
    """A config, document, or evidence object failed a closed check."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _reject(code: str, message: str) -> None:
    raise GridPlanError(code, message)


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _reject("unsupported_schema_version", f"{label} must be a mapping")
    return value


def _as_finite_number(value: Any, label: str, *, type_code: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject(type_code, f"{label} must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        _reject("non_finite_value", f"{label} must be finite")
    if isinstance(value, int):
        return int(value)
    return float(value)


def _as_positive_int(value: Any, label: str, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _reject(code, f"{label} must be a positive integer")
    if value < 1:
        _reject(code, f"{label} must be >= 1")
    return int(value)


def _as_seed(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _reject("invalid_seed", f"{label} must be a non-negative integer")
    return int(value)


def _as_positive_finite(value: Any, label: str) -> float:
    number = _as_finite_number(value, label, type_code="over_budget")
    if float(number) <= 0.0:
        _reject("over_budget", f"{label} must be > 0")
    return float(number)


def _parse_aware(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("naive timestamp")
    return parsed.astimezone(timezone.utc)


def _refuse_callback(simulation: Optional[Callable[..., Any]]) -> None:
    """Accept an optional spy callback and never call it.

    Dry-run and execution both take the callback so tests can prove the
    grid is not launched. A non-callable object is rejected before planning.
    """

    if simulation is None:
        return
    if not callable(simulation):
        _reject(
            "invalid_simulation_callback",
            "simulation callback must be callable; it is never invoked by grid_plan_v1",
        )


def _normalize_identifier_list(
    raw: Any,
    *,
    label: str,
    allowlist: Sequence[str],
    unknown_code: str,
) -> List[str]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        _reject(unknown_code, f"{label} must be a non-empty list of allowlisted ids")
    if len(raw) == 0:
        _reject(unknown_code, f"{label} must be a non-empty list of allowlisted ids")
    allowed = set(allowlist)
    seen: set[str] = set()
    out: List[str] = []
    for item in raw:
        if not isinstance(item, str) or item not in allowed:
            _reject(unknown_code, f"unknown {label} id {item!r}")
        if item in seen:
            _reject("duplicate_identifier", f"duplicate {label} id {item!r}")
        seen.add(item)
        out.append(item)
    return out


def _normalize_axes(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) == 0:
        _reject("empty_axes", "axes must be a non-empty list")
    normalized: List[Dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, axis in enumerate(raw):
        if not isinstance(axis, Mapping):
            _reject("empty_axes", f"axis {index} must be a mapping")
        extra = set(axis) - _AXIS_KEYS
        if extra:
            _reject("unknown_field", f"axis {index} has unknown fields {sorted(extra)}")
        missing = _AXIS_KEYS - set(axis)
        if missing:
            _reject("invalid_range", f"axis {index} missing fields {sorted(missing)}")
        name = axis["name"]
        unit = axis["unit"]
        if not isinstance(name, str) or not _AXIS_NAME.match(name):
            _reject("empty_axes", f"axis {index} name must be a non-empty identifier")
        if name in seen_names:
            _reject("duplicate_axis", f"duplicate axis name {name!r}")
        seen_names.add(name)
        if not isinstance(unit, str) or not unit.strip():
            _reject("invalid_range", f"axis {name!r} unit must be a non-empty string")
        values_raw = axis["values"]
        if (
            not isinstance(values_raw, Sequence)
            or isinstance(values_raw, (str, bytes))
            or len(values_raw) == 0
        ):
            _reject("empty_axes", f"axis {name!r} values must be a non-empty list")
        minimum = _as_finite_number(
            axis["minimum"], f"axis {name!r} minimum", type_code="invalid_range"
        )
        maximum = _as_finite_number(
            axis["maximum"], f"axis {name!r} maximum", type_code="invalid_range"
        )
        if float(minimum) > float(maximum):
            _reject("invalid_range", f"axis {name!r} minimum exceeds maximum")
        values: List[int | float] = []
        seen_values: List[float] = []
        for value_index, raw_value in enumerate(values_raw):
            number = _as_finite_number(
                raw_value,
                f"axis {name!r} value {value_index}",
                type_code="invalid_range",
            )
            as_float = float(number)
            if as_float < float(minimum) or as_float > float(maximum):
                _reject(
                    "invalid_range",
                    f"axis {name!r} value {number!r} is outside [{minimum}, {maximum}]",
                )
            if any(as_float == previous for previous in seen_values):
                _reject("duplicate_axis", f"axis {name!r} has a duplicate value {number!r}")
            seen_values.append(as_float)
            values.append(number)
        normalized.append(
            {
                "name": name,
                "unit": unit.strip(),
                "values": values,
                "minimum": minimum,
                "maximum": maximum,
            }
        )
    normalized.sort(key=lambda item: item["name"])
    return normalized


def _normalize_nuisance(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, str) or _NUISANCE_ID.match(raw) is None:
        _reject(
            "invalid_nuisance_scenario_id",
            "nuisance_scenario_id must be an opaque id token; it is not resolved or imported",
        )
    return raw


def _normalize_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(config, Mapping):
        _reject("unsupported_schema_version", "config must be a mapping")
    extra = set(config) - _CONFIG_KEYS
    if extra:
        _reject("unknown_field", f"unknown config fields {sorted(extra)}")
    schema_version = config.get("schema_version")
    if schema_version != GRID_PLAN_SCHEMA_VERSION:
        _reject(
            "unsupported_schema_version",
            f"unsupported schema_version {schema_version!r}; expected {GRID_PLAN_SCHEMA_VERSION!r}",
        )
    missing = _REQUIRED_CONFIG_KEYS - set(config)
    if missing:
        _reject("unknown_field", f"missing config fields {sorted(missing)}")

    axes = _normalize_axes(config["axes"])
    null_model_ids = _normalize_identifier_list(
        config["null_model_ids"],
        label="null_model",
        allowlist=NULL_MODEL_IDS,
        unknown_code="unknown_null_model",
    )
    source_model_ids = _normalize_identifier_list(
        config["source_model_ids"],
        label="source_model",
        allowlist=SOURCE_MODEL_IDS,
        unknown_code="unknown_source_model",
    )
    master_seed = _as_seed(config["master_seed"], "master_seed")
    calibration_seed = _as_seed(config["calibration_seed"], "calibration_seed")
    evaluation_seed = _as_seed(config["evaluation_seed"], "evaluation_seed")
    if len({master_seed, calibration_seed, evaluation_seed}) < 3:
        _reject(
            "invalid_seed",
            "master_seed, calibration_seed, and evaluation_seed must be pairwise distinct",
        )
    calibration_samples = _as_positive_int(
        config["calibration_samples"], "calibration_samples", "invalid_sample_count"
    )
    evaluation_samples = _as_positive_int(
        config["evaluation_samples"], "evaluation_samples", "invalid_sample_count"
    )
    confidence = _as_finite_number(
        config["wilson_confidence_level"],
        "wilson_confidence_level",
        type_code="invalid_sample_count",
    )
    if not 0.0 < float(confidence) < 1.0:
        _reject("invalid_sample_count", "wilson_confidence_level must be in (0, 1)")
    width = _as_finite_number(
        config["wilson_target_full_width"],
        "wilson_target_full_width",
        type_code="invalid_sample_count",
    )
    if not 0.0 < float(width) < 1.0:
        _reject("invalid_sample_count", "wilson_target_full_width must be in (0, 1)")
    if "wilson_design_p" in config and config["wilson_design_p"] is not None:
        design_p: Optional[float] = float(
            _as_finite_number(
                config["wilson_design_p"],
                "wilson_design_p",
                type_code="invalid_range",
            )
        )
        if not 0.0 <= design_p <= 1.0:
            _reject("invalid_range", "wilson_design_p must be in [0, 1] or null")
    else:
        design_p = None
    max_cells = _as_positive_int(config["max_cells"], "max_cells", "over_budget")
    max_trials = _as_positive_int(config["max_trials"], "max_trials", "over_budget")
    max_compute_units = _as_positive_finite(config["max_compute_units"], "max_compute_units")
    compute_units_per_trial = _as_positive_finite(
        config["compute_units_per_trial"], "compute_units_per_trial"
    )
    max_evidence_age_s = _as_positive_finite(
        config["max_evidence_age_s"], "max_evidence_age_s"
    )
    nuisance_scenario_id = _normalize_nuisance(config.get("nuisance_scenario_id"))
    return {
        "schema_version": GRID_PLAN_SCHEMA_VERSION,
        "axes": axes,
        "null_model_ids": null_model_ids,
        "source_model_ids": source_model_ids,
        "master_seed": master_seed,
        "calibration_seed": calibration_seed,
        "evaluation_seed": evaluation_seed,
        "calibration_samples": calibration_samples,
        "evaluation_samples": evaluation_samples,
        "wilson_confidence_level": float(confidence),
        "wilson_target_full_width": float(width),
        "wilson_design_p": design_p,
        "max_cells": max_cells,
        "max_trials": max_trials,
        "max_compute_units": max_compute_units,
        "compute_units_per_trial": compute_units_per_trial,
        "max_evidence_age_s": max_evidence_age_s,
        "nuisance_scenario_id": nuisance_scenario_id,
    }


def _wilson_bound(normalized: Mapping[str, Any]) -> SampleSizePlanResult:
    search_cap = min(int(normalized["max_trials"]), ABSOLUTE_MAX_TRIALS)
    try:
        result = plan_sample_size(
            float(normalized["wilson_target_full_width"]),
            design_p=normalized["wilson_design_p"],
            is_half_width=False,
            confidence_level=float(normalized["wilson_confidence_level"]),
            min_n=1,
            max_n=search_cap,
        )
    except ValueError as exc:
        _reject("invalid_sample_count", str(exc))
    if result.status != "found" or result.required_n is None:
        _reject(
            "over_budget",
            "Wilson sample-size search did not find a finite n inside max_trials "
            f"({search_cap})",
        )
    required = int(result.required_n)
    if (
        int(normalized["calibration_samples"]) < required
        or int(normalized["evaluation_samples"]) < required
    ):
        _reject(
            "invalid_sample_count",
            "calibration_samples and evaluation_samples must each be >= "
            f"Wilson required_n {required}",
        )
    return result


def _enforce_budget(normalized: Mapping[str, Any]) -> Dict[str, Any]:
    cell_count = 1
    for axis in normalized["axes"]:
        cell_count *= len(axis["values"])
    cell_count *= len(normalized["null_model_ids"]) * len(normalized["source_model_ids"])
    if cell_count > int(normalized["max_cells"]) or cell_count > ABSOLUTE_MAX_CELLS:
        _reject(
            "over_budget",
            f"cell count {cell_count} exceeds max_cells {normalized['max_cells']} "
            f"or planner ceiling {ABSOLUTE_MAX_CELLS}",
        )
    per_cell = int(normalized["calibration_samples"]) + int(normalized["evaluation_samples"])
    trial_budget = int(normalized["max_trials"])
    if per_cell > trial_budget or cell_count > trial_budget // per_cell:
        _reject(
            "over_budget",
            f"trial count {cell_count * per_cell} exceeds max_trials {normalized['max_trials']}",
        )
    trial_count = cell_count * per_cell
    if trial_count > ABSOLUTE_MAX_TRIALS:
        _reject(
            "over_budget",
            f"trial count {trial_count} exceeds planner ceiling {ABSOLUTE_MAX_TRIALS}",
        )
    compute_units = float(trial_count) * float(normalized["compute_units_per_trial"])
    if (not math.isfinite(compute_units)) or compute_units > float(normalized["max_compute_units"]):
        _reject(
            "over_budget",
            f"compute units {compute_units} exceed max_compute_units "
            f"{normalized['max_compute_units']}",
        )
    return {
        "cell_count": cell_count,
        "trial_count": trial_count,
        "compute_units": compute_units,
        "trials_per_cell": per_cell,
    }


def _hash_payload(normalized: Mapping[str, Any]) -> Dict[str, Any]:
    """Inputs that define the scientific plan. Derived cells are not included."""

    return {
        "schema_version": GRID_PLAN_SCHEMA_VERSION,
        "axes": normalized["axes"],
        "null_model_ids": list(normalized["null_model_ids"]),
        "source_model_ids": list(normalized["source_model_ids"]),
        "master_seed": normalized["master_seed"],
        "calibration_seed": normalized["calibration_seed"],
        "evaluation_seed": normalized["evaluation_seed"],
        "calibration_samples": normalized["calibration_samples"],
        "evaluation_samples": normalized["evaluation_samples"],
        "split_algorithm": SPLIT_ALGORITHM,
        "wilson_confidence_level": normalized["wilson_confidence_level"],
        "wilson_target_full_width": normalized["wilson_target_full_width"],
        "wilson_design_p": normalized["wilson_design_p"],
        "max_cells": normalized["max_cells"],
        "max_trials": normalized["max_trials"],
        "max_compute_units": normalized["max_compute_units"],
        "compute_units_per_trial": normalized["compute_units_per_trial"],
        "max_evidence_age_s": normalized["max_evidence_age_s"],
        "required_gate_ids": list(REQUIRED_GATE_IDS),
        "admissible_gate_decisions": list(ADMISSIBLE_GATE_DECISIONS),
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "nuisance_scenario_id": normalized["nuisance_scenario_id"],
    }


def _expand_cells(normalized: Mapping[str, Any]) -> List[Dict[str, Any]]:
    axes = list(normalized["axes"])
    names = [axis["name"] for axis in axes]
    value_lists = [list(axis["values"]) for axis in axes]
    cells: List[Dict[str, Any]] = []
    index = 0
    for combo in itertools.product(*value_lists):
        axis_values = {name: value for name, value in zip(names, combo)}
        for null_model_id in normalized["null_model_ids"]:
            for source_model_id in normalized["source_model_ids"]:
                cell_id = f"cell-{index:04d}"
                parameter_case = {
                    "plan_only": True,
                    "executable": False,
                    "cell_index": index,
                    "axes": axis_values,
                    "null_model_id": null_model_id,
                    "source_model_id": source_model_id,
                    "nuisance_scenario_id": normalized["nuisance_scenario_id"],
                    "calibration_samples": normalized["calibration_samples"],
                    "evaluation_samples": normalized["evaluation_samples"],
                    "calibration_seed": normalized["calibration_seed"],
                    "evaluation_seed": normalized["evaluation_seed"],
                    "split_algorithm": SPLIT_ALGORITHM,
                }
                cells.append(
                    {
                        "cell_id": cell_id,
                        "cell_index": index,
                        "parameter_case": parameter_case,
                        "null_model_id": null_model_id,
                        "source_model_id": source_model_id,
                        "nuisance_scenario_id": normalized["nuisance_scenario_id"],
                        "calibration_samples": normalized["calibration_samples"],
                        "evaluation_samples": normalized["evaluation_samples"],
                        "calibration_seed": normalized["calibration_seed"],
                        "evaluation_seed": normalized["evaluation_seed"],
                        "split": {
                            "algorithm": SPLIT_ALGORITHM,
                            "trial_identity": "(cell_index, role, trial_index)",
                            "calibration_trial_index_start": 0,
                            "calibration_trial_index_stop": normalized["calibration_samples"],
                            "evaluation_trial_index_start": 0,
                            "evaluation_trial_index_stop": normalized["evaluation_samples"],
                            "roles_are_disjoint": True,
                        },
                    }
                )
                index += 1
    return cells


def _campaign_manifest(
    normalized: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]],
    config_hash: str,
) -> CampaignManifest:
    units = [
        WorkUnit(
            unit_id=str(cell["cell_id"]),
            command=[],
            parameter_case=copy.deepcopy(dict(cell["parameter_case"])),
            expected_outputs=[],
            timeout_s=0.0,
            dependencies=[],
            estimated_disk_mb=0.0,
            estimated_memory_mb=0.0,
            retryable=False,
            max_retries=0,
        )
        for cell in cells
    ]
    return CampaignManifest(
        schema_version=CAMPAIGN_MANIFEST_SCHEMA_VERSION,
        campaign_id=f"grid-plan-v1-{config_hash[:12]}",
        created_at=_CREATED_AT,
        code_commit="not_recorded",
        configuration_hash=config_hash,
        seed=int(normalized["master_seed"]),
        units=units,
        environment={
            "data_mode": "synthetic",
            "status": HOLD_STATUS,
            "launches_simulation": False,
            "participant_data": False,
        },
        resource_policy=ResourcePolicy(
            max_workers=1,
            concurrency_cap=1,
            min_disk_free_mb=0.0,
            max_memory_mb=1.0,
            max_retries_per_unit=0,
            default_timeout_s=0.0,
        ),
    )


def _limits() -> Dict[str, Any]:
    return {
        "campaign_manifest_schema": CAMPAIGN_MANIFEST_SCHEMA_VERSION,
        "campaign_manifest_has_run_states": False,
        "campaign_manifest_has_gate_evidence": False,
        "outcome_pass_is_not_a_gate": True,
        "launches_simulation": False,
        "marks_complete_on_validation": False,
        "data_mode": "synthetic",
        "hold_status": HOLD_STATUS,
        "absolute_max_cells": ABSOLUTE_MAX_CELLS,
        "absolute_max_trials": ABSOLUTE_MAX_TRIALS,
        "artifact_sha_is_structural": True,
        "nuisance_scenarios_are_ids_only": True,
    }


def _wilson_dict(result: SampleSizePlanResult) -> Dict[str, Any]:
    return {
        "status": result.status,
        "required_n": result.required_n,
        "target_metric": result.target_metric,
        "target_threshold": result.target_threshold,
        "guarantee_type": result.guarantee_type,
        "confidence_level": result.confidence_level,
        "design_proportion": result.design_proportion,
        "achieved_metric_value": result.achieved_metric_value,
        "source": "analysis.binomial_planning.plan_sample_size",
    }


class GridPlan:
    """Serializable grid plan. Validation never sets ``run_state`` to completed."""

    def __init__(
        self,
        *,
        normalized: Mapping[str, Any],
        budget: Mapping[str, Any],
        wilson: SampleSizePlanResult,
        cells: Sequence[Mapping[str, Any]],
        manifest: CampaignManifest,
        config_hash: str,
        hash_payload: Mapping[str, Any],
        run_state: str,
        gate_check: Mapping[str, Any],
        execution: Mapping[str, Any],
        gate_evidence: Optional[List[Dict[str, Any]]],
        evidence_hash: Optional[str],
        checked_at: Optional[str],
    ) -> None:
        if run_state not in EMITTED_RUN_STATES:
            _reject("self_declared_state", f"grid_plan_v1 cannot emit run_state {run_state!r}")
        self.schema_version = GRID_PLAN_SCHEMA_VERSION
        self.status_label = HOLD_STATUS
        self.run_state = run_state
        self.config_hash = config_hash
        self.hash_payload = copy.deepcopy(dict(hash_payload))
        self.cell_count = int(budget["cell_count"])
        self.trial_count = int(budget["trial_count"])
        self.compute_units = float(budget["compute_units"])
        self.configuration = copy.deepcopy(dict(normalized))
        self.cells = copy.deepcopy(list(cells))
        self.campaign_manifest = manifest
        self.wilson = wilson
        self.gate_check = {
            "opened": bool(gate_check["opened"]),
            "blockers": list(gate_check["blockers"]),
        }
        self.execution = dict(execution)
        self.gate_evidence = gate_evidence
        self.evidence_hash = evidence_hash
        self.checked_at = checked_at
        self.limits = _limits()
        if self.execution.get("completed") is True or self.run_state == "completed":
            _reject("self_declared_state", "a validated plan is not a completed run")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status_label": self.status_label,
            "run_state": self.run_state,
            "config_hash": self.config_hash,
            "evidence_hash": self.evidence_hash,
            "checked_at": self.checked_at,
            "cell_count": self.cell_count,
            "trial_count": self.trial_count,
            "compute_units": self.compute_units,
            "hash_payload": self.hash_payload,
            "configuration": self.configuration,
            "split_plan": {
                "algorithm": SPLIT_ALGORITHM,
                "master_seed": self.configuration["master_seed"],
                "calibration_seed": self.configuration["calibration_seed"],
                "evaluation_seed": self.configuration["evaluation_seed"],
                "trial_identity": "(cell_index, role, trial_index)",
                "roles_are_disjoint": True,
            },
            "cells": self.cells,
            "campaign_manifest": self.campaign_manifest.to_dict(),
            "wilson_bound": _wilson_dict(self.wilson),
            "required_gate_ids": list(REQUIRED_GATE_IDS),
            "gate_evidence": self.gate_evidence,
            "gate_check": self.gate_check,
            "execution": self.execution,
            "limits": self.limits,
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        simulation: Optional[Callable[..., Any]] = None,
    ) -> "GridPlan":
        """Rebuild from ``configuration``. Stored cells and states are not trusted."""

        document = _require_mapping(data, "grid plan")
        if document.get("schema_version") != GRID_PLAN_SCHEMA_VERSION:
            _reject(
                "unsupported_schema_version",
                f"unsupported schema_version {document.get('schema_version')!r}",
            )
        run_state = document.get("run_state")
        if run_state not in RUN_STATES:
            _reject("self_declared_state", f"unknown run_state {run_state!r}")
        if run_state not in EMITTED_RUN_STATES:
            _reject(
                "self_declared_state",
                f"run_state {run_state!r} cannot be declared on a grid_plan_v1 document",
            )
        if "configuration" not in document:
            _reject("unknown_field", "configuration is required")
        evidence = document.get("gate_evidence")
        if evidence is None:
            plan = dry_run(document["configuration"], simulation=simulation)
        else:
            plan = execute(
                document["configuration"],
                evidence,
                simulation=simulation,
                checked_at=document.get("checked_at"),
            )
        stored_hash = document.get("config_hash")
        if stored_hash != plan.config_hash:
            _reject(
                "hash_mismatch",
                "stored config_hash does not match compute_config_hash(configuration)",
            )
        return plan


def _prepare(
    config: Mapping[str, Any],
    simulation: Optional[Callable[..., Any]],
) -> tuple[
    Dict[str, Any],
    SampleSizePlanResult,
    Dict[str, Any],
    List[Dict[str, Any]],
    CampaignManifest,
    str,
    Dict[str, Any],
]:
    _refuse_callback(simulation)
    normalized = _normalize_config(config)
    wilson = _wilson_bound(normalized)
    budget = _enforce_budget(normalized)
    payload = _hash_payload(normalized)
    config_hash = compute_config_hash(payload)
    cells = _expand_cells(normalized)
    if len(cells) != budget["cell_count"]:
        _reject("over_budget", "expanded cell count does not match the budget count")
    manifest = _campaign_manifest(normalized, cells, config_hash)
    return normalized, wilson, budget, cells, manifest, config_hash, payload


def dry_run(
    config: Mapping[str, Any],
    *,
    simulation: Optional[Callable[..., Any]] = None,
) -> GridPlan:
    """Validate and list cells. Does not read gate evidence and does not execute."""

    normalized, wilson, budget, cells, manifest, config_hash, payload = _prepare(
        config, simulation
    )
    return GridPlan(
        normalized=normalized,
        budget=budget,
        wilson=wilson,
        cells=cells,
        manifest=manifest,
        config_hash=config_hash,
        hash_payload=payload,
        run_state="planned",
        gate_check={
            "opened": False,
            "blockers": [
                {
                    "code": "not_checked",
                    "gate_id": None,
                    "message": "dry-run lists cells and does not evaluate gate evidence or execute",
                }
            ],
        },
        execution={
            "requested": False,
            "refused": False,
            "refusal_reasons": [],
            "simulation_invoked": False,
            "launched": False,
            "completed": False,
            "reason": "dry-run does not execute",
        },
        gate_evidence=None,
        evidence_hash=None,
        checked_at=None,
    )


def _blocker(code: str, message: str, gate_id: Optional[str] = None) -> Dict[str, Any]:
    return {"code": code, "gate_id": gate_id, "message": message}


def _normalize_evidence_record(
    record: Mapping[str, Any],
    *,
    checked: Optional[datetime],
    max_age_s: float,
) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    blockers: List[Dict[str, Any]] = []
    extra = set(record) - _EVIDENCE_KEYS
    gate_id = record.get("gate_id")
    if not isinstance(gate_id, str):
        blockers.append(_blocker("invalid_evidence", "gate_id must be a string", None))
        return None, blockers
    if gate_id not in REQUIRED_GATE_IDS:
        blockers.append(
            _blocker("invalid_evidence", f"unknown gate id {gate_id!r}", gate_id)
        )
        return None, blockers
    if extra:
        blockers.append(
            _blocker(
                "invalid_evidence",
                f"gate {gate_id} has unknown fields {sorted(extra)}",
                gate_id,
            )
        )
        return None, blockers
    missing = _EVIDENCE_KEYS - set(record)
    if missing:
        blockers.append(
            _blocker(
                "unverified_gate",
                f"gate {gate_id} is missing {sorted(missing)}",
                gate_id,
            )
        )
        return None, blockers

    decision = record["promotion_decision"]
    sha = record["artifact_sha256"]
    log_pointer = record["log_pointer"]
    verifier = record["verifier"]
    verified_at = record["verified_at"]
    normalized = {
        "gate_id": gate_id,
        "promotion_decision": decision if isinstance(decision, str) else None,
        "artifact_sha256": sha if isinstance(sha, str) else None,
        "log_pointer": log_pointer if isinstance(log_pointer, str) else None,
        "verifier": verifier if isinstance(verifier, str) else None,
        "verified_at": verified_at if isinstance(verified_at, str) else None,
    }

    decision_rejected = (
        not isinstance(decision, str)
        or decision in _RUNTIME_OUTCOMES
        or decision == "VERIFIED"
    )
    if decision_rejected:
        blockers.append(
            _blocker(
                "gate_not_admissible",
                f"gate {gate_id} decision {decision!r} is not an evidence-schema ADMISSIBLE decision",
                gate_id,
            )
        )
    elif decision not in ADMISSIBLE_GATE_DECISIONS:
        blockers.append(
            _blocker(
                "gate_not_admissible",
                f"gate {gate_id} decision {decision!r} does not open a gate",
                gate_id,
            )
        )
    if not isinstance(sha, str) or _SHA256.match(sha) is None:
        blockers.append(
            _blocker(
                "unverified_gate",
                f"gate {gate_id} artifact_sha256 must be 64 lowercase hex characters",
                gate_id,
            )
        )
    if not isinstance(log_pointer, str) or not log_pointer.strip():
        blockers.append(
            _blocker("unverified_gate", f"gate {gate_id} log_pointer is empty", gate_id)
        )
    if not isinstance(verifier, str) or not verifier.strip():
        blockers.append(
            _blocker("unverified_gate", f"gate {gate_id} verifier is empty", gate_id)
        )
    verified: Optional[datetime] = None
    if not isinstance(verified_at, str):
        blockers.append(
            _blocker("unverified_gate", f"gate {gate_id} verified_at is not a timestamp", gate_id)
        )
    else:
        try:
            verified = _parse_aware(verified_at)
        except ValueError:
            blockers.append(
                _blocker(
                    "unverified_gate",
                    f"gate {gate_id} verified_at must be timezone-aware ISO-8601",
                    gate_id,
                )
            )
    if checked is None or verified is None:
        if checked is None:
            blockers.append(
                _blocker(
                    "unverified_gate",
                    f"gate {gate_id} freshness cannot be checked without checked_at",
                    gate_id,
                )
            )
    else:
        age_s = (checked - verified).total_seconds()
        if age_s < 0.0:
            blockers.append(
                _blocker(
                    "unverified_gate",
                    f"gate {gate_id} verified_at is later than checked_at",
                    gate_id,
                )
            )
        elif age_s > max_age_s:
            blockers.append(
                _blocker(
                    "stale_gate",
                    f"gate {gate_id} age {age_s}s exceeds max_evidence_age_s {max_age_s}",
                    gate_id,
                )
            )
    return normalized, blockers


def _assess_evidence(
    evidence: Any,
    *,
    checked_at: Any,
    max_age_s: float,
) -> tuple[bool, Optional[List[Dict[str, Any]]], Optional[str], List[Dict[str, Any]]]:
    blockers: List[Dict[str, Any]] = []
    if isinstance(evidence, bool) or evidence is None:
        return (
            False,
            None,
            None,
            [_blocker("invalid_evidence", "a boolean or null is not gate evidence")],
        )
    records: Optional[List[Mapping[str, Any]]] = None
    if isinstance(evidence, Mapping):
        coerced: List[Mapping[str, Any]] = []
        for key, value in evidence.items():
            if isinstance(value, bool) or not isinstance(value, Mapping):
                blockers.append(
                    _blocker(
                        "invalid_evidence",
                        f"gate {key!r} value is not a structured record",
                        str(key),
                    )
                )
                continue
            record = dict(value)
            if "gate_id" in record and record["gate_id"] != key:
                blockers.append(
                    _blocker(
                        "invalid_evidence",
                        f"gate key {key!r} does not match record gate_id",
                        str(key),
                    )
                )
                continue
            record["gate_id"] = key
            coerced.append(record)
        records = coerced
    elif isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes)):
        records = []
        for item in evidence:
            if isinstance(item, bool) or not isinstance(item, Mapping):
                blockers.append(
                    _blocker("invalid_evidence", "each gate entry must be a structured record")
                )
                continue
            records.append(item)
    else:
        return (
            False,
            None,
            None,
            [_blocker("invalid_evidence", "gate evidence must be a list or mapping of records")],
        )

    checked: Optional[datetime] = None
    if not isinstance(checked_at, str):
        blockers.append(
            _blocker("unverified_gate", "checked_at must be a timezone-aware ISO-8601 timestamp")
        )
    else:
        try:
            checked = _parse_aware(checked_at)
        except ValueError:
            blockers.append(
                _blocker(
                    "unverified_gate",
                    "checked_at must be a timezone-aware ISO-8601 timestamp",
                )
            )

    by_id: Dict[str, Dict[str, Any]] = {}
    assert records is not None
    for record in records:
        normalized, record_blockers = _normalize_evidence_record(
            record, checked=checked, max_age_s=max_age_s
        )
        blockers.extend(record_blockers)
        if normalized is None:
            continue
        gate_id = str(normalized["gate_id"])
        if gate_id in by_id:
            blockers.append(_blocker("invalid_evidence", f"duplicate gate id {gate_id}", gate_id))
            continue
        by_id[gate_id] = normalized

    for gate_id in REQUIRED_GATE_IDS:
        if gate_id not in by_id:
            blockers.append(_blocker("missing_gate", f"required gate {gate_id} is missing", gate_id))

    if len(by_id) != len(REQUIRED_GATE_IDS):
        return False, None, None, blockers

    ordered = [by_id[gate_id] for gate_id in REQUIRED_GATE_IDS]
    evidence_hash = compute_config_hash({"checked_at": checked_at, "records": ordered})
    opened = not blockers
    return opened, ordered, evidence_hash, blockers


def execute(
    config: Mapping[str, Any],
    gate_evidence: Any,
    *,
    simulation: Optional[Callable[..., Any]] = None,
    checked_at: Any = None,
) -> GridPlan:
    """Refuse execution unless every required gate has a fresh ADMISSIBLE record.

    Even when the gate check opens, this function does not call ``simulation``
    and does not mark the plan completed. ``grid_plan_v1`` does not launch.
    """

    normalized, wilson, budget, cells, manifest, config_hash, payload = _prepare(
        config, simulation
    )
    opened, records, evidence_hash, blockers = _assess_evidence(
        gate_evidence,
        checked_at=checked_at,
        max_age_s=float(normalized["max_evidence_age_s"]),
    )
    if opened:
        run_state = "planned"
        execution = {
            "requested": True,
            "refused": False,
            "refusal_reasons": [],
            "simulation_invoked": False,
            "launched": False,
            "completed": False,
            "reason": _PLAN_ONLY_REASON,
        }
    else:
        run_state = "blocked"
        execution = {
            "requested": True,
            "refused": True,
            "refusal_reasons": list(blockers),
            "simulation_invoked": False,
            "launched": False,
            "completed": False,
            "reason": _REFUSAL_REASON,
        }
    return GridPlan(
        normalized=normalized,
        budget=budget,
        wilson=wilson,
        cells=cells,
        manifest=manifest,
        config_hash=config_hash,
        hash_payload=payload,
        run_state=run_state,
        gate_check={"opened": opened, "blockers": blockers},
        execution=execution,
        gate_evidence=records,
        evidence_hash=evidence_hash,
        checked_at=checked_at if isinstance(checked_at, str) else None,
    )


__all__ = [
    "ABSOLUTE_MAX_CELLS",
    "ABSOLUTE_MAX_TRIALS",
    "ADMISSIBLE_GATE_DECISIONS",
    "CAMPAIGN_MANIFEST_SCHEMA_VERSION",
    "EMITTED_RUN_STATES",
    "GRID_PLAN_SCHEMA_VERSION",
    "HOLD_STATUS",
    "NULL_MODEL_IDS",
    "REQUIRED_GATE_IDS",
    "RUN_STATES",
    "SOURCE_MODEL_IDS",
    "SPLIT_ALGORITHM",
    "GridPlan",
    "GridPlanError",
    "compute_config_hash",
    "dry_run",
    "execute",
]
