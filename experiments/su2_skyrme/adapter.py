"""Thin adapter to an optional ``field_theory.su2`` solver.

This module never duplicates Skyrme energy, gradient, charge, or evolution
mathematics. When the solver package is absent or a requested backend cannot
be imported, diagnostics are labeled ``unavailable``.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Optional

from .result_contract import TaggedValue, computed, unavailable
from .schema import ExperimentConfig


@dataclass(frozen=True)
class SolverCapabilities:
    package_available: bool
    nearest_neighbor: bool
    constrained_pair: bool
    lorentzian: bool
    generators: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_available": self.package_available,
            "nearest_neighbor": self.nearest_neighbor,
            "constrained_pair": self.constrained_pair,
            "lorentzian": self.lorentzian,
            "generators": self.generators,
            "detail": self.detail,
            "epistemic_tag": "computed",
        }


@dataclass
class AdapterOutput:
    backend_resolved: str
    solver_available: bool
    status: str
    termination: Optional[str]
    iterations: Optional[int]
    diagnostics: dict[str, TaggedValue]
    missing_data: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def diagnostics_dict(self) -> dict[str, Any]:
        return {key: value.to_dict() for key, value in self.diagnostics.items()}


def probe_solver_capabilities() -> SolverCapabilities:
    """Import-probe the optional solver package without executing math."""
    try:
        su2 = importlib.import_module("field_theory.su2")
    except Exception as exc:  # noqa: BLE001 - honest availability reporting
        return SolverCapabilities(
            package_available=False,
            nearest_neighbor=False,
            constrained_pair=False,
            lorentzian=False,
            generators=False,
            detail=f"field_theory.su2 unavailable: {type(exc).__name__}: {exc}",
        )

    def _has(module_name: str, attr: str) -> bool:
        try:
            module = importlib.import_module(module_name)
            return hasattr(module, attr)
        except Exception:
            return False

    return SolverCapabilities(
        package_available=True,
        nearest_neighbor=_has(
            "field_theory.su2.nearest_neighbor",
            "relax_skyrme_field_nearest_neighbor",
        ),
        constrained_pair=_has(
            "field_theory.su2.constrained_interaction",
            "run_constrained_two_hedgehog_relaxation",
        ),
        lorentzian=_has("field_theory.su2.lorentzian", "evolve_lorentzian_skyrme"),
        generators=hasattr(su2, "hedgehog") or _has("field_theory.su2.generators", "hedgehog"),
        detail="field_theory.su2 import succeeded",
    )


def resolve_backend(requested: str, caps: SolverCapabilities) -> str:
    if requested == "unavailable_stub":
        return "unavailable_stub"
    if requested == "auto":
        if caps.nearest_neighbor:
            return "nearest_neighbor"
        if caps.constrained_pair:
            return "constrained_pair"
        if caps.lorentzian:
            return "lorentzian"
        return "unavailable_stub"
    return requested


def _unavailable_bundle(reason: str) -> dict[str, TaggedValue]:
    names = (
        "energy_total",
        "energy_history",
        "topological_charge",
        "topological_charge_history",
        "raw_gradient_norm",
        "continuum_l2_residual",
        "stationarity_status",
        "curvature_assessment",
    )
    return {
        name: unavailable(name, reason=reason, epistemic_tag="assumed")
        for name in names
    }


def _build_initial_field(config: ExperimentConfig):
    """Construct an initial SU2GridField via the external generators module."""
    generators = importlib.import_module("field_theory.su2.generators")
    shape = config.discretization.shape
    spacing = config.discretization.spacing
    length_unit = config.discretization.length_unit
    boundary = config.boundary_conditions
    ic = config.initial_condition

    if ic.kind == "vacuum":
        return generators.vacuum(
            shape,
            spacing=spacing,
            boundary=boundary,
            length_unit=length_unit,
        )
    if ic.kind == "hedgehog":
        return generators.hedgehog(
            shape,
            radius=float(ic.radius if ic.radius is not None else 1.0),
            spacing=spacing,
            length_unit=length_unit,
        )
    if ic.kind == "fixed_axis":
        import numpy as np

        theta = float(ic.theta if ic.theta is not None else 0.0)
        theta_field = np.full(shape, theta, dtype=float)
        return generators.fixed_axis(
            theta_field,
            axis=ic.axis if ic.axis is not None else (0.0, 0.0, 1.0),
            spacing=spacing,
            boundary=boundary,
            length_unit=length_unit,
        )
    raise ValueError(f"unsupported initial_condition.kind: {ic.kind}")


def _run_nearest_neighbor(config: ExperimentConfig) -> AdapterOutput:
    nn = importlib.import_module("field_theory.su2.nearest_neighbor")
    relax = nn.relax_skyrme_field_nearest_neighbor
    initial = _build_initial_field(config)
    result = relax(
        initial,
        f_pi=config.model.f_pi,
        e=config.model.e,
        vacuum=config.model.vacuum,
        max_iterations=config.solver.max_iterations,
        initial_step=config.solver.initial_step,
        gradient_tolerance=config.solver.gradient_tolerance,
        max_backtracks=config.solver.max_backtracks,
        stationarity_metric=config.solver.stationarity_metric,
    )
    energy_history = list(getattr(result, "energy_history", ()))
    charge_history = list(getattr(result, "topological_charge_history", ()))
    termination = str(getattr(result, "termination", "unknown"))
    iterations = int(getattr(result, "iterations", 0))
    diagnostics = {
        "energy_total": computed(
            energy_history[-1] if energy_history else None,
            units="dimensionless_model_energy",
            note="final entry of solver energy_history",
        ),
        "energy_history": computed(
            energy_history,
            units="dimensionless_model_energy",
            note="solver energy_history",
        ),
        "topological_charge": computed(
            charge_history[-1] if charge_history else None,
            units="dimensionless_finite_grid_charge",
            note="finite-grid approximation; not an integer-sector proof",
        ),
        "topological_charge_history": computed(
            charge_history,
            units="dimensionless_finite_grid_charge",
            note="finite-grid charge trajectory",
        ),
        "raw_gradient_norm": computed(
            float(getattr(result, "raw_gradient_norm", float("nan"))),
            units="dimensionless",
            note="solver raw gradient norm",
        ),
        "continuum_l2_residual": computed(
            float(getattr(result, "continuum_l2_residual", float("nan"))),
            units="dimensionless",
            note="finite-grid residual diagnostic",
        ),
        "stationarity_status": computed(
            str(getattr(result, "stationarity_status", "not_established")),
            units="label",
            note="solver-reported stationarity label",
        ),
        "curvature_assessment": computed(
            None
            if getattr(result, "curvature_diagnostics", None) is None
            else str(getattr(result.curvature_diagnostics, "assessment", None)),
            units="label",
            note="optional curvature probe assessment",
        ),
    }
    status = "completed"
    if termination == "gradient_tolerance":
        status = "converged"
    elif termination in {"iteration_limit", "line_search_stalled"}:
        status = termination
    return AdapterOutput(
        backend_resolved="nearest_neighbor",
        solver_available=True,
        status=status,
        termination=termination,
        iterations=iterations,
        diagnostics=diagnostics,
        raw={
            "minimum_certified": bool(getattr(result, "minimum_certified", False)),
            "active_site_count": getattr(result, "active_site_count", None),
            "cell_volume": getattr(result, "cell_volume", None),
        },
    )


def _run_unavailable(config: ExperimentConfig, *, reason: str, backend: str) -> AdapterOutput:
    diagnostics = _unavailable_bundle(reason)
    missing = sorted(diagnostics.keys())
    return AdapterOutput(
        backend_resolved=backend,
        solver_available=False,
        status="completed_with_unavailable_solver",
        termination=None,
        iterations=None,
        diagnostics=diagnostics,
        missing_data=missing,
        failures=[],
        raw={"reason": reason, "requested_backend": config.solver.backend},
    )


def run_adapter(config: ExperimentConfig) -> AdapterOutput:
    """Execute one configured solve through the optional solver package."""
    caps = probe_solver_capabilities()
    backend = resolve_backend(config.solver.backend, caps)

    if backend == "unavailable_stub" or not caps.package_available:
        return _run_unavailable(
            config,
            reason=caps.detail or "solver package unavailable",
            backend="unavailable_stub",
        )

    try:
        if backend == "nearest_neighbor":
            if not caps.nearest_neighbor:
                return _run_unavailable(
                    config,
                    reason="nearest_neighbor backend symbols unavailable",
                    backend="unavailable_stub",
                )
            return _run_nearest_neighbor(config)

        if backend == "constrained_pair":
            # Constrained-pair runs require richer multi-soliton inputs owned by
            # the solver lane. This experiment layer records unavailability
            # rather than inventing pair geometry.
            return _run_unavailable(
                config,
                reason=(
                    "constrained_pair backend is detected but not wired by this "
                    "experiment runner; pair geometry remains solver-owned"
                ),
                backend="constrained_pair",
            )

        if backend == "lorentzian":
            return _run_unavailable(
                config,
                reason=(
                    "lorentzian backend is detected but evolution ICs/velocity "
                    "setup remain solver-owned; experiment runner does not fabricate them"
                ),
                backend="lorentzian",
            )

        return _run_unavailable(
            config,
            reason=f"unsupported backend {backend!r}",
            backend=backend,
        )
    except Exception as exc:  # noqa: BLE001 - map solver failures into contract
        diagnostics = _unavailable_bundle(f"solver raised {type(exc).__name__}")
        return AdapterOutput(
            backend_resolved=backend,
            solver_available=True,
            status="numerical_failure",
            termination="numerical_failure",
            iterations=None,
            diagnostics={
                **diagnostics,
                "exception_type": computed(
                    type(exc).__name__,
                    units="label",
                    note="exception class from solver adapter call",
                ),
            },
            missing_data=sorted(k for k, v in diagnostics.items() if v.availability != "available"),
            failures=[f"{type(exc).__name__}: {exc}"],
            raw={"exception": f"{type(exc).__name__}: {exc}"},
        )
