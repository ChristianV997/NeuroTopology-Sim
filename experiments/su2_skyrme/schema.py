"""Configuration schema for SU(2)/Skyrme experiment runs and parameter grids.

Validation only — no solver mathematics. Invalid configs raise ``ConfigError``
before any adapter call.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

SCHEMA_VERSION = "su2_skyrme.experiment.config.v1"
ALLOWED_MODES = frozenset({"single", "grid"})
ALLOWED_BOUNDARIES = frozenset({"fixed_vacuum", "periodic"})
ALLOWED_IC_KINDS = frozenset({"hedgehog", "vacuum", "fixed_axis"})
ALLOWED_BACKENDS = frozenset(
    {
        "auto",
        "nearest_neighbor",
        "constrained_pair",
        "lorentzian",
        "unavailable_stub",
    }
)
ALLOWED_EPISTEMIC = frozenset({"computed", "assumed", "speculative"})
MAX_GRID_POINTS = 256


class ConfigError(ValueError):
    """Raised when an experiment config fails schema validation."""


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{name} must be a mapping")
    return value


def _require_str(value: object, name: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{name} must be a string")
    if nonempty and not value.strip():
        raise ConfigError(f"{name} must be a nonempty string")
    return value


def _require_int(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return value


def _require_float(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a finite number")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ConfigError(f"{name} must be a finite number")
    if positive and number <= 0.0:
        raise ConfigError(f"{name} must be > 0")
    return number


def _require_float_triple(value: object, name: str, *, positive: bool = True) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ConfigError(f"{name} must be a length-3 sequence of numbers")
    if len(value) != 3:
        raise ConfigError(f"{name} must contain exactly three numbers")
    return (
        _require_float(value[0], f"{name}[0]", positive=positive),
        _require_float(value[1], f"{name}[1]", positive=positive),
        _require_float(value[2], f"{name}[2]", positive=positive),
    )


def _require_shape(value: object) -> tuple[int, int, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ConfigError("discretization.shape must be a length-3 integer sequence")
    if len(value) != 3:
        raise ConfigError("discretization.shape must contain exactly three integers")
    shape = (
        _require_int(value[0], "discretization.shape[0]", minimum=2),
        _require_int(value[1], "discretization.shape[1]", minimum=2),
        _require_int(value[2], "discretization.shape[2]", minimum=2),
    )
    return shape


def _require_float_list(value: object, name: str, *, positive: bool = True) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ConfigError(f"{name} must be a nonempty sequence of numbers")
    if not value:
        raise ConfigError(f"{name} must be a nonempty sequence of numbers")
    items = tuple(_require_float(item, f"{name}[{i}]", positive=positive) for i, item in enumerate(value))
    if len(set(items)) != len(items):
        raise ConfigError(f"{name} must not contain duplicates")
    return items


def _require_int_list(value: object, name: str, *, minimum: int = 1) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ConfigError(f"{name} must be a nonempty sequence of integers")
    if not value:
        raise ConfigError(f"{name} must be a nonempty sequence of integers")
    items = tuple(_require_int(item, f"{name}[{i}]", minimum=minimum) for i, item in enumerate(value))
    if len(set(items)) != len(items):
        raise ConfigError(f"{name} must not contain duplicates")
    return items


@dataclass(frozen=True)
class DiscretizationConfig:
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float]
    length_unit: str = "dimensionless"

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape": list(self.shape),
            "spacing": list(self.spacing),
            "length_unit": self.length_unit,
        }


@dataclass(frozen=True)
class InitialConditionConfig:
    kind: str
    radius: float | None = None
    axis: tuple[float, float, float] | None = None
    theta: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind}
        if self.radius is not None:
            payload["radius"] = self.radius
        if self.axis is not None:
            payload["axis"] = list(self.axis)
        if self.theta is not None:
            payload["theta"] = self.theta
        return payload


@dataclass(frozen=True)
class ModelConfig:
    f_pi: float = 1.0
    e: float = 1.0
    vacuum: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "f_pi": self.f_pi,
            "e": self.e,
            "vacuum": list(self.vacuum),
            "units": "dimensionless_model_parameters",
            "epistemic_tag": "assumed",
        }


@dataclass(frozen=True)
class SolverConfig:
    backend: str = "auto"
    max_iterations: int = 8
    initial_step: float = 1.0e-3
    gradient_tolerance: float = 1.0e-7
    max_backtracks: int = 8
    stationarity_metric: str = "euclidean"

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "max_iterations": self.max_iterations,
            "initial_step": self.initial_step,
            "gradient_tolerance": self.gradient_tolerance,
            "max_backtracks": self.max_backtracks,
            "stationarity_metric": self.stationarity_metric,
            "interpretation": "numerical_controls_not_physical_time",
        }


@dataclass(frozen=True)
class GridAxesConfig:
    f_pi_values: tuple[float, ...] = ()
    e_values: tuple[float, ...] = ()
    max_iterations_values: tuple[int, ...] = ()
    initial_step_values: tuple[float, ...] = ()

    def point_count(self) -> int:
        counts = [
            len(self.f_pi_values) or 1,
            len(self.e_values) or 1,
            len(self.max_iterations_values) or 1,
            len(self.initial_step_values) or 1,
        ]
        total = 1
        for count in counts:
            total *= count
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "f_pi_values": list(self.f_pi_values),
            "e_values": list(self.e_values),
            "max_iterations_values": list(self.max_iterations_values),
            "initial_step_values": list(self.initial_step_values),
            "point_count": self.point_count(),
        }


@dataclass(frozen=True)
class ExperimentConfig:
    """Validated experiment configuration (single run or parameter grid)."""

    experiment_id: str
    mode: str
    seed: int
    discretization: DiscretizationConfig
    boundary_conditions: str
    initial_condition: InitialConditionConfig
    model: ModelConfig
    solver: SolverConfig
    grid: GridAxesConfig = field(default_factory=GridAxesConfig)
    output_root: str = "outputs/experiments/su2_skyrme"
    notes: str = ""
    schema_version: str = SCHEMA_VERSION
    claim_scope: str = (
        "engineering_reproducibility_only; no consciousness, biological, "
        "or physical-validation claim"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "mode": self.mode,
            "seed": self.seed,
            "discretization": self.discretization.to_dict(),
            "boundary_conditions": self.boundary_conditions,
            "initial_condition": self.initial_condition.to_dict(),
            "model": self.model.to_dict(),
            "solver": self.solver.to_dict(),
            "grid": self.grid.to_dict(),
            "output_root": self.output_root,
            "notes": self.notes,
            "claim_scope": self.claim_scope,
            "consciousness_score": None,
            "consciousness_implication": "none",
        }

    def canonical_dict(self) -> dict[str, Any]:
        """Stable subset used for config hashing.

        Excludes free-form notes and output_root so replay identity is stable
        across redirected artifact directories.
        """
        payload = self.to_dict()
        payload.pop("notes", None)
        payload.pop("output_root", None)
        return payload


def _parse_initial_condition(raw: Mapping[str, Any]) -> InitialConditionConfig:
    kind = _require_str(raw.get("kind"), "initial_condition.kind")
    if kind not in ALLOWED_IC_KINDS:
        raise ConfigError(
            f"initial_condition.kind must be one of {sorted(ALLOWED_IC_KINDS)}"
        )
    radius = None
    axis = None
    theta = None
    if kind == "hedgehog":
        radius = _require_float(raw.get("radius", 1.0), "initial_condition.radius", positive=True)
    elif kind == "fixed_axis":
        axis = _require_float_triple(raw.get("axis", (0.0, 0.0, 1.0)), "initial_condition.axis", positive=False)
        theta = _require_float(raw.get("theta", 0.0), "initial_condition.theta", positive=False)
    return InitialConditionConfig(kind=kind, radius=radius, axis=axis, theta=theta)


def _parse_model(raw: Mapping[str, Any]) -> ModelConfig:
    vacuum_raw = raw.get("vacuum", (1.0, 0.0, 0.0, 0.0))
    if not isinstance(vacuum_raw, Sequence) or isinstance(vacuum_raw, (str, bytes)) or len(vacuum_raw) != 4:
        raise ConfigError("model.vacuum must be a length-4 numeric sequence")
    vacuum = tuple(
        _require_float(item, f"model.vacuum[{i}]", positive=False)
        for i, item in enumerate(vacuum_raw)
    )
    return ModelConfig(
        f_pi=_require_float(raw.get("f_pi", 1.0), "model.f_pi", positive=True),
        e=_require_float(raw.get("e", 1.0), "model.e", positive=True),
        vacuum=vacuum,  # type: ignore[arg-type]
    )


def _parse_solver(raw: Mapping[str, Any]) -> SolverConfig:
    backend = _require_str(raw.get("backend", "auto"), "solver.backend")
    if backend not in ALLOWED_BACKENDS:
        raise ConfigError(f"solver.backend must be one of {sorted(ALLOWED_BACKENDS)}")
    return SolverConfig(
        backend=backend,
        max_iterations=_require_int(raw.get("max_iterations", 8), "solver.max_iterations", minimum=1),
        initial_step=_require_float(raw.get("initial_step", 1.0e-3), "solver.initial_step", positive=True),
        gradient_tolerance=_require_float(
            raw.get("gradient_tolerance", 1.0e-7),
            "solver.gradient_tolerance",
            positive=True,
        ),
        max_backtracks=_require_int(raw.get("max_backtracks", 8), "solver.max_backtracks", minimum=0),
        stationarity_metric=_require_str(
            raw.get("stationarity_metric", "euclidean"),
            "solver.stationarity_metric",
        ),
    )


def _parse_grid(raw: Mapping[str, Any] | None, mode: str) -> GridAxesConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ConfigError("grid must be a mapping")
    grid = GridAxesConfig(
        f_pi_values=_require_float_list(raw["f_pi_values"], "grid.f_pi_values")
        if "f_pi_values" in raw
        else (),
        e_values=_require_float_list(raw["e_values"], "grid.e_values") if "e_values" in raw else (),
        max_iterations_values=_require_int_list(raw["max_iterations_values"], "grid.max_iterations_values")
        if "max_iterations_values" in raw
        else (),
        initial_step_values=_require_float_list(raw["initial_step_values"], "grid.initial_step_values")
        if "initial_step_values" in raw
        else (),
    )
    if mode == "grid" and grid.point_count() < 2 and not any(
        (
            grid.f_pi_values,
            grid.e_values,
            grid.max_iterations_values,
            grid.initial_step_values,
        )
    ):
        raise ConfigError("mode=grid requires at least one nonempty grid axis")
    if grid.point_count() > MAX_GRID_POINTS:
        raise ConfigError(f"grid point count exceeds maximum of {MAX_GRID_POINTS}")
    return grid


def validate_config(raw: Mapping[str, Any]) -> ExperimentConfig:
    """Validate and normalize a raw config mapping into ``ExperimentConfig``."""
    data = _require_mapping(raw, "config")
    schema_version = _require_str(data.get("schema_version", SCHEMA_VERSION), "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ConfigError(
            f"unsupported schema_version {schema_version!r}; expected {SCHEMA_VERSION!r}"
        )
    mode = _require_str(data.get("mode", "single"), "mode")
    if mode not in ALLOWED_MODES:
        raise ConfigError(f"mode must be one of {sorted(ALLOWED_MODES)}")

    disc_raw = _require_mapping(data.get("discretization"), "discretization")
    discretization = DiscretizationConfig(
        shape=_require_shape(disc_raw.get("shape")),
        spacing=_require_float_triple(disc_raw.get("spacing", (1.0, 1.0, 1.0)), "discretization.spacing"),
        length_unit=_require_str(disc_raw.get("length_unit", "dimensionless"), "discretization.length_unit"),
    )

    boundary = _require_str(data.get("boundary_conditions", "fixed_vacuum"), "boundary_conditions")
    if boundary not in ALLOWED_BOUNDARIES:
        raise ConfigError(f"boundary_conditions must be one of {sorted(ALLOWED_BOUNDARIES)}")

    ic_raw = _require_mapping(data.get("initial_condition"), "initial_condition")
    model_raw = _require_mapping(data.get("model", {}), "model")
    solver_raw = _require_mapping(data.get("solver", {}), "solver")
    grid = _parse_grid(data.get("grid"), mode)

    return ExperimentConfig(
        experiment_id=_require_str(data.get("experiment_id"), "experiment_id"),
        mode=mode,
        seed=_require_int(data.get("seed", 0), "seed", minimum=0),
        discretization=discretization,
        boundary_conditions=boundary,
        initial_condition=_parse_initial_condition(ic_raw),
        model=_parse_model(model_raw),
        solver=_parse_solver(solver_raw),
        grid=grid,
        output_root=_require_str(
            data.get("output_root", "outputs/experiments/su2_skyrme"),
            "output_root",
        ),
        notes=str(data.get("notes", "")),
        schema_version=schema_version,
    )


def load_config(path: str | Path) -> ExperimentConfig:
    """Load YAML or JSON experiment config from disk."""
    target = Path(path)
    if not target.is_file():
        raise ConfigError(f"config file not found: {target}")
    text = target.read_text(encoding="utf-8")
    suffix = target.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised when PyYAML absent
            raise ConfigError(
                "PyYAML is required to load .yaml configs; install PyYAML or use JSON"
            ) from exc
        raw = yaml.safe_load(text)
    elif suffix == ".json":
        raw = json.loads(text)
    else:
        raise ConfigError("config path must end in .yaml, .yml, or .json")
    if not isinstance(raw, Mapping):
        raise ConfigError("config root must be a mapping")
    return validate_config(raw)


def expand_grid_points(config: ExperimentConfig) -> list[ExperimentConfig]:
    """Expand a grid config into concrete single-run configs."""
    if config.mode != "grid":
        return [config]

    f_pi_values = config.grid.f_pi_values or (config.model.f_pi,)
    e_values = config.grid.e_values or (config.model.e,)
    max_iter_values = config.grid.max_iterations_values or (config.solver.max_iterations,)
    step_values = config.grid.initial_step_values or (config.solver.initial_step,)

    points: list[ExperimentConfig] = []
    index = 0
    for f_pi in f_pi_values:
        for e in e_values:
            for max_iterations in max_iter_values:
                for initial_step in step_values:
                    index += 1
                    point_id = f"{config.experiment_id}__p{index:03d}"
                    points.append(
                        ExperimentConfig(
                            experiment_id=point_id,
                            mode="single",
                            seed=config.seed,
                            discretization=config.discretization,
                            boundary_conditions=config.boundary_conditions,
                            initial_condition=config.initial_condition,
                            model=ModelConfig(
                                f_pi=f_pi,
                                e=e,
                                vacuum=config.model.vacuum,
                            ),
                            solver=SolverConfig(
                                backend=config.solver.backend,
                                max_iterations=max_iterations,
                                initial_step=initial_step,
                                gradient_tolerance=config.solver.gradient_tolerance,
                                max_backtracks=config.solver.max_backtracks,
                                stationarity_metric=config.solver.stationarity_metric,
                            ),
                            grid=GridAxesConfig(),
                            output_root=config.output_root,
                            notes=config.notes,
                            schema_version=config.schema_version,
                            claim_scope=config.claim_scope,
                        )
                    )
    return points


def deep_update(base: MutableMapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings for test helpers."""
    result = copy.deepcopy(dict(base))
    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = deep_update(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = copy.deepcopy(value)
    return result
