"""Thin adapter over the public ``field_theory.su2`` solver API.

This module intentionally contains **no** Skyrme mathematics. When the solver
package is absent (typical on base branches that have not merged PRs #466/#468),
availability is reported explicitly and callers may inject a test double that
implements ``SolverBackend``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from .schema import DiscretizationConfig, ExperimentConfig, InitialConditionConfig, ModelConfig, SolverSettings

SolverMode = Literal[
    "nearest_neighbor_relax",
    "nearest_neighbor_sweep",
    "lorentzian_evolve",
]


@dataclass(frozen=True)
class SolverAvailability:
    import_status: Literal["available", "unavailable"]
    module_path: str
    public_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    notes: str
    dependency_blocker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "import_status": self.import_status,
            "module_path": self.module_path,
            "public_symbols": list(self.public_symbols),
            "missing_symbols": list(self.missing_symbols),
            "notes": self.notes,
            "dependency_blocker": self.dependency_blocker,
        }


REQUIRED_RELAX_SYMBOLS = (
    "SU2GridField",
    "vacuum",
    "hedgehog",
    "relax_skyrme_field_nearest_neighbor",
)

REQUIRED_LORENTZIAN_SYMBOLS = (
    "SU2GridField",
    "vacuum",
    "hedgehog",
    "evolve_lorentzian_skyrme",
)

OPTIONAL_SWEEP_SYMBOLS = (
    "NearestNeighborSweepSpec",
    "run_nearest_neighbor_sweep",
)


def probe_solver_availability() -> SolverAvailability:
    """Inspect whether the live SU(2) solver public API can be imported."""
    missing: list[str] = []
    found: list[str] = []
    blocker = (
        "field_theory.su2 is not present on this working tree. Live solver code "
        "currently lives on draft PRs "
        "https://github.com/ChristianV997/NeuroTopology-Sim/pull/466 "
        "(nearest-neighbor / constrained / parameter_sweep) and "
        "https://github.com/ChristianV997/NeuroTopology-Sim/pull/468 "
        "(lorentzian Skyrme evolution). Merge or install those modules before "
        "running non-stub experiments."
    )
    try:
        import field_theory.su2 as su2  # type: ignore
    except Exception as exc:  # noqa: BLE001 - availability probe must never crash callers
        missing_on_import = tuple(
            dict.fromkeys(REQUIRED_RELAX_SYMBOLS + REQUIRED_LORENTZIAN_SYMBOLS)
        )
        return SolverAvailability(
            import_status="unavailable",
            module_path="field_theory.su2",
            public_symbols=tuple(),
            missing_symbols=missing_on_import,
            notes=f"import failed: {type(exc).__name__}: {exc}",
            dependency_blocker=blocker,
        )

    # Resolve nested public callables that may not be re-exported from __init__.
    symbol_sources: dict[str, Any] = {
        "SU2GridField": getattr(su2, "SU2GridField", None),
        "vacuum": getattr(su2, "vacuum", None),
        "hedgehog": getattr(su2, "hedgehog", None),
    }
    try:
        from field_theory.su2.nearest_neighbor import (  # type: ignore
            relax_skyrme_field_nearest_neighbor,
        )

        symbol_sources["relax_skyrme_field_nearest_neighbor"] = (
            relax_skyrme_field_nearest_neighbor
        )
    except Exception:
        symbol_sources["relax_skyrme_field_nearest_neighbor"] = None

    try:
        from field_theory.su2.lorentzian import evolve_lorentzian_skyrme  # type: ignore

        symbol_sources["evolve_lorentzian_skyrme"] = evolve_lorentzian_skyrme
    except Exception:
        symbol_sources["evolve_lorentzian_skyrme"] = getattr(
            su2, "evolve_lorentzian_skyrme", None
        )

    try:
        from field_theory.su2.parameter_sweep import (  # type: ignore
            NearestNeighborSweepSpec,
            run_nearest_neighbor_sweep,
        )

        symbol_sources["NearestNeighborSweepSpec"] = NearestNeighborSweepSpec
        symbol_sources["run_nearest_neighbor_sweep"] = run_nearest_neighbor_sweep
    except Exception:
        symbol_sources["NearestNeighborSweepSpec"] = None
        symbol_sources["run_nearest_neighbor_sweep"] = None

    for name, value in symbol_sources.items():
        if value is None:
            missing.append(name)
        else:
            found.append(name)

    status: Literal["available", "unavailable"]
    if all(symbol_sources.get(name) is not None for name in REQUIRED_RELAX_SYMBOLS):
        status = "available"
        notes = "nearest-neighbor relax API importable"
        dep = None
    else:
        status = "unavailable"
        notes = "required relax symbols missing after import"
        dep = blocker

    lorentzian_ok = all(
        symbol_sources.get(name) is not None for name in REQUIRED_LORENTZIAN_SYMBOLS
    )
    if status == "available" and not lorentzian_ok:
        notes += "; lorentzian evolve API unavailable (PR #468 not present)"

    return SolverAvailability(
        import_status=status,
        module_path="field_theory.su2",
        public_symbols=tuple(found),
        missing_symbols=tuple(missing),
        notes=notes,
        dependency_blocker=dep,
    )


@dataclass(frozen=True)
class AdapterRunRequest:
    mode: SolverMode
    discretization: DiscretizationConfig
    initial_condition: InitialConditionConfig
    model: ModelConfig
    solver: SolverSettings
    seed: int
    sweep_point: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterRunPayload:
    """Normalized solver payload used by the experiment runner."""

    status: str
    backend: str
    diagnostics: dict[str, Any]
    histories: dict[str, list[Any]]
    raw_termination: str | None = None
    message: str | None = None
    field_checksum: str | None = None


@runtime_checkable
class SolverBackend(Protocol):
    name: str

    def run(self, request: AdapterRunRequest) -> AdapterRunPayload:
        ...


class SolverUnavailableError(RuntimeError):
    """Raised when a live solver call is requested but the API is missing."""


class LiveSolverBackend:
    """Adapter that imports and calls the public solver API only."""

    name = "field_theory.su2"

    def __init__(self) -> None:
        self.availability = probe_solver_availability()
        if self.availability.import_status != "available":
            raise SolverUnavailableError(
                self.availability.dependency_blocker
                or self.availability.notes
            )

    def run(self, request: AdapterRunRequest) -> AdapterRunPayload:
        from field_theory.su2 import hedgehog, vacuum  # type: ignore

        disc = request.discretization
        ic = request.initial_condition
        if ic.kind == "vacuum":
            field = vacuum(
                disc.shape,
                spacing=disc.spacing,
                boundary=disc.boundary,
                length_unit=disc.length_unit,
            )
        elif ic.kind == "hedgehog":
            field = hedgehog(
                disc.shape,
                radius=float(ic.radius),
                spacing=disc.spacing,
                length_unit=disc.length_unit,
            )
        else:  # pragma: no cover - schema rejects other kinds
            raise ValueError(f"unsupported IC kind: {ic.kind}")

        if request.mode in {"nearest_neighbor_relax", "nearest_neighbor_sweep"}:
            return self._run_relax(field, request)
        if request.mode == "lorentzian_evolve":
            return self._run_lorentzian(field, request)
        raise ValueError(f"unsupported mode: {request.mode}")

    def _run_relax(self, field: Any, request: AdapterRunRequest) -> AdapterRunPayload:
        from field_theory.su2.nearest_neighbor import (  # type: ignore
            relax_skyrme_field_nearest_neighbor,
        )

        point = request.sweep_point
        f_pi = float(point.get("f_pi", request.model.f_pi))
        e = float(point.get("e", request.model.e))
        max_iterations = int(point.get("max_iterations", request.solver.max_iterations))
        initial_step = float(point.get("initial_step", request.solver.initial_step))

        result = relax_skyrme_field_nearest_neighbor(
            field,
            f_pi=f_pi,
            e=e,
            max_iterations=max_iterations,
            initial_step=initial_step,
            gradient_tolerance=request.solver.gradient_tolerance,
            max_backtracks=request.solver.max_backtracks,
            stationarity_metric=request.solver.stationarity_metric,
            descent_metric=request.solver.descent_metric,
        )
        diagnostics = {
            "final_energy_total": float(result.energy_history[-1])
            if result.energy_history
            else None,
            "final_approximate_topological_charge": (
                float(result.topological_charge_history[-1])
                if result.topological_charge_history
                else None
            ),
            "iterations": int(result.iterations),
            "raw_gradient_norm": float(result.raw_gradient_norm),
            "continuum_l2_residual": float(result.continuum_l2_residual),
            "active_l2_measure": float(result.active_l2_measure),
            "active_l2_rms_residual": float(result.active_l2_rms_residual),
            "stationarity_status": str(result.stationarity_status),
            "minimum_certified": bool(result.minimum_certified),
            "cell_volume": float(result.cell_volume),
            "active_site_count": int(result.active_site_count),
        }
        return AdapterRunPayload(
            status=str(result.termination),
            backend=self.name,
            diagnostics=diagnostics,
            histories={
                "energy_history": [float(x) for x in result.energy_history],
                "topological_charge_history": [
                    float(x) for x in result.topological_charge_history
                ],
            },
            raw_termination=str(result.termination),
            field_checksum=_field_checksum(result.field),
        )

    def _run_lorentzian(self, field: Any, request: AdapterRunRequest) -> AdapterRunPayload:
        import numpy as np

        try:
            from field_theory.su2.lorentzian import evolve_lorentzian_skyrme  # type: ignore
        except Exception as exc:
            raise SolverUnavailableError(
                "evolve_lorentzian_skyrme unavailable (needs PR #468): "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        point = request.sweep_point
        dt = float(point.get("dt", request.solver.dt))
        steps = int(point.get("steps", request.solver.steps))
        save_every = int(request.solver.save_every or 1)
        f_pi = float(point.get("f_pi", request.model.f_pi))
        e = float(point.get("e", request.model.e))

        velocity = np.zeros(field.components.shape, dtype=np.float64)
        trajectory = evolve_lorentzian_skyrme(
            field,
            velocity,
            dt=dt,
            steps=steps,
            save_every=save_every,
            f_pi=f_pi,
            e=e,
            damping=request.model.damping,
        )
        diagnostics = {
            "final_total_energy": float(trajectory.total_energy_history[-1])
            if trajectory.total_energy_history
            else None,
            "final_approximate_topological_charge": (
                float(trajectory.approximate_charge_history[-1])
                if trajectory.approximate_charge_history
                else None
            ),
            "max_unit_norm_error": float(trajectory.max_unit_norm_error),
            "max_tangency_error": float(trajectory.max_tangency_error),
            "linearized_cfl_indicator": float(trajectory.linearized_cfl_indicator),
            "hyperbolicity_status": str(trajectory.hyperbolicity_status),
            "steps": int(trajectory.steps),
            "dt": float(trajectory.dt),
            "cell_volume": float(trajectory.cell_volume),
        }
        return AdapterRunPayload(
            status=str(trajectory.termination),
            backend=self.name,
            diagnostics=diagnostics,
            histories={
                "total_energy_history": [float(x) for x in trajectory.total_energy_history],
                "approximate_charge_history": [
                    float(x) for x in trajectory.approximate_charge_history
                ],
                "energy_balance_residual_history": [
                    float(x) for x in trajectory.energy_balance_residual_history
                ],
            },
            raw_termination=str(trajectory.termination),
        )


class StubSolverBackend:
    """Deterministic contract-test backend; not a physics solver.

    Emits synthetic but seed-stable diagnostics tagged by the runner as
    ``assumed`` / stub-backend values. Never claim these as live solver output.
    """

    name = "stub.su2_skyrme"

    def run(self, request: AdapterRunRequest) -> AdapterRunPayload:
        point = request.sweep_point
        f_pi = float(point.get("f_pi", request.model.f_pi))
        e = float(point.get("e", request.model.e))
        max_iterations = int(point.get("max_iterations", request.solver.max_iterations))
        # Purely synthetic, seed-stable numbers for contract/replay tests.
        base = float(request.seed + 1) * 0.01
        energy = base * f_pi / e + 0.1 * max_iterations
        charge = 0.0 if request.initial_condition.kind == "vacuum" else 0.5 * base
        if request.mode == "lorentzian_evolve":
            steps = int(point.get("steps", request.solver.steps or 1))
            return AdapterRunPayload(
                status="completed",
                backend=self.name,
                diagnostics={
                    "final_total_energy": energy,
                    "final_approximate_topological_charge": charge,
                    "max_unit_norm_error": 0.0,
                    "max_tangency_error": 0.0,
                    "linearized_cfl_indicator": float(request.solver.dt or 0.0)
                    * 2.0
                    * 3.0**0.5,
                    "hyperbolicity_status": "not_certified",
                    "steps": steps,
                    "dt": float(request.solver.dt or 0.0),
                    "cell_volume": float(
                        request.discretization.spacing[0]
                        * request.discretization.spacing[1]
                        * request.discretization.spacing[2]
                    ),
                },
                histories={
                    "total_energy_history": [energy, energy],
                    "approximate_charge_history": [charge, charge],
                    "energy_balance_residual_history": [0.0, 0.0],
                },
                raw_termination="completed",
                message="stub backend; not live solver output",
                field_checksum=f"stub-{request.seed:04d}-{max_iterations}",
            )
        return AdapterRunPayload(
            status="iteration_limit",
            backend=self.name,
            diagnostics={
                "final_energy_total": energy,
                "final_approximate_topological_charge": charge,
                "iterations": max_iterations,
                "raw_gradient_norm": 1.0,
                "continuum_l2_residual": 1.0,
                "active_l2_measure": float(
                    request.discretization.shape[0]
                    * request.discretization.shape[1]
                    * request.discretization.shape[2]
                ),
                "active_l2_rms_residual": 1.0,
                "stationarity_status": "not_established",
                "minimum_certified": False,
                "cell_volume": float(
                    request.discretization.spacing[0]
                    * request.discretization.spacing[1]
                    * request.discretization.spacing[2]
                ),
                "active_site_count": int(
                    request.discretization.shape[0]
                    * request.discretization.shape[1]
                    * request.discretization.shape[2]
                ),
            },
            histories={
                "energy_history": [energy + 0.1, energy],
                "topological_charge_history": [charge, charge],
            },
            raw_termination="iteration_limit",
            message="stub backend; not live solver output",
            field_checksum=f"stub-{request.seed:04d}-{max_iterations}",
        )


def get_backend(*, prefer_live: bool = True, allow_stub: bool = False) -> SolverBackend:
    """Return a live backend when importable, else optional stub, else raise."""
    availability = probe_solver_availability()
    if prefer_live and availability.import_status == "available":
        return LiveSolverBackend()
    if allow_stub:
        return StubSolverBackend()
    raise SolverUnavailableError(
        availability.dependency_blocker or availability.notes
    )


def request_from_config(
    config: ExperimentConfig,
    *,
    sweep_point: dict[str, Any] | None = None,
) -> AdapterRunRequest:
    return AdapterRunRequest(
        mode=config.mode,  # type: ignore[arg-type]
        discretization=config.discretization,
        initial_condition=config.initial_condition,
        model=config.model,
        solver=config.solver,
        seed=config.seed,
        sweep_point=dict(sweep_point or {}),
    )


def _field_checksum(field: Any) -> str:
    import hashlib
    import json

    import numpy as np

    components = np.asarray(field.components)
    metadata = {
        "shape": list(components.shape),
        "spacing": list(field.spacing),
        "boundary": field.boundary,
        "length_unit": field.length_unit,
    }
    canonical_metadata = json.dumps(
        metadata, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    canonical_values = np.ascontiguousarray(components, dtype="<f8").tobytes(order="C")
    return hashlib.sha256(canonical_metadata + b"\0" + canonical_values).hexdigest()
