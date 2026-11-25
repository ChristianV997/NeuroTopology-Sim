"""Deterministic experiment and parameter-grid runner for SU(2)/Skyrme."""

from __future__ import annotations

import hashlib
import itertools
import json
from typing import Any, Iterator

from .adapter import (
    AdapterRunPayload,
    SolverBackend,
    SolverUnavailableError,
    get_backend,
    request_from_config,
)
from .provenance import build_provenance
from .result_contract import (
    ExperimentResultV1,
    QuantityRecord,
    quantity,
    unavailable_quantity,
)
from .schema import ExperimentConfig, ExperimentConfigError


def _result_id(config: ExperimentConfig, provenance_hash: str, point_key: str = "") -> str:
    basis = {
        "experiment_id": config.experiment_id,
        "mode": config.mode,
        "config_sha256": provenance_hash,
        "point_key": point_key,
    }
    encoded = json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _map_status(payload: AdapterRunPayload) -> str:
    termination = (payload.raw_termination or payload.status or "").lower()
    if termination in {"gradient_tolerance", "converged"}:
        return "converged"
    if termination in {"iteration_limit"}:
        return "iteration_limit"
    if termination in {"line_search_stalled"}:
        return "line_search_stalled"
    if termination in {"completed"}:
        return "completed"
    if termination in {"numerical_failure", "failed"}:
        return "numerical_failure"
    return payload.status if payload.status in {
        "completed",
        "converged",
        "iteration_limit",
        "line_search_stalled",
        "failed",
        "solver_unavailable",
        "invalid_config",
        "numerical_failure",
    } else "failed"


def _evidence_for_backend(backend_name: str) -> str:
    if backend_name.startswith("stub"):
        return "assumed"
    return "computed"


def _diagnostics_from_payload(payload: AdapterRunPayload) -> list[QuantityRecord]:
    evidence = _evidence_for_backend(payload.backend)
    records: list[QuantityRecord] = []
    mapping = {
        "final_energy_total": (
            "Finite-grid static energy total from nearest-neighbor objective; "
            "not a physical binding energy."
        ),
        "final_total_energy": (
            "Finite-grid Lorentzian Hamiltonian snapshot; RK4 is not exactly "
            "energy-preserving."
        ),
        "final_approximate_topological_charge": (
            "Approximate lattice topological charge diagnostic; not an integer-sector proof "
            "and not a consciousness score."
        ),
        "iterations": "Accepted optimizer iterations.",
        "raw_gradient_norm": "Euclidean free-site gradient norm.",
        "continuum_l2_residual": "Mesh-aware residual diagnostic on uniform Cartesian cells.",
        "active_l2_measure": "Lumped free-site measure N_free * V_c.",
        "active_l2_rms_residual": "RMS residual over free sites.",
        "stationarity_status": "First-order stationarity label from solver; not a minimum certificate.",
        "minimum_certified": "Solver reports whether a minimum is certified (expected false).",
        "cell_volume": "Uniform cell volume h_x*h_y*h_z.",
        "active_site_count": "Count of free lattice sites.",
        "max_unit_norm_error": "Constraint drift on |n|=1.",
        "max_tangency_error": "Velocity tangency constraint residual.",
        "linearized_cfl_indicator": "Vacuum-linearized CFL indicator; not nonlinear stability.",
        "hyperbolicity_status": "Hyperbolicity is not certified by this solver.",
        "steps": "Completed evolution steps.",
        "dt": "Integrator time step (dimensionless unless caller unitized).",
    }
    for name, notes in mapping.items():
        if name in payload.diagnostics:
            records.append(
                quantity(
                    name,
                    payload.diagnostics[name],
                    evidence=evidence,  # type: ignore[arg-type]
                    notes=notes
                    + (
                        " Stub-backend synthetic value."
                        if evidence == "assumed"
                        else ""
                    ),
                )
            )

    # Always surface speculative / unavailable scientific claims as explicit records.
    records.append(
        unavailable_quantity(
            "physical_energy_si",
            "Physical SI energy conversion is not_assessed by this experiment layer.",
        )
    )
    records.append(
        quantity(
            "continuum_energy_extrapolation",
            None,
            evidence="speculative",
            notes=(
                "Continuum-limit energy extrapolation from a single finite grid is "
                "not performed; any such mapping would be speculative and is left null."
            ),
        )
    )
    records.append(
        QuantityRecord(
            name="consciousness_metric",
            value=None,
            evidence="unavailable",
            notes="Forbidden interpretation; topological diagnostics are not consciousness scores.",
            availability="unavailable",
        )
    )
    if payload.field_checksum is not None:
        records.append(
            quantity(
                "final_field_checksum_sha256",
                payload.field_checksum,
                evidence=evidence,  # type: ignore[arg-type]
                units="sha256-hex",
                notes="Checksum of final field components + metadata.",
            )
        )
    return records


def _base_result(
    config: ExperimentConfig,
    *,
    status: str,
    provenance: dict[str, Any],
    backend_name: str,
    api_status: str,
    diagnostics: list[QuantityRecord] | None = None,
    points: list[dict[str, Any]] | None = None,
    failure_message: str | None = None,
    point_key: str = "",
) -> ExperimentResultV1:
    return ExperimentResultV1(
        result_id=_result_id(config, provenance["config_sha256"], point_key=point_key),
        experiment_id=config.experiment_id,
        mode=config.mode,
        status=status,  # type: ignore[arg-type]
        config=config.to_dict(),
        provenance=provenance,
        discretization=config.discretization.to_dict(),
        boundary_conditions={
            "boundary": config.discretization.boundary,
            "length_unit": config.discretization.length_unit,
            "fixed_mask": "unavailable",
        },
        initial_condition=config.initial_condition.to_dict(),
        model_settings=config.model.to_dict(),
        solver_settings=config.solver.to_dict(),
        diagnostics=diagnostics or [],
        points=points or [],
        solver_backend=backend_name,
        solver_api_status=api_status,
        failure_message=failure_message,
    )


def iter_sweep_points(config: ExperimentConfig) -> Iterator[dict[str, Any]]:
    """Yield Cartesian product points for a sweep config."""
    if config.sweep is None:
        yield {}
        return
    axes = config.sweep
    f_pi_vals = axes.f_pi
    e_vals = axes.e
    max_iter_vals = axes.max_iterations
    step_vals = axes.initial_step
    dt_vals = axes.dt if axes.dt is not None else (None,)
    steps_vals = axes.steps if axes.steps is not None else (None,)
    for f_pi, e, max_iterations, initial_step, dt, steps in itertools.product(
        f_pi_vals, e_vals, max_iter_vals, step_vals, dt_vals, steps_vals
    ):
        point: dict[str, Any] = {
            "f_pi": f_pi,
            "e": e,
            "max_iterations": max_iterations,
            "initial_step": initial_step,
        }
        if dt is not None:
            point["dt"] = dt
        if steps is not None:
            point["steps"] = steps
        yield point


def run_experiment(
    config: ExperimentConfig,
    *,
    backend: SolverBackend | None = None,
    allow_stub: bool = False,
    repo_root: str | None = None,
    created_at=None,
) -> ExperimentResultV1:
    """Execute one deterministic experiment (single point or full sweep)."""
    provenance = build_provenance(
        config, repo_root=repo_root, created_at=created_at
    ).to_dict()

    try:
        active_backend = backend or get_backend(prefer_live=True, allow_stub=allow_stub)
    except SolverUnavailableError as exc:
        return _base_result(
            config,
            status="solver_unavailable",
            provenance=provenance,
            backend_name="unavailable",
            api_status="unavailable",
            diagnostics=[
                unavailable_quantity("solver_output", str(exc)),
                QuantityRecord(
                    name="consciousness_metric",
                    value=None,
                    evidence="unavailable",
                    notes="Forbidden interpretation.",
                    availability="unavailable",
                ),
            ],
            failure_message=str(exc),
        )

    if config.mode == "nearest_neighbor_sweep" or (
        config.mode == "lorentzian_evolve" and config.sweep is not None
    ):
        return run_parameter_sweep(
            config,
            backend=active_backend,
            allow_stub=allow_stub,
            repo_root=repo_root,
            provenance=provenance,
            created_at=created_at,
        )

    request = request_from_config(config)
    try:
        payload = active_backend.run(request)
    except SolverUnavailableError as exc:
        return _base_result(
            config,
            status="solver_unavailable",
            provenance=provenance,
            backend_name=getattr(active_backend, "name", "unavailable"),
            api_status="unavailable",
            failure_message=str(exc),
            diagnostics=[unavailable_quantity("solver_output", str(exc))],
        )
    except Exception as exc:  # noqa: BLE001 - convert solver failures into result status
        return _base_result(
            config,
            status="failed",
            provenance=provenance,
            backend_name=getattr(active_backend, "name", "unknown"),
            api_status="error",
            failure_message=f"{type(exc).__name__}: {exc}",
            diagnostics=[unavailable_quantity("solver_output", f"{type(exc).__name__}: {exc}")],
        )

    return _base_result(
        config,
        status=_map_status(payload),
        provenance=provenance,
        backend_name=payload.backend,
        api_status="available" if not payload.backend.startswith("stub") else "stub",
        diagnostics=_diagnostics_from_payload(payload),
        points=[
            {
                "point_id": "point-0000",
                "parameters": {},
                "status": _map_status(payload),
                "diagnostics": {
                    item.name: item.to_dict() for item in _diagnostics_from_payload(payload)
                },
                "histories": payload.histories,
            }
        ],
        failure_message=payload.message,
    )


def run_parameter_sweep(
    config: ExperimentConfig,
    *,
    backend: SolverBackend | None = None,
    allow_stub: bool = False,
    repo_root: str | None = None,
    provenance: dict[str, Any] | None = None,
    created_at=None,
) -> ExperimentResultV1:
    """Run an ordered Cartesian parameter sweep with stable point ids."""
    if config.mode == "nearest_neighbor_sweep" and config.sweep is None:
        raise ExperimentConfigError("nearest_neighbor_sweep requires sweep axes")

    provenance_payload = provenance or build_provenance(
        config, repo_root=repo_root, created_at=created_at
    ).to_dict()
    try:
        active_backend = backend or get_backend(prefer_live=True, allow_stub=allow_stub)
    except SolverUnavailableError as exc:
        return _base_result(
            config,
            status="solver_unavailable",
            provenance=provenance_payload,
            backend_name="unavailable",
            api_status="unavailable",
            failure_message=str(exc),
            diagnostics=[unavailable_quantity("solver_output", str(exc))],
        )

    points: list[dict[str, Any]] = []
    aggregate_diagnostics: list[QuantityRecord] = []
    statuses: list[str] = []

    for index, sweep_point in enumerate(iter_sweep_points(config)):
        request = request_from_config(config, sweep_point=sweep_point)
        # For sweep mode, force the adapter into a relax/evolve request mode.
        if config.mode == "nearest_neighbor_sweep":
            from dataclasses import replace

            request = replace(request, mode="nearest_neighbor_relax")
        try:
            payload = active_backend.run(request)
            status = _map_status(payload)
            point_diagnostics = _diagnostics_from_payload(payload)
            points.append(
                {
                    "point_id": f"point-{index:04d}",
                    "parameters": sweep_point,
                    "status": status,
                    "diagnostics": {
                        item.name: item.to_dict() for item in point_diagnostics
                    },
                    "histories": payload.histories,
                }
            )
            statuses.append(status)
        except Exception as exc:  # noqa: BLE001
            points.append(
                {
                    "point_id": f"point-{index:04d}",
                    "parameters": sweep_point,
                    "status": "failed",
                    "diagnostics": {},
                    "histories": {},
                    "failure_message": f"{type(exc).__name__}: {exc}",
                }
            )
            statuses.append("failed")

    if not statuses:
        overall = "failed"
    elif all(status == "converged" for status in statuses):
        overall = "converged"
    elif all(status in {"completed", "converged"} for status in statuses):
        overall = "completed"
    elif any(status == "failed" for status in statuses):
        overall = "failed"
    else:
        overall = statuses[0]

    aggregate_diagnostics.append(
        quantity(
            "sweep_point_count",
            len(points),
            evidence="computed",
            units="count",
            notes="Number of Cartesian sweep points executed.",
        )
    )
    aggregate_diagnostics.append(
        quantity(
            "continuum_energy_extrapolation",
            None,
            evidence="speculative",
            notes=(
                "Continuum-limit energy extrapolation across sweep points is not "
                "performed; any such mapping would be speculative and is left null."
            ),
        )
    )
    aggregate_diagnostics.append(
        QuantityRecord(
            name="consciousness_metric",
            value=None,
            evidence="unavailable",
            notes="Forbidden interpretation across all sweep points.",
            availability="unavailable",
        )
    )

    return _base_result(
        config,
        status=overall,  # type: ignore[arg-type]
        provenance=provenance_payload,
        backend_name=getattr(active_backend, "name", "unknown"),
        api_status="available"
        if not str(getattr(active_backend, "name", "")).startswith("stub")
        else "stub",
        diagnostics=aggregate_diagnostics,
        points=points,
    )
