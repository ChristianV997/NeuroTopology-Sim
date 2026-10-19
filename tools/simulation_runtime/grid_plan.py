"""Fail-closed synthetic benchmark grid plan (schema ``grid_plan_v2``).

This module plans a finite parameter grid and refuses to launch it.
It does not download data, call the network, import nuisance-scenario
generators, or mark a run completed because a config parsed.

``execute`` accepts no gate decision from the caller. Gate reports are
read only from git blobs tracked at the local main SHA, and only at a
path ``tools.evidence_promotion_gate.reporting.write_report`` uses by
default. That function requires an output path, so there is no committed
default location and every gate stays missing. Untracked files and
``record_root`` are not evidence. ``record_root`` is a test seam labeled
``TEST_FIXTURE_NOT_EVIDENCE`` and cannot make a gate admissible.

``ci_discovery`` is blocking and stays blocked: the CI lists do not
collect ``tests/simulation_runtime``. ``dmd_crouzeix`` is nonblocking.

Dependency gates record a candidate commit. An open pull request, a
local pass, or a green unrelated workflow is not evidence. A report
whose ``source_sha`` differs from the recorded pin is stale and blocked.
"""

from __future__ import annotations

import copy
import inspect
import itertools
import json
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from analysis.binomial_planning.planner import SampleSizePlanResult, plan_sample_size
from tools.evidence_promotion_gate.reporting import serialize_json, write_report
from tools.evidence_promotion_gate.schema import (
    PROMOTION_DECISIONS,
    SCHEMA_VERSION as EVIDENCE_SCHEMA_VERSION,
    PromotionResult,
)
from tools.simulation_runtime.atomic_io import compute_config_hash
from tools.simulation_runtime.types import (
    CampaignManifest,
    Outcome,
    ResourcePolicy,
    WorkUnit,
)

GRID_PLAN_SCHEMA_VERSION = "grid_plan_v2"
CAMPAIGN_MANIFEST_SCHEMA_VERSION = "simulation_campaign_manifest_v1"
HOLD_STATUS = "HOLD_SYNTHETIC_ONLY"
SPLIT_ALGORITHM = "explicit_disjoint_id_sets"
GENERATOR = "tools.simulation_runtime.grid_plan"
FAILURE_POLICY = "fail_closed_block_grid"
TOY_FIXTURE_LABEL = "TOY_FIXTURE_NOT_A_RESULT"
TEST_FIXTURE_NOT_EVIDENCE = "TEST_FIXTURE_NOT_EVIDENCE"
POWER_CLAIM = "none"
PROJECT_STATUS = "HOLD / SYNTHETIC_ONLY"
ENGINEERING_THRESHOLD_N = 100
UNDERPOWERED_DRY_RUN = "UNDERPOWERED_DRY_RUN"
ENGINEERING_THRESHOLD_MET = "ENGINEERING_THRESHOLD_MET"
ENGINEERING_MINIMUM_NOTE = "engineering minimum, not a power guarantee"
EXECUTION_MODE_SMOKE = "smoke_only"
EXECUTION_MODE_HELD = "held"
DECLARED_ESTIMATE = "DECLARED_ESTIMATE"
DECLARED_BYTES_PER_RECORD = 4096
CODE_VERSION_UNKNOWN = "UNKNOWN"
ROC_API_PR = 426
ROC_API_HEAD = "55115149c7443ca8b325dc4dbf65d6900c9fdd79"
# Names only. This module does not import that package.
ROC_API_NAMES = (
    "tpr",
    "fpr",
    "precision",
    "auc",
    "average_precision",
)
AUDITED_MAIN_SHA = "19c3203573082f8bc41f7da226b52dc20a49fdb0"
ROLES_DISJOINT_NOTE = (
    "Disjoint calibration and evaluation ids are not proof of statistical "
    "independence. Independent draws need per-seed RNG streams downstream."
)
_REPORTING_HASH_NAMES = ("report_hash", "compute_report_hash")

# Labels only. There is no evidence that phase shuffle or IAAFT randomizes
# a spatial winding statistic. These strings do not call a surrogate.
NULL_MODEL_NOTE = (
    "Null ids are labels only. There is no evidence that phase shuffle "
    "or IAAFT randomizes a spatial winding statistic."
)
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

INDEPENDENT_UNITS: tuple[str, ...] = ("simulation_seed", "subject", "recording")
SYNTHETIC_INDEPENDENT_UNIT = "simulation_seed"
NESTED_UNITS: tuple[str, ...] = ("window", "trial", "none")
INTERVAL_METHODS: tuple[str, ...] = (
    "cluster_bootstrap_over_independent_unit",
    "wilson_on_independent_unit",
)

# Blocking gates. ci_discovery cannot be opened by a promotion record.
BLOCKING_GATE_IDS: tuple[str, ...] = (
    "four_sphere_forward_model",
    "planar_geometry",
    "winding_hodge",
    "csd_full_matrix_pinned_mne",
    "phase_dispersion",
    "surrogate_null",
    "roc_metrics",
    "ci_discovery",
)
NONBLOCKING_GATE_IDS: tuple[str, ...] = ("dmd_crouzeix",)
REQUIRED_GATE_IDS: tuple[str, ...] = BLOCKING_GATE_IDS
CI_DISCOVERY_GATE_ID = "ci_discovery"
PHASE_DISPERSION_GATE_ID = "phase_dispersion"

# Candidate refs only. An open PR head is not a promotion record on main.
# #427 moved off 27d451fa; that head is not a gate pin.
REQUIRED_SOURCE_SHA: Dict[str, str] = {
    "four_sphere_forward_model": "4b04df0bed9d34e1f4de4bb920933aa84df3a724",
    "planar_geometry": "04d5af7321ff002bb88d75353e59aec73eabbf56",
    "winding_hodge": "3328dd15a995a62759c4256de944e2dd8e7c9364",
    "csd_full_matrix_pinned_mne": "24ad946c1cd6142846e19e9db8b7a5325d49ef46",
    "phase_dispersion": "42f8f9ccdb126fafaf429e7e8b20ac4e8ff5aa98",
    "surrogate_null": "f8939eec66e585d00966d433cc563d3d34ca0b11",
    "roc_metrics": ROC_API_HEAD,
}
OPEN_PR_HEADS_NOT_EVIDENCE: Dict[str, str] = {
    "426": ROC_API_HEAD,
    "427": "e64304087dba4205ee2211963a3cf40025695e9c",
}

# Audit labels for this main SHA. Not a registry, and not a substitute
# for a promotion-gate report. Only ci_discovery is unconditionally blocked.
GATE_INTEGRATION_STATE: Dict[str, str] = {
    "four_sphere_forward_model": "NOT_INTEGRATED",
    "planar_geometry": "NOT_INTEGRATED",
    "winding_hodge": "NOT_INTEGRATED",
    "csd_full_matrix_pinned_mne": "NOT_INTEGRATED",
    "phase_dispersion": "NOT_INTEGRATED",
    "surrogate_null": "NOT_INTEGRATED",
    "roc_metrics": "NOT_INTEGRATED",
    "ci_discovery": "BLOCKED",
    "dmd_crouzeix": "NONBLOCKING",
}

# Name citation only. This module does not import the ROC module.
_UNIT_AGGREGATION_NAMED = {
    "cluster_any_event_rate": {
        "named_on_pr_426": True,
        "symbol": "cluster_any_event_rate",
        "source_citation": "synthetic_forward_roc.py:194",
        "cluster_ids_parameters": ["operating_point", "compute_roc"],
    }
}

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
EMITTED_RUN_STATES: frozenset[str] = frozenset({"planned", "blocked"})

ABSOLUTE_MAX_CELLS = 4096
ABSOLUTE_MAX_TRIALS = 1_000_000
_MAX_REPORT_BYTES = 2_000_000

PLANNED_OUTPUTS: tuple[str, ...] = (
    "grid_plan_document",
    "cell_inventory",
    "gate_resolution",
    "threshold_hash",
)
FORBIDDEN_OUTPUTS: tuple[str, ...] = ("detector_roc", "auc", "roc_curve")

_CREATED_AT = "1970-01-01T00:00:00+00:00"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_AXIS_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_NUISANCE_ID = re.compile(r"^[A-Za-z0-9_.:+-]{1,200}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_LOCKED_INPUT = re.compile(r"ds005620|\bbids\b|participant|empirical", re.IGNORECASE)
_ROC_KEYS = frozenset({"auc", "roc", "fpr", "tpr", "detector_roc", "roc_curve"})
_CALLER_GATE_DECISION = object()

_CONFIG_KEYS = frozenset(
    {
        "schema_version",
        "axes",
        "null_model_ids",
        "source_model_ids",
        "master_seed",
        "calibration_seed",
        "evaluation_seed",
        "independent_unit",
        "n_independent_calibration",
        "n_positive_calibration",
        "n_negative_calibration",
        "nested_unit",
        "nested_per_unit",
        "unit_aggregation",
        "interval_method",
        "estimand",
        "power_claim",
        "h0",
        "h1",
        "score_definition_id",
        "threshold",
        "wilson_confidence_level",
        "wilson_target_full_width",
        "wilson_design_p",
        "max_cells",
        "max_trials",
        "max_compute_units",
        "compute_units_per_trial",
        "nuisance_scenario_id",
    }
)
# n_independent_evaluation is read only after the threshold hash is recorded.
# Unit id lists are derived inside the planner. Caller-supplied id lists are rejected.
_EVALUATION_KEYS = frozenset(
    {
        "n_independent_evaluation",
        "n_positive_evaluation",
        "n_negative_evaluation",
    }
)
_CALLER_UNIT_ID_KEYS = frozenset({"calibration_unit_ids", "evaluation_unit_ids"})
_OPTIONAL_CONFIG_KEYS = frozenset(
    {"wilson_design_p", "nuisance_scenario_id", "unit_aggregation"}
)
_REQUIRED_BEFORE_THRESHOLD = (_CONFIG_KEYS - _OPTIONAL_CONFIG_KEYS) - _EVALUATION_KEYS
_INPUT_KEYS = _CONFIG_KEYS | _EVALUATION_KEYS
_AXIS_KEYS = frozenset({"name", "unit", "values", "minimum", "maximum"})
_RUNTIME_OUTCOMES = frozenset(item.value for item in Outcome)

_REFUSAL_REASON = (
    "execution refused; blocking gates are missing, not an ancestor of main, "
    "or ci_discovery is blocked because tests/simulation_runtime is not CI-collected"
)


class GridPlanError(ValueError):
    """A config, document, or gate record failed a closed check."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _reject(code: str, message: str) -> None:
    raise GridPlanError(code, message)


def _reject_locked_inputs(value: Any, label: str = "config") -> None:
    """Refuse dataset, BIDS, participant, and empirical input strings."""

    if isinstance(value, str):
        if _LOCKED_INPUT.search(value):
            _reject(
                "locked_input",
                f"{label} references ds005620, BIDS, participant, or empirical inputs",
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                _reject_locked_inputs(key, label)
            _reject_locked_inputs(item, label)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_locked_inputs(item, label)


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


def _as_text(value: Any, label: str, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _reject(code, f"{label} must be non-empty text")
    if len(value.strip()) > 2000:
        _reject(code, f"{label} exceeds 2000 characters")
    return value.strip()


def _refuse_callback(simulation: Optional[Callable[..., Any]]) -> None:
    """Accept an optional spy callback and never call it."""

    if simulation is None:
        return
    if not callable(simulation):
        _reject(
            "invalid_simulation_callback",
            "simulation callback must be callable; it is never invoked by grid_plan_v2",
        )


def _reject_roc_shaped(value: Any, *, label: str) -> None:
    if isinstance(value, Mapping) and _ROC_KEYS.intersection(value):
        _reject("detector_roc_refused", f"{label} must not carry a detector ROC")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_roc_shaped(item, label=label)


def _walk_finite(value: Any, label: str) -> Any:
    """Copy JSON-like data and reject bools, NaN, and Infinity before hashing."""

    if isinstance(value, bool) or value is None:
        _reject("invalid_threshold", f"{label} must be finite JSON, not bool or null")
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            _reject("non_finite_value", f"{label} must be finite")
        return float(value)
    if isinstance(value, Mapping):
        copied: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _reject("invalid_threshold", f"{label} keys must be strings")
            copied[key] = _walk_finite(item, f"{label}.{key}")
        return copied
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_walk_finite(item, f"{label}[]") for item in value]
    _reject("invalid_threshold", f"{label} has an unsupported value")


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


def _normalize_unit_ids(raw: Any, *, label: str) -> List[str]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) == 0:
        _reject("invalid_unit_id", f"{label} must be a non-empty list of unit ids")
    seen: set[str] = set()
    out: List[str] = []
    for item in raw:
        if not isinstance(item, str) or _TOKEN.match(item) is None:
            _reject("invalid_unit_id", f"{label} entries must be id tokens")
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


def _count_matches_ids(count: int, unit_ids: Sequence[str], nested_per_unit: int, label: str) -> None:
    """Wilson N is the independent-unit count. Windows never enter N."""

    if nested_per_unit > 1 and count == len(unit_ids) * nested_per_unit:
        _reject(
            "windows_counted_in_n",
            f"{label} equals len(unit ids) * nested_per_unit; nested units are not in N",
        )
    if count != len(unit_ids):
        _reject(
            "n_independent_mismatch",
            f"{label} must equal the number of {label} unit ids",
        )


def _derive_unit_ids(seed: int, count: int, role: str) -> List[str]:
    """Independent-unit ids from a seed. Window indexes are not part of the id."""

    return [f"{role}-seed{seed}-u{index:06d}" for index in range(count)]


def _unit_aggregation_spec(raw: Any, nested_per_unit: int) -> Dict[str, Any]:
    """Map a caller aggregation onto the named #426 contract, or reject it."""

    if nested_per_unit > 1 and raw is None:
        _reject(
            "missing_unit_aggregation",
            "unit_aggregation is required when nested_per_unit > 1",
        )
    if raw is None:
        return {
            "value": "not_required",
            "named_on_pr_426": False,
            "required": False,
        }
    if not isinstance(raw, str) or raw not in _UNIT_AGGREGATION_NAMED:
        _reject(
            "invalid_unit_aggregation",
            "unit_aggregation must be cluster_any_event_rate "
            "(synthetic_forward_roc.py:194; cluster_ids on operating_point and compute_roc)",
        )
    named = _UNIT_AGGREGATION_NAMED[raw]
    return {
        "value": raw,
        "required": nested_per_unit > 1,
        "named_on_pr_426": named["named_on_pr_426"],
        "symbol": named["symbol"],
        "source_citation": named["source_citation"],
        "cluster_ids_parameters": list(named["cluster_ids_parameters"]),
    }


def _class_pair(positive: int, negative: int, total: int, role: str) -> None:
    if positive + negative != total:
        _reject(
            "n_class_mismatch",
            f"n_positive_{role} + n_negative_{role} must equal n_independent_{role}",
        )


def _freeze_threshold(
    *,
    h0: str,
    h1: str,
    score_definition_id: str,
    threshold: Mapping[str, Any],
    calibration_unit_ids: Sequence[str],
    calibration_seed: int,
    estimand: str,
    interval_method: str,
    unit_aggregation: str,
) -> str:
    """Hash the decision rule. This function does not read evaluation ids.

    The read order is in-process only. It is not a preregistration record.
    """

    return compute_config_hash(
        {
            "h0": h0,
            "h1": h1,
            "score_definition_id": score_definition_id,
            "threshold": threshold,
            "calibration_unit_ids": list(calibration_unit_ids),
            "calibration_seed": calibration_seed,
            "estimand": estimand,
            "interval_method": interval_method,
            "unit_aggregation": unit_aggregation,
        }
    )


def _evaluation_manifest(
    *,
    threshold_hash: str,
    score_definition_id: str,
    evaluation_unit_ids: Sequence[str],
    n_independent_evaluation: int,
) -> Dict[str, Any]:
    if not isinstance(threshold_hash, str) or len(threshold_hash) != 64:
        _reject(
            "threshold_not_frozen",
            "evaluation manifest requires a recorded threshold hash",
        )
    return {
        "threshold_hash": threshold_hash,
        "score_definition_id": score_definition_id,
        "built_after_threshold_hash": True,
        "threshold_order": "in_process_only_not_preregistration",
        "evaluation_unit_ids": list(evaluation_unit_ids),
        "n_independent_evaluation": int(n_independent_evaluation),
    }


def _read_evaluation_side(
    config: Mapping[str, Any],
    *,
    threshold_hash: str,
    score_definition_id: str,
    calibration_unit_ids: Sequence[str],
    evaluation_seed: int,
    nested_per_unit: int,
) -> Tuple[List[str], int, bool, Dict[str, Any], int, int]:
    """Derive evaluation ids only after ``threshold_hash`` exists."""

    if "n_independent_evaluation" not in config:
        _reject("unknown_field", "n_independent_evaluation is required")
    n_independent_evaluation = _as_positive_int(
        config["n_independent_evaluation"],
        "n_independent_evaluation",
        "invalid_sample_count",
    )
    for key in ("n_positive_evaluation", "n_negative_evaluation"):
        if key not in config:
            _reject("unknown_field", f"missing config fields ['{key}']")
    n_positive_evaluation = _as_positive_int(
        config["n_positive_evaluation"],
        "n_positive_evaluation",
        "invalid_sample_count",
    )
    n_negative_evaluation = _as_positive_int(
        config["n_negative_evaluation"],
        "n_negative_evaluation",
        "invalid_sample_count",
    )
    _class_pair(
        n_positive_evaluation,
        n_negative_evaluation,
        n_independent_evaluation,
        "evaluation",
    )
    evaluation_unit_ids = _derive_unit_ids(
        evaluation_seed, n_independent_evaluation, "evaluation"
    )
    _count_matches_ids(
        n_independent_evaluation,
        evaluation_unit_ids,
        nested_per_unit,
        "n_independent_evaluation",
    )
    roles_are_disjoint = set(calibration_unit_ids).isdisjoint(evaluation_unit_ids)
    if not roles_are_disjoint:
        _reject(
            "unit_id_overlap",
            "a unit id is in both calibration_unit_ids and evaluation_unit_ids",
        )
    manifest = _evaluation_manifest(
        threshold_hash=threshold_hash,
        score_definition_id=score_definition_id,
        evaluation_unit_ids=evaluation_unit_ids,
        n_independent_evaluation=n_independent_evaluation,
    )
    return (
        evaluation_unit_ids,
        n_independent_evaluation,
        roles_are_disjoint,
        manifest,
        n_positive_evaluation,
        n_negative_evaluation,
    )


def _normalize_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(config, Mapping):
        _reject("unsupported_schema_version", "config must be a mapping")
    _reject_locked_inputs(config)
    if _CALLER_UNIT_ID_KEYS.intersection(config):
        _reject(
            "caller_unit_ids_rejected",
            "calibration_unit_ids and evaluation_unit_ids are derived from seeds; "
            "caller lists, including window ids, are rejected",
        )
    if "evaluation_manifest" in config:
        _reject(
            "evaluation_manifest_before_threshold",
            "a caller-built evaluation manifest is rejected; the threshold hash is recorded first",
        )
    extra = set(config) - (_CONFIG_KEYS | _EVALUATION_KEYS)
    if extra:
        _reject("unknown_field", f"unknown config fields {sorted(extra)}")
    schema_version = config.get("schema_version") if "schema_version" in config else None
    if schema_version != GRID_PLAN_SCHEMA_VERSION:
        _reject(
            "unsupported_schema_version",
            f"unsupported schema_version {schema_version!r}; expected {GRID_PLAN_SCHEMA_VERSION!r}",
        )
    missing = [key for key in sorted(_REQUIRED_BEFORE_THRESHOLD | _EVALUATION_KEYS) if key not in config]
    # Presence of evaluation keys is checked later so a missing threshold
    # fails before those values are read. A missing pre-threshold key fails now.
    early_missing = [
        key for key in missing if key not in _EVALUATION_KEYS and key != "threshold"
    ]
    if early_missing:
        _reject("unknown_field", f"missing config fields {early_missing}")
    if "threshold" not in config:
        _reject("threshold_not_frozen", "threshold is required before evaluation ids are read")

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

    independent_unit = config["independent_unit"]
    if independent_unit not in INDEPENDENT_UNITS:
        _reject(
            "synthetic_requires_simulation_seed",
            "independent_unit must be simulation_seed, subject, or recording",
        )
    if independent_unit != SYNTHETIC_INDEPENDENT_UNIT:
        _reject(
            "synthetic_requires_simulation_seed",
            "synthetic plans require independent_unit simulation_seed",
        )
    n_independent_calibration = _as_positive_int(
        config["n_independent_calibration"],
        "n_independent_calibration",
        "invalid_sample_count",
    )
    n_positive_calibration = _as_positive_int(
        config["n_positive_calibration"],
        "n_positive_calibration",
        "invalid_sample_count",
    )
    n_negative_calibration = _as_positive_int(
        config["n_negative_calibration"],
        "n_negative_calibration",
        "invalid_sample_count",
    )
    _class_pair(
        n_positive_calibration,
        n_negative_calibration,
        n_independent_calibration,
        "calibration",
    )
    calibration_unit_ids = _derive_unit_ids(
        calibration_seed, n_independent_calibration, "calibration"
    )
    nested_unit = config["nested_unit"]
    if nested_unit not in NESTED_UNITS:
        _reject("invalid_nested", "nested_unit must be window, trial, or none")
    nested_per_unit = _as_positive_int(
        config["nested_per_unit"], "nested_per_unit", "invalid_nested"
    )
    if nested_unit == "none" and nested_per_unit != 1:
        _reject("invalid_nested", "nested_unit none requires nested_per_unit 1")
    unit_aggregation = _unit_aggregation_spec(
        config.get("unit_aggregation"), nested_per_unit
    )
    _count_matches_ids(
        n_independent_calibration,
        calibration_unit_ids,
        nested_per_unit,
        "n_independent_calibration",
    )

    interval_method = config["interval_method"]
    if not isinstance(interval_method, str) or interval_method not in INTERVAL_METHODS:
        _reject(
            "window_level_interval",
            "interval_method must be cluster_bootstrap_over_independent_unit "
            "or wilson_on_independent_unit",
        )
    estimand = _as_text(config["estimand"], "estimand", "missing_estimand")
    power_claim = config["power_claim"]
    if power_claim != POWER_CLAIM:
        _reject("power_claim", "power_claim must be 'none'; sample size is not a power guarantee")
    h0 = _as_text(config["h0"], "h0", "missing_hypothesis")
    h1 = _as_text(config["h1"], "h1", "missing_hypothesis")
    score_definition_id = config["score_definition_id"]
    if not isinstance(score_definition_id, str) or _TOKEN.match(score_definition_id) is None:
        _reject(
            "missing_score_definition",
            "score_definition_id must be an identifier; it is not computed here",
        )
    if "threshold" not in config or config["threshold"] is None:
        _reject("threshold_not_frozen", "threshold is required before evaluation ids are read")
    if not isinstance(config["threshold"], Mapping) or len(config["threshold"]) == 0:
        _reject("invalid_threshold", "threshold must be a non-empty mapping")
    threshold = _walk_finite(config["threshold"], "threshold")
    threshold_hash = _freeze_threshold(
        h0=h0,
        h1=h1,
        score_definition_id=score_definition_id,
        threshold=threshold,
        calibration_unit_ids=calibration_unit_ids,
        calibration_seed=calibration_seed,
        estimand=estimand,
        interval_method=interval_method,
        unit_aggregation=str(unit_aggregation["value"]),
    )

    (
        evaluation_unit_ids,
        n_independent_evaluation,
        roles_are_disjoint,
        evaluation_manifest,
        n_positive_evaluation,
        n_negative_evaluation,
    ) = _read_evaluation_side(
        config,
        threshold_hash=threshold_hash,
        score_definition_id=score_definition_id,
        calibration_unit_ids=calibration_unit_ids,
        evaluation_seed=evaluation_seed,
        nested_per_unit=nested_per_unit,
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
    nuisance_scenario_id = _normalize_nuisance(config.get("nuisance_scenario_id"))
    return {
        "schema_version": GRID_PLAN_SCHEMA_VERSION,
        "axes": axes,
        "null_model_ids": null_model_ids,
        "source_model_ids": source_model_ids,
        "master_seed": master_seed,
        "calibration_seed": calibration_seed,
        "evaluation_seed": evaluation_seed,
        "independent_unit": independent_unit,
        "calibration_unit_ids": calibration_unit_ids,
        "evaluation_unit_ids": evaluation_unit_ids,
        "n_independent_calibration": n_independent_calibration,
        "n_independent_evaluation": n_independent_evaluation,
        "n_positive_calibration": n_positive_calibration,
        "n_negative_calibration": n_negative_calibration,
        "n_positive_evaluation": n_positive_evaluation,
        "n_negative_evaluation": n_negative_evaluation,
        "nested_unit": nested_unit,
        "nested_per_unit": nested_per_unit,
        "unit_aggregation": config["unit_aggregation"] if "unit_aggregation" in config else None,
        "unit_aggregation_spec": unit_aggregation,
        "nested_counted_in_n": False,
        "roles_are_disjoint": roles_are_disjoint,
        "interval_method": interval_method,
        "estimand": estimand,
        "power_claim": POWER_CLAIM,
        "h0": h0,
        "h1": h1,
        "score_definition_id": score_definition_id,
        "threshold": threshold,
        "threshold_hash": threshold_hash,
        "evaluation_manifest": evaluation_manifest,
        "wilson_confidence_level": float(confidence),
        "wilson_target_full_width": float(width),
        "wilson_design_p": design_p,
        "max_cells": max_cells,
        "max_trials": max_trials,
        "max_compute_units": max_compute_units,
        "compute_units_per_trial": compute_units_per_trial,
        "nuisance_scenario_id": nuisance_scenario_id,
        "failure_policy": FAILURE_POLICY,
        "data_mode": "synthetic",
    }


def _wilson_bound(normalized: Mapping[str, Any]) -> SampleSizePlanResult:
    """Floor only the independent-unit counts. ``nested_per_unit`` is ignored."""

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
        int(normalized["n_independent_calibration"]) < required
        or int(normalized["n_independent_evaluation"]) < required
    ):
        _reject(
            "invalid_sample_count",
            "n_independent_calibration and n_independent_evaluation must each be >= "
            f"Wilson required_n {required}. Counts below that #405 floor are rejected "
            "and are not emitted. "
            f"{UNDERPOWERED_DRY_RUN} is only an emitted plan whose "
            "n_positive_calibration, n_negative_calibration, n_positive_evaluation, "
            f"or n_negative_evaluation is below {ENGINEERING_THRESHOLD_N}. "
            f"That label is an {ENGINEERING_MINIMUM_NOTE}.",
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
    per_cell = int(normalized["n_independent_calibration"]) + int(
        normalized["n_independent_evaluation"]
    )
    trial_budget = int(normalized["max_trials"])
    if per_cell > trial_budget or cell_count > trial_budget // per_cell:
        _reject(
            "over_budget",
            f"independent-unit count {cell_count * per_cell} exceeds max_trials "
            f"{normalized['max_trials']}",
        )
    trial_count = cell_count * per_cell
    if trial_count > ABSOLUTE_MAX_TRIALS:
        _reject(
            "over_budget",
            f"independent-unit count {trial_count} exceeds planner ceiling {ABSOLUTE_MAX_TRIALS}",
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
        "independent_units_per_cell": per_cell,
    }


def _proportion_declaration(
    metric_id: str,
    numerator: str,
    denominator: str,
    undefined_reason: str,
) -> Dict[str, Any]:
    """Declared proportion. No rate is computed."""

    return {
        "metric_id": metric_id,
        "named_on_pr_426": metric_id in ROC_API_NAMES,
        "integration": "NOT_INTEGRATED",
        "source_pr": ROC_API_PR,
        "source_head": ROC_API_HEAD,
        "computed": False,
        "value": None,
        "kind": "proportion_at_frozen_threshold",
        "numerator_field": numerator,
        "denominator_field": denominator,
        "count_unit": "independent_unit",
        "windows_counted": False,
        "interval_method": "wilson_on_independent_unit",
        "undefined_value": "UNDEFINED",
        "undefined_reason": undefined_reason,
        "silent_zero": False,
        "silent_nan": False,
    }


def _metric_spec(unit_aggregation: Mapping[str, Any]) -> Dict[str, Any]:
    """Metric declarations included in the plan hash. Nothing is scored."""

    return {
        "schema": "grid_plan_metric_declarations_v1",
        "computed": False,
        "imports_roc_api": False,
        "integration": "NOT_INTEGRATED",
        "source_pr": ROC_API_PR,
        "source_head": ROC_API_HEAD,
        "unit_aggregation": copy.deepcopy(dict(unit_aggregation)),
        "metrics": [
            _proportion_declaration(
                "tpr",
                "true_positives",
                "positives",
                "tpr_undefined_zero_denominator",
            ),
            _proportion_declaration(
                "fpr",
                "false_positives",
                "negatives",
                "fpr_undefined_zero_denominator",
            ),
            _proportion_declaration(
                "precision",
                "true_positives",
                "predicted_positives",
                "precision_undefined_no_predicted_positives",
            ),
            _proportion_declaration(
                "accuracy",
                "correct_independent_units",
                "independent_units",
                "accuracy_undefined_zero_denominator",
            ),
            {
                "metric_id": "auc",
                "named_on_pr_426": True,
                "integration": "NOT_INTEGRATED",
                "source_pr": ROC_API_PR,
                "source_head": ROC_API_HEAD,
                "computed": False,
                "value": None,
                "kind": "ranking",
                "estimator": "mann_whitney_midrank",
                "tie_rule": "ties_count_0.5",
                "interval_method": "cluster_bootstrap_over_independent_unit",
                "numerator_field": None,
                "denominator_field": None,
                "windows_counted": False,
                "undefined_value": "UNDEFINED",
                "undefined_when": "either_class_empty",
                "undefined_reason": "auc_undefined_empty_class",
                "silent_zero": False,
                "silent_nan": False,
            },
            {
                "metric_id": "average_precision",
                "named_on_pr_426": True,
                "integration": "NOT_INTEGRATED",
                "source_pr": ROC_API_PR,
                "source_head": ROC_API_HEAD,
                "computed": False,
                "value": None,
                "kind": "ranking",
                "estimator": "stepwise_precision_at_recall",
                "interpolation": False,
                "definition": "sum of precision at each recall step, no interpolation",
                "interval_method": "cluster_bootstrap_over_independent_unit",
                "numerator_field": None,
                "denominator_field": None,
                "windows_counted": False,
                "undefined_value": "UNDEFINED",
                "undefined_when": "no_positives",
                "undefined_reason": "ap_undefined_no_positives",
                "silent_zero": False,
                "silent_nan": False,
            },
        ],
    }


def _sample_size_label(
    n_positive_calibration: int,
    n_negative_calibration: int,
    n_positive_evaluation: int,
    n_negative_evaluation: int,
) -> str:
    """Engineering label. This is not a power analysis.

    Wilson counts below required_n are rejected before this label is applied.
    """

    counts = (
        n_positive_calibration,
        n_negative_calibration,
        n_positive_evaluation,
        n_negative_evaluation,
    )
    if any(count < ENGINEERING_THRESHOLD_N for count in counts):
        return UNDERPOWERED_DRY_RUN
    return ENGINEERING_THRESHOLD_MET


def _mb_bound(nbytes: int) -> float:
    if nbytes < 1:
        _reject("cost_not_estimated", "resource bound has no bytes to estimate")
    mb = nbytes / (1024 * 1024)
    if mb <= 0.0:
        _reject("cost_not_estimated", "resource bound rounded to 0")
    return mb


def _cost_estimate(normalized: Mapping[str, Any], cell_count: int) -> Dict[str, Any]:
    """Upper bound from declared sizes. No callback is run."""

    n_calibration = int(normalized["n_independent_calibration"])
    n_evaluation = int(normalized["n_independent_evaluation"])
    nested = int(normalized["nested_per_unit"])
    independent_units = n_calibration + n_evaluation
    product = cell_count * independent_units * nested
    output_bytes = product * DECLARED_BYTES_PER_RECORD
    expected_artifact_count = len(PLANNED_OUTPUTS) + cell_count
    artifact_bytes = expected_artifact_count * DECLARED_BYTES_PER_RECORD
    per_cell_bytes = independent_units * nested * DECLARED_BYTES_PER_RECORD
    per_cell_disk_bytes = per_cell_bytes + DECLARED_BYTES_PER_RECORD
    return {
        "computed_without_running": True,
        "label": DECLARED_ESTIMATE,
        "cell_count": cell_count,
        "n_independent_calibration": n_calibration,
        "n_independent_evaluation": n_evaluation,
        "independent_units_per_cell": independent_units,
        "nested_per_unit": nested,
        "cells_times_independent_units_times_nested": product,
        "estimated_callback_invocations": product,
        "output_records": product,
        "declared_bytes_per_record": DECLARED_BYTES_PER_RECORD,
        "estimated_output_bytes": output_bytes,
        "expected_artifact_count": expected_artifact_count,
        "estimated_disk_mb": _mb_bound(output_bytes + artifact_bytes),
        "estimated_memory_mb": _mb_bound(per_cell_bytes),
        "per_cell_disk_mb": _mb_bound(per_cell_disk_bytes),
        "per_cell_memory_mb": _mb_bound(per_cell_bytes),
    }


def _hash_payload(normalized: Mapping[str, Any]) -> Dict[str, Any]:
    """Scientific inputs only. Derived cells and gate records are not included."""

    return {
        "schema_version": GRID_PLAN_SCHEMA_VERSION,
        "axes": normalized["axes"],
        "null_model_ids": list(normalized["null_model_ids"]),
        "source_model_ids": list(normalized["source_model_ids"]),
        "master_seed": normalized["master_seed"],
        "calibration_seed": normalized["calibration_seed"],
        "evaluation_seed": normalized["evaluation_seed"],
        "independent_unit": normalized["independent_unit"],
        "calibration_unit_ids": list(normalized["calibration_unit_ids"]),
        "evaluation_unit_ids": list(normalized["evaluation_unit_ids"]),
        "n_independent_calibration": normalized["n_independent_calibration"],
        "n_independent_evaluation": normalized["n_independent_evaluation"],
        "n_positive_calibration": normalized["n_positive_calibration"],
        "n_negative_calibration": normalized["n_negative_calibration"],
        "n_positive_evaluation": normalized["n_positive_evaluation"],
        "n_negative_evaluation": normalized["n_negative_evaluation"],
        "nested_unit": normalized["nested_unit"],
        "nested_per_unit": normalized["nested_per_unit"],
        "unit_aggregation": normalized["unit_aggregation_spec"],
        "interval_method": normalized["interval_method"],
        "estimand": normalized["estimand"],
        "power_claim": normalized["power_claim"],
        "sample_size_label": normalized["sample_size_label"],
        "execution_mode": normalized["execution_mode"],
        "engineering_minimum_note": ENGINEERING_MINIMUM_NOTE,
        "engineering_threshold_n": ENGINEERING_THRESHOLD_N,
        "power_analysis_supplied": False,
        "engineering_threshold_is_power_guarantee": False,
        "declared_bytes_per_record": DECLARED_BYTES_PER_RECORD,
        "metric_spec": _metric_spec(normalized["unit_aggregation_spec"]),
        "required_source_sha": dict(REQUIRED_SOURCE_SHA),
        "h0": normalized["h0"],
        "h1": normalized["h1"],
        "score_definition_id": normalized["score_definition_id"],
        "threshold": normalized["threshold"],
        "threshold_hash": normalized["threshold_hash"],
        "split_algorithm": SPLIT_ALGORITHM,
        "wilson_confidence_level": normalized["wilson_confidence_level"],
        "wilson_target_full_width": normalized["wilson_target_full_width"],
        "wilson_design_p": normalized["wilson_design_p"],
        "max_cells": normalized["max_cells"],
        "max_trials": normalized["max_trials"],
        "max_compute_units": normalized["max_compute_units"],
        "compute_units_per_trial": normalized["compute_units_per_trial"],
        "blocking_gate_ids": list(BLOCKING_GATE_IDS),
        "nonblocking_gate_ids": list(NONBLOCKING_GATE_IDS),
        "admissible_gate_decisions": list(ADMISSIBLE_GATE_DECISIONS),
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "nuisance_scenario_id": normalized["nuisance_scenario_id"],
    }


def _independence_block(normalized: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "independent_unit": normalized["independent_unit"],
        "n_independent_calibration": normalized["n_independent_calibration"],
        "n_independent_evaluation": normalized["n_independent_evaluation"],
        "n_positive_calibration": normalized["n_positive_calibration"],
        "n_negative_calibration": normalized["n_negative_calibration"],
        "n_positive_evaluation": normalized["n_positive_evaluation"],
        "n_negative_evaluation": normalized["n_negative_evaluation"],
        "unit_aggregation": normalized["unit_aggregation_spec"]["value"],
        "nested_unit": normalized["nested_unit"],
        "nested_per_unit": normalized["nested_per_unit"],
        "interval_method": normalized["interval_method"],
        "estimand": normalized["estimand"],
        "power_claim": normalized["power_claim"],
        "calibration_unit_ids": list(normalized["calibration_unit_ids"]),
        "evaluation_unit_ids": list(normalized["evaluation_unit_ids"]),
        "roles_are_disjoint": normalized["roles_are_disjoint"],
        "roles_are_disjoint_is_statistical_independence": False,
        "roles_are_disjoint_note": ROLES_DISJOINT_NOTE,
        "sample_size_label": normalized["sample_size_label"],
        "execution_mode": normalized["execution_mode"],
        "engineering_minimum_note": ENGINEERING_MINIMUM_NOTE,
        "nested_counted_in_n": False,
    }


def _expand_cells(normalized: Mapping[str, Any], *, block_reason: str) -> List[Dict[str, Any]]:
    axes = list(normalized["axes"])
    names = [axis["name"] for axis in axes]
    value_lists = [list(axis["values"]) for axis in axes]
    independence = _independence_block(normalized)
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
                    "blocked": True,
                    "block_reason": block_reason,
                    "cell_index": index,
                    "axes": axis_values,
                    "null_model_id": null_model_id,
                    "source_model_id": source_model_id,
                    "nuisance_scenario_id": normalized["nuisance_scenario_id"],
                    "calibration_seed": normalized["calibration_seed"],
                    "evaluation_seed": normalized["evaluation_seed"],
                    "split_algorithm": SPLIT_ALGORITHM,
                    "threshold_hash": normalized["threshold_hash"],
                    "score_definition_id": normalized["score_definition_id"],
                    "h0": normalized["h0"],
                    "h1": normalized["h1"],
                    **independence,
                }
                cells.append(
                    {
                        "cell_id": cell_id,
                        "cell_index": index,
                        "blocked": True,
                        "block_reason": block_reason,
                        "evaluation_eligible": False,
                        "parameter_case": parameter_case,
                        "null_model_id": null_model_id,
                        "source_model_id": source_model_id,
                        "nuisance_scenario_id": normalized["nuisance_scenario_id"],
                        "threshold_hash": normalized["threshold_hash"],
                        "score_definition_id": normalized["score_definition_id"],
                        **independence,
                    }
                )
                index += 1
    return cells


def _campaign_manifest(
    normalized: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]],
    config_hash: str,
    cost: Mapping[str, Any],
) -> CampaignManifest:
    units = [
        WorkUnit(
            unit_id=str(cell["cell_id"]),
            command=[],
            parameter_case=copy.deepcopy(dict(cell["parameter_case"])),
            expected_outputs=[],
            timeout_s=0.0,
            dependencies=[],
            estimated_disk_mb=float(cost["per_cell_disk_mb"]),
            estimated_memory_mb=float(cost["per_cell_memory_mb"]),
            retryable=False,
            max_retries=0,
        )
        for cell in cells
    ]
    return CampaignManifest(
        schema_version=CAMPAIGN_MANIFEST_SCHEMA_VERSION,
        campaign_id=f"grid-plan-v2-{config_hash[:12]}",
        created_at=_CREATED_AT,
        code_commit=_code_version_id(),
        configuration_hash=config_hash,
        seed=int(normalized["master_seed"]),
        units=units,
        environment={
            "data_mode": "synthetic",
            "status": HOLD_STATUS,
            "launches_simulation": False,
            "participant_data": False,
            "detector_roc": None,
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
        "sweep_reachable": False,
        "marks_complete_on_validation": False,
        "data_mode": "synthetic",
        "hold_status": HOLD_STATUS,
        "absolute_max_cells": ABSOLUTE_MAX_CELLS,
        "absolute_max_trials": ABSOLUTE_MAX_TRIALS,
        "artifact_sha_is_format_only": True,
        "checked_at_is_caller_set": True,
        "caller_gate_decision_accepted": False,
        "nuisance_scenarios_are_ids_only": True,
        "null_ids_are_labels_only": True,
        "null_model_note": NULL_MODEL_NOTE,
        "spatial_winding_randomization_evidence": False,
        "power_claim": POWER_CLAIM,
        "nested_units_count_toward_wilson_n": False,
        "windows_count_toward_wilson_n": False,
        "engineering_threshold_n": ENGINEERING_THRESHOLD_N,
        "engineering_threshold_is_power_guarantee": False,
        "engineering_minimum_note": ENGINEERING_MINIMUM_NOTE,
        "candidate_is_evidence": False,
        "open_pr_is_evidence": False,
        "required_source_sha": dict(REQUIRED_SOURCE_SHA),
        "open_pr_heads_not_evidence": dict(OPEN_PR_HEADS_NOT_EVIDENCE),
        "metrics_are_computed": False,
        "roc_api_integrated": False,
        "ci_discovery": "BLOCKED",
        "detector_roc": None,
        "planned_outputs": list(PLANNED_OUTPUTS),
        "forbidden_outputs": list(FORBIDDEN_OUTPUTS),
        "failure_policy": FAILURE_POLICY,
        "reports_read_from": "git_blobs_at_writer_paths_on_main",
        "record_root_is_evidence": False,
        "gate_integration_state_is_evidence": False,
        "ancestry_fetches": False,
        "writer_report_paths": list(_writer_report_paths()),
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
        "applied_to": ["n_independent_calibration", "n_independent_evaluation"],
        "nested_per_unit_ignored": True,
        "source": "analysis.binomial_planning.plan_sample_size",
    }


def _git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def _resolve_main_sha() -> Optional[str]:
    """Local main ref only. This does not fetch."""

    for ref in ("origin/main", "main"):
        try:
            completed = _git(["rev-parse", "--verify", ref])
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            continue
        sha = completed.stdout.strip()
        if _COMMIT_SHA.fullmatch(sha):
            return sha
    return None


def _is_ancestor_of_main(commit: str, main_sha: str) -> bool:
    if _COMMIT_SHA.fullmatch(commit) is None or _COMMIT_SHA.fullmatch(main_sha) is None:
        return False
    try:
        completed = _git(["merge-base", "--is-ancestor", commit, main_sha])
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _resolve_head_sha() -> Optional[str]:
    """Local HEAD only. Missing git yields None, which becomes UNKNOWN."""

    try:
        completed = _git(["rev-parse", "--verify", "HEAD"])
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    sha = completed.stdout.strip()
    if _COMMIT_SHA.fullmatch(sha):
        return sha
    return None


def _code_version_id() -> str:
    return _resolve_head_sha() or CODE_VERSION_UNKNOWN


def _worktree_dirty() -> bool:
    """True when HEAD is dirty, or when status cannot be read. Fail closed."""

    try:
        completed = _git(["status", "--porcelain"])
    except (OSError, subprocess.SubprocessError):
        return True
    if completed.returncode != 0:
        return True
    return bool(completed.stdout.strip())


def _provenance(
    main_sha: Optional[str],
    code_version_id: str,
    config_hash: str,
    worktree_dirty: bool,
) -> Dict[str, Any]:
    return {
        "schema_version": GRID_PLAN_SCHEMA_VERSION,
        "generator": GENERATOR,
        "base_sha": main_sha or "unresolved",
        "audited_main_sha": AUDITED_MAIN_SHA,
        "code_version_id": code_version_id,
        "worktree_dirty": bool(worktree_dirty),
        "config_digest": config_hash,
        "failure_policy": FAILURE_POLICY,
    }


def _toy_fixture(scores: Any) -> Dict[str, Any]:
    if scores is None:
        return {"label": None, "scores": None, "detector_roc": None}
    _reject_roc_shaped(scores, label="toy_scores")
    if isinstance(scores, bool) or not isinstance(scores, Sequence) or isinstance(scores, (str, bytes)):
        _reject("invalid_toy_fixture", "toy_scores must be a list of finite numbers")
    copied: List[int | float] = []
    for index, item in enumerate(scores):
        copied.append(_as_finite_number(item, f"toy_scores[{index}]", type_code="invalid_toy_fixture"))
    return {
        "label": TOY_FIXTURE_LABEL,
        "scores": copied,
        "detector_roc": None,
    }


def _writer_result_keys() -> frozenset[str]:
    """Keys ``PromotionResult.to_dict`` emits. reporting defines no separate hash."""

    sample = PromotionResult(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        case_id="shape",
        promotion_decision="HOLD_INCONCLUSIVE",
        reason_codes=(),
        reasons=(),
        declared_evidence_class=None,
        allowed_evidence_class="hypothesis",
        synthetic_demo=True,
        scientific_pass=False,
        scientific_eligibility=False,
        formal_bayes_factor=None,
        declared_formal_bayes_factor=None,
        claim_gate=None,
        input_fingerprints={},
    )
    return frozenset(sample.to_dict())


_PAYLOAD_KEYS = frozenset({"schema_version", "scientific_pass", "case_count", "results"})
_RESULT_KEYS = _writer_result_keys()
_EXTRA_RESULT_KEYS = frozenset(
    {"verified_at_commit", "source_sha", "limitations_recorded"}
)


def _reporting_hash_callable() -> Optional[Callable[..., Any]]:
    """Return reporting's hash callable when it has one of the exact names.

    A name that merely contains ``hash`` is not a reporting hash.
    """

    import tools.evidence_promotion_gate.reporting as reporting

    for name in _REPORTING_HASH_NAMES:
        value = getattr(reporting, name, None)
        if callable(value):
            return value
    return None


def _writer_report_paths() -> Tuple[str, ...]:
    """Repo-relative paths ``write_report`` writes without a caller path.

    ``write_report(payload, output)`` requires ``output``. It has no default
    location, so no path on main is a promotion report this planner will read.
    """

    signature = inspect.signature(write_report)
    output = signature.parameters.get("output")
    if output is None or output.default is inspect.Parameter.empty:
        return ()
    default = output.default
    if isinstance(default, (str, Path)) and str(default).strip():
        return (str(default).replace("\\", "/"),)
    return ()


def _git_failure_reason() -> Optional[str]:
    """Fail closed when git, a full history, or main cannot be used. No fetch."""

    try:
        shallow = _git(["rev-parse", "--is-shallow-repository"])
    except (OSError, subprocess.SubprocessError):
        return "git_missing"
    if shallow.returncode != 0:
        return "git_missing"
    if shallow.stdout.strip() == "true":
        return "shallow_clone"
    if _resolve_main_sha() is None:
        return "main_unresolved"
    return None


def _path_tracked(main_sha: str, path: str) -> bool:
    try:
        completed = _git(["ls-tree", "-r", "--name-only", main_sha, "--", path])
    except (OSError, subprocess.SubprocessError):
        return False
    if completed.returncode != 0:
        return False
    names = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    return path in names


def _git_show(main_sha: str, path: str) -> Optional[str]:
    try:
        completed = _git(["show", f"{main_sha}:{path}"])
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    text = completed.stdout
    if len(text.encode("utf-8")) > _MAX_REPORT_BYTES:
        return None
    return text


def _blob_commit(main_sha: str, path: str) -> Optional[str]:
    try:
        completed = _git(["rev-list", "-1", main_sha, "--", path])
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    sha = completed.stdout.strip()
    if _COMMIT_SHA.fullmatch(sha):
        return sha
    return None


def _writer_shaped(payload: Mapping[str, Any], raw_text: str) -> Optional[str]:
    """Return compute_config_hash of the writer body, or None when the shape differs."""

    if set(payload) != _PAYLOAD_KEYS:
        return None
    if payload.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        return None
    if payload.get("scientific_pass") is not False:
        return None
    results = payload.get("results")
    if not isinstance(results, list) or payload.get("case_count") != len(results):
        return None
    writer_results: List[Dict[str, Any]] = []
    for row in results:
        if not isinstance(row, Mapping):
            return None
        if set(row) - _RESULT_KEYS - _EXTRA_RESULT_KEYS:
            return None
        if not _RESULT_KEYS.issubset(row):
            return None
        if row.get("scientific_pass") is not False:
            return None
        if not isinstance(row.get("case_id"), str):
            return None
        writer_results.append({key: row[key] for key in sorted(_RESULT_KEYS)})
    try:
        canonical = serialize_json(dict(payload))
    except (TypeError, ValueError):
        return None
    if raw_text != canonical:
        return None
    writer_body = {
        "schema_version": payload["schema_version"],
        "scientific_pass": False,
        "case_count": payload["case_count"],
        "results": writer_results,
    }
    recomputed = compute_config_hash(writer_body)
    hash_fn = _reporting_hash_callable()
    if hash_fn is not None:
        try:
            declared = hash_fn(writer_body)
        except (TypeError, ValueError):
            return None
        if declared != recomputed:
            return None
    return recomputed


def _load_tracked_rows(main_sha: str) -> List[Dict[str, Any]]:
    """Rows from ``git show <main_sha>:<writer path>`` only. No worktree reads."""

    rows: List[Dict[str, Any]] = []
    for path in _writer_report_paths():
        if not _path_tracked(main_sha, path):
            continue
        raw = _git_show(main_sha, path)
        if raw is None:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, Mapping):
            continue
        report_hash = _writer_shaped(payload, raw)
        if report_hash is None:
            continue
        blob_commit = _blob_commit(main_sha, path)
        for row in payload["results"]:
            copied = dict(row)
            copied["_source"] = "git_blob"
            copied["_path"] = path
            copied["_blob_commit"] = blob_commit
            copied["_report_hash"] = report_hash
            rows.append(copied)
    return rows


def _blocker(code: str, message: str, gate_id: Optional[str] = None) -> Dict[str, Any]:
    return {"code": code, "gate_id": gate_id, "message": message}


def _ci_discovery_blocked() -> bool:
    """Production default. Tests may patch this. A patch is not evidence."""

    return True


def _blob_is_at_or_after(verified_at_commit: str, blob_commit: Optional[str], main_sha: str) -> bool:
    """The blob commit on main must be ``verified_at_commit`` or a later descendant.

    ``verified_at_commit == main`` is accepted only when the blob itself was
    last committed at that tip. A worktree file is never a blob commit.
    """

    if blob_commit is None or _COMMIT_SHA.fullmatch(blob_commit) is None:
        return False
    if not _is_ancestor_of_main(verified_at_commit, main_sha):
        return False
    return _is_ancestor_of_main(verified_at_commit, blob_commit)


def _resolve_one(
    gate_id: str,
    *,
    role: str,
    rows: Sequence[Mapping[str, Any]],
    main_sha: Optional[str],
    git_failure: Optional[str],
) -> Dict[str, Any]:
    integration = GATE_INTEGRATION_STATE.get(gate_id, "NOT_INTEGRATED")
    base = {
        "gate_id": gate_id,
        "role": role,
        "integration": integration,
        "integration_is_evidence": False,
        "candidate_is_evidence": False,
        "required_source_sha": REQUIRED_SOURCE_SHA.get(gate_id),
        "verified_at_commit": None,
        "resolved_from": "none",
        "report_hash": None,
    }
    if git_failure is not None or main_sha is None:
        return {**base, "status": "missing", "git_failure": git_failure or "main_unresolved"}
    if gate_id == CI_DISCOVERY_GATE_ID and _ci_discovery_blocked():
        return {
            **base,
            "status": "ci_discovery_blocked",
            "message": (
                "tests/simulation_runtime is not collected by .github/workflows/ci.yml, "
                ".github/workflows/required-checks.yml, or docker/ci/core.Dockerfile. "
                "A CI workflow change must not land before this gate repair is merged."
            ),
        }
    matched = [row for row in rows if row.get("case_id") == gate_id]
    if len(matched) > 1:
        return {
            **base,
            "status": "duplicate_record",
            "resolved_from": "evidence_promotion_gate_report",
        }
    if len(matched) == 0:
        return {**base, "status": "missing"}
    row = matched[0]
    if row.get("_source") != "git_blob":
        return {**base, "status": "missing", "label": TEST_FIXTURE_NOT_EVIDENCE}
    required_sha = REQUIRED_SOURCE_SHA.get(gate_id)
    if required_sha is not None:
        recorded = row.get("source_sha")
        if not isinstance(recorded, str) or _COMMIT_SHA.fullmatch(recorded) is None:
            return {**base, "status": "missing_source_sha", "source_sha": recorded}
        if recorded != required_sha:
            return {
                **base,
                "status": "stale_source",
                "source_sha": recorded,
                "required_source_sha": required_sha,
            }
    if gate_id == PHASE_DISPERSION_GATE_ID and row.get("limitations_recorded") is not True:
        return {**base, "status": "limitations_missing"}
    path = row.get("_path")
    if not isinstance(path, str) or not _path_tracked(main_sha, path):
        return {**base, "status": "not_on_main"}
    raw = _git_show(main_sha, path)
    blob_commit = _blob_commit(main_sha, path)
    commit = row.get("verified_at_commit")
    report_hash = None
    status = "not_on_main"
    resolved_from = "none"
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = None
        report_hash = _writer_shaped(payload, raw) if isinstance(payload, Mapping) else None
        case_ids: List[Any] = []
        if isinstance(payload, Mapping) and isinstance(payload.get("results"), list):
            case_ids = [
                item.get("case_id") for item in payload["results"] if isinstance(item, Mapping)
            ]
        decision = row.get("promotion_decision")
        if report_hash is None or case_ids != [gate_id]:
            status = "not_on_main" if report_hash is None else "report_opens_multiple_gates"
        elif row.get("scientific_pass") is True:
            status = "scientific_pass_refused"
            resolved_from = "evidence_promotion_gate_report"
        elif (
            not isinstance(decision, str)
            or decision in _RUNTIME_OUTCOMES
            or decision == "VERIFIED"
            or decision not in ADMISSIBLE_GATE_DECISIONS
        ):
            status = "not_admissible"
            resolved_from = "evidence_promotion_gate_report"
        elif not isinstance(commit, str) or _COMMIT_SHA.fullmatch(commit) is None:
            status = "missing"
            commit = None
        elif not _blob_is_at_or_after(commit, blob_commit, main_sha):
            status = "not_on_main" if commit == main_sha else "not_ancestor"
            resolved_from = "evidence_promotion_gate_report"
        else:
            status = "admissible_on_ancestor"
            resolved_from = "evidence_promotion_gate_report"
    return {
        **base,
        "status": status,
        "verified_at_commit": commit if isinstance(commit, str) else None,
        "resolved_from": resolved_from,
        "report_hash": report_hash,
    }


def _one_case_id_per_report(rows: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """A report blob with more than one case_id opens no gate."""

    grouped: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        path = str(row.get("_path") or "")
        grouped.setdefault(path, []).append(row)
    kept: List[Mapping[str, Any]] = []
    for group in grouped.values():
        case_ids = [row.get("case_id") for row in group]
        if len(set(case_ids)) == 1:
            kept.extend(group)
    return kept


def _resolve_gates_from_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    main_sha: Optional[str],
    git_failure: Optional[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Map each case_id onto one gate. A repeated case_id blocks that gate."""

    rows = _one_case_id_per_report(rows)
    resolved: List[Dict[str, Any]] = []
    for gate_id in BLOCKING_GATE_IDS:
        resolved.append(
            _resolve_one(
                gate_id,
                role="blocking",
                rows=rows,
                main_sha=main_sha,
                git_failure=git_failure,
            )
        )
    for gate_id in NONBLOCKING_GATE_IDS:
        resolved.append(
            _resolve_one(
                gate_id,
                role="nonblocking",
                rows=rows,
                main_sha=main_sha,
                git_failure=git_failure,
            )
        )
    blockers: List[Dict[str, Any]] = []
    for item in resolved:
        if item["role"] != "blocking":
            continue
        status = item["status"]
        gate_id = str(item["gate_id"])
        if status == "admissible_on_ancestor":
            continue
        code = {
            "missing": "missing_gate",
            "not_ancestor": "not_ancestor",
            "not_on_main": "not_on_main",
            "not_admissible": "gate_not_admissible",
            "scientific_pass_refused": "scientific_pass_refused",
            "duplicate_record": "duplicate_gate_record",
            "report_opens_multiple_gates": "report_opens_multiple_gates",
            "ci_discovery_blocked": "ci_discovery_blocked",
            "stale_source": "stale_source",
            "missing_source_sha": "missing_dependency",
            "limitations_missing": "limitations_missing",
        }.get(status, "missing_gate")
        if git_failure is not None:
            code = git_failure
        blockers.append(_blocker(code, f"gate {gate_id} is {status}", gate_id))
    return resolved, blockers


def _resolve_gates() -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str], List[Dict[str, Any]]]:
    """Read writer blobs at local main. ``record_root`` is intentionally absent."""

    git_failure = _git_failure_reason()
    main_sha = None if git_failure else _resolve_main_sha()
    if git_failure or main_sha is None:
        rows: List[Dict[str, Any]] = []
        git_failure = git_failure or "main_unresolved"
    else:
        rows = _load_tracked_rows(main_sha)
    resolved, blockers = _resolve_gates_from_rows(rows, main_sha=main_sha, git_failure=git_failure)
    return resolved, main_sha, git_failure, blockers


def _prepare(
    config: Mapping[str, Any],
    simulation: Optional[Callable[..., Any]],
    *,
    block_reason: str,
) -> tuple:
    _refuse_callback(simulation)
    normalized = _normalize_config(config)
    wilson = _wilson_bound(normalized)
    normalized["sample_size_label"] = _sample_size_label(
        int(normalized["n_positive_calibration"]),
        int(normalized["n_negative_calibration"]),
        int(normalized["n_positive_evaluation"]),
        int(normalized["n_negative_evaluation"]),
    )
    normalized["execution_mode"] = (
        EXECUTION_MODE_SMOKE
        if normalized["sample_size_label"] == UNDERPOWERED_DRY_RUN
        else EXECUTION_MODE_HELD
    )
    normalized["power_analysis_supplied"] = False
    budget = _enforce_budget(normalized)
    payload = _hash_payload(normalized)
    config_hash = compute_config_hash(payload)
    cells = _expand_cells(normalized, block_reason=block_reason)
    if len(cells) != budget["cell_count"]:
        _reject("over_budget", "expanded cell count does not match the budget count")
    cost = _cost_estimate(normalized, budget["cell_count"])
    manifest = _campaign_manifest(normalized, cells, config_hash, cost)
    return normalized, wilson, budget, cells, manifest, config_hash, payload, cost


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
        gate_resolution: Sequence[Mapping[str, Any]],
        provenance: Mapping[str, Any],
        toy_fixture: Mapping[str, Any],
        evidence_hash: Optional[str],
        checked_at: Optional[str],
        caller_gate_decision_rejected: bool,
        test_fixture_label: Optional[str],
        gate_source_failure: Optional[str],
        cost_estimate: Mapping[str, Any],
    ) -> None:
        if run_state not in EMITTED_RUN_STATES:
            _reject("self_declared_state", f"grid_plan_v2 cannot emit run_state {run_state!r}")
        self.schema_version = GRID_PLAN_SCHEMA_VERSION
        self.status_label = HOLD_STATUS
        self.run_state = run_state
        self.config_hash = config_hash
        self.hash_payload = copy.deepcopy(dict(hash_payload))
        self.cell_count = int(budget["cell_count"])
        self.trial_count = int(budget["trial_count"])
        self.compute_units = float(budget["compute_units"])
        self.configuration = {
            key: copy.deepcopy(normalized[key]) for key in sorted(_INPUT_KEYS) if key in normalized
        }
        self.cells = copy.deepcopy(list(cells))
        self.campaign_manifest = manifest
        self.wilson = wilson
        self.threshold_hash = str(normalized["threshold_hash"])
        self.evaluation_manifest = copy.deepcopy(dict(normalized["evaluation_manifest"]))
        self.gate_check = {
            "opened": bool(gate_check["opened"]),
            "blockers": list(gate_check["blockers"]),
            "caller_gate_decision_rejected": bool(
                gate_check.get("caller_gate_decision_rejected", caller_gate_decision_rejected)
            ),
        }
        self.execution = dict(execution)
        self.gate_resolution = copy.deepcopy(list(gate_resolution))
        self.gate_evidence = None
        self.provenance = dict(provenance)
        self.toy_fixture = dict(toy_fixture)
        self.evidence_hash = evidence_hash
        self.checked_at = checked_at
        self.caller_gate_decision_rejected = caller_gate_decision_rejected
        self.test_fixture_label = test_fixture_label
        self.gate_source_failure = gate_source_failure
        self.code_version_id = str(provenance["code_version_id"])
        self.worktree_dirty = bool(provenance["worktree_dirty"])
        self.sample_size_label = str(normalized["sample_size_label"])
        self.execution_mode = str(normalized["execution_mode"])
        self.engineering_minimum_note = ENGINEERING_MINIMUM_NOTE
        self.cost_estimate = copy.deepcopy(dict(cost_estimate))
        self.metric_spec = copy.deepcopy(dict(hash_payload["metric_spec"]))
        self.limits = _limits()
        self.failure_policy = FAILURE_POLICY
        self.planned_outputs = list(PLANNED_OUTPUTS)
        self.detector_roc = None
        if self.execution.get("completed") is True or self.run_state == "completed":
            _reject("self_declared_state", "a validated plan is not a completed run")
        if any(cell.get("blocked") is not True for cell in self.cells):
            _reject("self_declared_state", "grid_plan_v2 cannot emit an unblocked cell")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status_label": self.status_label,
            "run_state": self.run_state,
            "project_status": PROJECT_STATUS,
            "code_version_id": self.code_version_id,
            "worktree_dirty": self.worktree_dirty,
            "config_hash": self.config_hash,
            "config_digest": self.config_hash,
            "execution_mode": self.execution_mode,
            "engineering_minimum_note": self.engineering_minimum_note,
            "threshold_hash": self.threshold_hash,
            "evidence_hash": self.evidence_hash,
            "checked_at": self.checked_at,
            "checked_at_is_caller_set": True,
            "caller_gate_decision_rejected": self.caller_gate_decision_rejected,
            "test_fixture_label": self.test_fixture_label,
            "gate_source_failure": self.gate_source_failure,
            "cell_count": self.cell_count,
            "trial_count": self.trial_count,
            "compute_units": self.compute_units,
            "hash_payload": self.hash_payload,
            "configuration": self.configuration,
            "failure_policy": self.failure_policy,
            "planned_outputs": self.planned_outputs,
            "detector_roc": None,
            "split_plan": {
                "algorithm": SPLIT_ALGORITHM,
                "master_seed": self.configuration["master_seed"],
                "calibration_seed": self.configuration["calibration_seed"],
                "evaluation_seed": self.configuration["evaluation_seed"],
                "calibration_unit_ids": list(self.cells[0]["calibration_unit_ids"]),
                "evaluation_unit_ids": list(self.cells[0]["evaluation_unit_ids"]),
                "roles_are_disjoint": self.cells[0]["roles_are_disjoint"],
                "roles_are_disjoint_is_statistical_independence": False,
                "roles_are_disjoint_note": ROLES_DISJOINT_NOTE,
                "independent_unit": self.configuration["independent_unit"],
                "nested_unit": self.configuration["nested_unit"],
                "nested_per_unit": self.configuration["nested_per_unit"],
                "nested_counted_in_n": False,
            },
            "evaluation_manifest": self.evaluation_manifest,
            "sample_size_label": self.sample_size_label,
            "execution_mode": self.execution_mode,
            "engineering_minimum_note": self.engineering_minimum_note,
            "engineering_threshold_n": ENGINEERING_THRESHOLD_N,
            "power_analysis_supplied": False,
            "engineering_threshold_is_power_guarantee": False,
            "metric_spec": self.metric_spec,
            "would_execute": self.would_execute(),
            "cost_estimate": self.cost_estimate,
            "audit": {
                "project_status": PROJECT_STATUS,
                "status_label": self.status_label,
                "code_version_id": self.code_version_id,
                "worktree_dirty": self.worktree_dirty,
                "config_digest": self.config_hash,
                "seeds": {
                    "master_seed": self.configuration["master_seed"],
                    "calibration_seed": self.configuration["calibration_seed"],
                    "evaluation_seed": self.configuration["evaluation_seed"],
                },
                "calibration_unit_ids": list(self.cells[0]["calibration_unit_ids"]),
                "evaluation_unit_ids": list(self.cells[0]["evaluation_unit_ids"]),
                "sample_size_label": self.sample_size_label,
                "engineering_threshold_n": ENGINEERING_THRESHOLD_N,
                "power_analysis_supplied": False,
                "power_claim": POWER_CLAIM,
                "engineering_threshold_is_power_guarantee": False,
            },
            "cells": self.cells,
            "campaign_manifest": self.campaign_manifest.to_dict(),
            "wilson_bound": _wilson_dict(self.wilson),
            "blocking_gate_ids": list(BLOCKING_GATE_IDS),
            "nonblocking_gate_ids": list(NONBLOCKING_GATE_IDS),
            "gate_integration_state": dict(GATE_INTEGRATION_STATE),
            "gate_evidence": None,
            "gate_resolution": self.gate_resolution,
            "gate_check": self.gate_check,
            "execution": self.execution,
            "provenance": self.provenance,
            "toy_fixture": self.toy_fixture,
            "limits": self.limits,
            "null_model_note": NULL_MODEL_NOTE,
            "required_source_sha": dict(REQUIRED_SOURCE_SHA),
            "open_pr_heads_not_evidence": dict(OPEN_PR_HEADS_NOT_EVIDENCE),
        }

    def would_execute(self) -> Dict[str, Any]:
        """Cells, seeds, splits, and cost that a launch would use. Nothing runs."""

        cell = self.cells[0]
        return {
            "executed": False,
            "execution_mode": self.execution_mode,
            "cells": [
                {
                    "cell_id": item["cell_id"],
                    "cell_index": item["cell_index"],
                    "blocked": True,
                    "null_model_id": item["null_model_id"],
                    "source_model_id": item["source_model_id"],
                }
                for item in self.cells
            ],
            "seeds": {
                "master_seed": self.configuration["master_seed"],
                "calibration_seed": self.configuration["calibration_seed"],
                "evaluation_seed": self.configuration["evaluation_seed"],
            },
            "splits": {
                "calibration_unit_ids": list(cell["calibration_unit_ids"]),
                "evaluation_unit_ids": list(cell["evaluation_unit_ids"]),
                "n_positive_calibration": cell["n_positive_calibration"],
                "n_negative_calibration": cell["n_negative_calibration"],
                "n_positive_evaluation": cell["n_positive_evaluation"],
                "n_negative_evaluation": cell["n_negative_evaluation"],
                "n_independent_calibration": cell["n_independent_calibration"],
                "n_independent_evaluation": cell["n_independent_evaluation"],
                "roles_are_disjoint": cell["roles_are_disjoint"],
            },
            "cost": self.cost_estimate,
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        simulation: Optional[Callable[..., Any]] = None,
        record_root: Optional[Path] = None,
    ) -> "GridPlan":
        """Rebuild from ``configuration``. Stored cells, states, and gate objects are not trusted."""

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
                f"run_state {run_state!r} cannot be declared on a grid_plan_v2 document",
            )
        if "configuration" not in document:
            _reject("unknown_field", "configuration is required")
        execution = document.get("execution") if isinstance(document.get("execution"), Mapping) else {}
        # An execution attempt is re-resolved from writer reports. Stored
        # gate_evidence is not passed through.
        if execution.get("requested") is True or document.get("gate_resolution") not in (None, []):
            plan = execute(
                document["configuration"],
                simulation=simulation,
                checked_at=document.get("checked_at"),
                record_root=record_root,
            )
        else:
            plan = dry_run(document["configuration"], simulation=simulation)
        stored_hash = document.get("config_hash")
        if stored_hash != plan.config_hash:
            _reject(
                "hash_mismatch",
                "stored config_hash does not match compute_config_hash(configuration)",
            )
        return plan


def dry_run(
    config: Mapping[str, Any],
    *,
    simulation: Optional[Callable[..., Any]] = None,
    toy_scores: Any = None,
) -> GridPlan:
    """Validate and list cells. Does not resolve gates and does not execute."""

    normalized, wilson, budget, cells, manifest, config_hash, payload, cost = _prepare(
        config,
        simulation,
        block_reason="dry_run_does_not_resolve_gates",
    )
    main_sha = _resolve_main_sha()
    code_version_id = _code_version_id()
    worktree_dirty = _worktree_dirty() if code_version_id != CODE_VERSION_UNKNOWN else True
    blockers = [
        _blocker(
            "not_checked",
            "dry-run lists cells and does not resolve promotion-gate reports",
        )
    ]
    if code_version_id == CODE_VERSION_UNKNOWN:
        blockers.append(
            _blocker(
                "code_version_unknown",
                "HEAD did not resolve; code_version_id is UNKNOWN and the plan stays closed",
            )
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
            "blockers": blockers,
            "caller_gate_decision_rejected": False,
        },
        execution={
            "requested": False,
            "refused": False,
            "refusal_reasons": [],
            "simulation_invoked": False,
            "launched": False,
            "completed": False,
            "reason": "dry-run does not execute",
            "sweep_reachable": False,
            "executed": False,
            "aborted": False,
            "abort_gate": None,
            "partial_launch": False,
        },
        gate_resolution=[],
        provenance=_provenance(main_sha, code_version_id, config_hash, worktree_dirty),
        toy_fixture=_toy_fixture(toy_scores),
        evidence_hash=None,
        checked_at=None,
        caller_gate_decision_rejected=False,
        test_fixture_label=None,
        gate_source_failure=None,
        cost_estimate=cost,
    )


def execute(
    config: Mapping[str, Any],
    gate_evidence: Any = _CALLER_GATE_DECISION,
    *,
    simulation: Optional[Callable[..., Any]] = None,
    checked_at: Any = None,
    record_root: Optional[os.PathLike[str] | str] = None,
) -> GridPlan:
    """Resolve gates from promotion-gate blobs on local main.

    ``gate_evidence`` is accepted only so a fabricated decision can be
    rejected. It is not read. ``checked_at`` is stored as caller-set text
    and is not a freshness proof. ``record_root``, when it is a path, labels
    the plan ``TEST_FIXTURE_NOT_EVIDENCE``. The path is not opened and cannot
    make a gate ``admissible_on_ancestor``. Reports are read only from git
    blobs at paths ``write_report`` uses by default. This function does not
    write a registry and does not call ``simulation``.
    """

    caller_rejected = gate_evidence is not _CALLER_GATE_DECISION
    if record_root is not None and not isinstance(record_root, (str, os.PathLike)):
        _reject("invalid_record_root", "record_root must be a directory path")
    if record_root is not None:
        _reject_locked_inputs(os.fspath(record_root), label="record_root")
    test_fixture_label = None if record_root is None else TEST_FIXTURE_NOT_EVIDENCE
    normalized, wilson, budget, cells, manifest, config_hash, payload, cost = _prepare(
        config,
        simulation,
        block_reason="blocking_gates_unresolved",
    )
    resolved, main_sha, git_failure, blockers = _resolve_gates()
    code_version_id = _code_version_id()
    blockers = list(blockers)
    worktree_dirty = False
    if git_failure is None:
        worktree_dirty = _worktree_dirty()
        if code_version_id == CODE_VERSION_UNKNOWN:
            blockers.append(
                _blocker(
                    "code_version_unknown",
                    "HEAD did not resolve; code_version_id is UNKNOWN and the plan stays closed",
                )
            )
        if worktree_dirty:
            blockers.append(
                _blocker(
                    "dirty_worktree",
                    "worktree is dirty; code_version_id is not a clean HEAD and the plan stays closed",
                )
            )
    aborted = False
    abort_gate = None
    for item in resolved:
        if item["role"] != "blocking":
            continue
        if item["status"] != "admissible_on_ancestor":
            aborted = True
            abort_gate = str(item["gate_id"])
            break
    gates_clear = code_version_id != CODE_VERSION_UNKNOWN and not blockers and all(
        item["status"] == "admissible_on_ancestor"
        for item in resolved
        if item["role"] == "blocking"
    )
    # No sweep exists in this module. Gate rows cannot unlock cells.
    opened = False
    cell_reason = "grid_plan_does_not_launch" if gates_clear else "blocking_gates_unresolved"
    for cell in cells:
        cell["blocked"] = True
        cell["evaluation_eligible"] = False
        cell["block_reason"] = cell_reason
        cell["parameter_case"]["blocked"] = True
        cell["parameter_case"]["executable"] = False
        cell["parameter_case"]["block_reason"] = cell_reason
    evidence_hash = compute_config_hash(
        {
            "main_sha": main_sha,
            "git_failure": git_failure,
            "resolution": [
                {
                    "gate_id": item["gate_id"],
                    "status": item["status"],
                    "verified_at_commit": item.get("verified_at_commit"),
                }
                for item in resolved
            ],
        }
    )
    checked_text = checked_at if isinstance(checked_at, str) else None
    execution = {
        "requested": True,
        "refused": not opened,
        "refusal_reasons": list(blockers),
        "simulation_invoked": False,
        "launched": False,
        "completed": False,
        "reason": _REFUSAL_REASON,
        "sweep_reachable": False,
        "caller_gate_decision_rejected": caller_rejected,
        "checked_at_is_caller_set": True,
        "executed": False,
        "aborted": aborted,
        "abort_gate": abort_gate,
        "partial_launch": False,
    }
    return GridPlan(
        normalized=normalized,
        budget=budget,
        wilson=wilson,
        cells=cells,
        manifest=manifest,
        config_hash=config_hash,
        hash_payload=payload,
        run_state="blocked" if not opened else "planned",
        gate_check={
            "opened": opened,
            "blockers": blockers,
            "caller_gate_decision_rejected": caller_rejected,
        },
        execution=execution,
        gate_resolution=resolved,
        provenance=_provenance(main_sha, code_version_id, config_hash, worktree_dirty),
        toy_fixture=_toy_fixture(None),
        evidence_hash=evidence_hash,
        checked_at=checked_text,
        caller_gate_decision_rejected=caller_rejected,
        test_fixture_label=test_fixture_label,
        gate_source_failure=git_failure,
        cost_estimate=cost,
    )


__all__ = [
    "ABSOLUTE_MAX_CELLS",
    "ABSOLUTE_MAX_TRIALS",
    "ADMISSIBLE_GATE_DECISIONS",
    "AUDITED_MAIN_SHA",
    "BLOCKING_GATE_IDS",
    "CAMPAIGN_MANIFEST_SCHEMA_VERSION",
    "EMITTED_RUN_STATES",
    "FAILURE_POLICY",
    "GATE_INTEGRATION_STATE",
    "GENERATOR",
    "GRID_PLAN_SCHEMA_VERSION",
    "HOLD_STATUS",
    "NONBLOCKING_GATE_IDS",
    "NULL_MODEL_IDS",
    "NULL_MODEL_NOTE",
    "CODE_VERSION_UNKNOWN",
    "DECLARED_BYTES_PER_RECORD",
    "DECLARED_ESTIMATE",
    "ENGINEERING_MINIMUM_NOTE",
    "ENGINEERING_THRESHOLD_MET",
    "ENGINEERING_THRESHOLD_N",
    "EXECUTION_MODE_HELD",
    "EXECUTION_MODE_SMOKE",
    "OPEN_PR_HEADS_NOT_EVIDENCE",
    "REQUIRED_SOURCE_SHA",
    "POWER_CLAIM",
    "PROJECT_STATUS",
    "REQUIRED_GATE_IDS",
    "ROC_API_HEAD",
    "ROC_API_PR",
    "UNDERPOWERED_DRY_RUN",
    "RUN_STATES",
    "SOURCE_MODEL_IDS",
    "SPLIT_ALGORITHM",
    "TEST_FIXTURE_NOT_EVIDENCE",
    "TOY_FIXTURE_LABEL",
    "GridPlan",
    "GridPlanError",
    "compute_config_hash",
    "dry_run",
    "execute",
]
