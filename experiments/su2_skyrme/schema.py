"""Configuration schema for SU(2)/Skyrme experiment runs and sweeps.

Unsupported solver knobs are labeled ``unavailable`` in the schema notes and
rejected if supplied, rather than inventing parameter ranges or fake defaults.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

SCHEMA_VERSION = "0.1.0"

SUPPORTED_MODES = frozenset(
    {
        "nearest_neighbor_relax",
        "nearest_neighbor_sweep",
        "lorentzian_evolve",
    }
)

SUPPORTED_IC_KINDS = frozenset({"vacuum", "hedgehog"})

CLAIM_GUARDRAIL = (
    "Research simulator only. Outputs are finite-grid numerical diagnostics, "
    "not consciousness scores, clinical findings, or validated physical predictions."
)

# Documented but not wired by this experiment layer (owned by solver PRs / viz).
# Keys must match the top-level banned field names checked in validate_experiment_config.
UNAVAILABLE_FIELDS: dict[str, str] = {
    "constrained_pair_relaxation": (
        "Owned by field_theory.su2.constrained_interaction on PR #466; "
        "not exposed by this experiment runner."
    ),
    "interaction_sweep": (
        "Owned by field_theory.su2.interaction_sweep on PR #466; "
        "use that module directly until a dedicated adapter is added."
    ),
    "physical_unit_conversion": (
        "Solver records length_unit metadata only; physical conversion is not_assessed."
    ),
    "visualization": (
        "Visualization UI is owned by a separate lane "
        "(field_theory.su2.*_visualization on solver branches)."
    ),
    "multi_hedgehog": (
        "multi_hedgehog IC kind is available in the solver generators API but "
        "not yet accepted by this experiment schema (label: unavailable)."
    ),
    "fixed_mask": (
        "Optional fixed-site masks exist on the solver API but are not yet "
        "config-driven here (label: unavailable)."
    ),
}


class ExperimentConfigError(ValueError):
    """Raised when an experiment config fails structural validation."""


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExperimentConfigError(f"{name} must be a mapping")
    return value


def _as_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentConfigError(f"{name} must be a positive integer")
    if int(value) != value or int(value) < 1:
        raise ExperimentConfigError(f"{name} must be a positive integer")
    return int(value)


def _as_nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentConfigError(f"{name} must be a nonnegative integer")
    if int(value) != value or int(value) < 0:
        raise ExperimentConfigError(f"{name} must be a nonnegative integer")
    return int(value)


def _as_finite_float(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentConfigError(f"{name} must be a finite number")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ExperimentConfigError(f"{name} must be a finite number")
    if positive and number <= 0.0:
        raise ExperimentConfigError(f"{name} must be positive")
    return number


def _as_triplet(values: object, name: str, *, positive: bool = False) -> tuple[float, float, float]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ExperimentConfigError(f"{name} must be a length-3 sequence")
    if len(values) != 3:
        raise ExperimentConfigError(f"{name} must be a length-3 sequence")
    return tuple(_as_finite_float(v, f"{name}[{i}]", positive=positive) for i, v in enumerate(values))  # type: ignore[return-value]


def _as_shape(values: object) -> tuple[int, int, int]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ExperimentConfigError("discretization.shape must be three integers >= 2")
    if len(values) != 3:
        raise ExperimentConfigError("discretization.shape must be three integers >= 2")
    shape = tuple(_as_positive_int(v, f"discretization.shape[{i}]") for i, v in enumerate(values))
    if any(n < 2 for n in shape):
        raise ExperimentConfigError("discretization.shape must be three integers >= 2")
    return shape  # type: ignore[return-value]


@dataclass(frozen=True)
class DiscretizationConfig:
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float] = (1.0, 1.0, 1.0)
    boundary: str = "fixed_vacuum"
    length_unit: str = "dimensionless"

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape": list(self.shape),
            "spacing": list(self.spacing),
            "boundary": self.boundary,
            "length_unit": self.length_unit,
        }


@dataclass(frozen=True)
class InitialConditionConfig:
    kind: str
    radius: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind}
        if self.radius is not None:
            payload["radius"] = self.radius
        return payload


@dataclass(frozen=True)
class ModelConfig:
    f_pi: float = 1.0
    e: float = 1.0
    damping: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"f_pi": self.f_pi, "e": self.e, "damping": self.damping}


@dataclass(frozen=True)
class SolverSettings:
    max_iterations: int = 2
    initial_step: float = 1.0e-3
    gradient_tolerance: float = 1.0e-7
    max_backtracks: int = 4
    # Lorentzian-only settings (ignored / unavailable for relax modes).
    dt: float | None = None
    steps: int | None = None
    save_every: int | None = None
    stationarity_metric: str = "euclidean"
    descent_metric: str = "euclidean"

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "initial_step": self.initial_step,
            "gradient_tolerance": self.gradient_tolerance,
            "max_backtracks": self.max_backtracks,
            "dt": self.dt,
            "steps": self.steps,
            "save_every": self.save_every,
            "stationarity_metric": self.stationarity_metric,
            "descent_metric": self.descent_metric,
        }


@dataclass(frozen=True)
class SweepAxisConfig:
    """Cartesian product axes for parameter sweeps.

    Only axes listed here are supported. Unknown axis names are rejected.
    """

    f_pi: tuple[float, ...] = (1.0,)
    e: tuple[float, ...] = (1.0,)
    max_iterations: tuple[int, ...] = (2,)
    initial_step: tuple[float, ...] = (1.0e-3,)
    dt: tuple[float, ...] | None = None
    steps: tuple[int, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "f_pi": list(self.f_pi),
            "e": list(self.e),
            "max_iterations": list(self.max_iterations),
            "initial_step": list(self.initial_step),
        }
        if self.dt is not None:
            payload["dt"] = list(self.dt)
        if self.steps is not None:
            payload["steps"] = list(self.steps)
        return payload

    @property
    def point_count(self) -> int:
        count = (
            len(self.f_pi)
            * len(self.e)
            * len(self.max_iterations)
            * len(self.initial_step)
        )
        if self.dt is not None:
            count *= len(self.dt)
        if self.steps is not None:
            count *= len(self.steps)
        return count


@dataclass(frozen=True)
class ExperimentConfig:
    """Smallest useful reproducible experiment / sweep configuration."""

    experiment_id: str
    mode: str
    seed: int = 0
    discretization: DiscretizationConfig = field(
        default_factory=lambda: DiscretizationConfig(shape=(4, 4, 4))
    )
    initial_condition: InitialConditionConfig = field(
        default_factory=lambda: InitialConditionConfig(kind="hedgehog", radius=1.0)
    )
    model: ModelConfig = field(default_factory=ModelConfig)
    solver: SolverSettings = field(default_factory=SolverSettings)
    sweep: SweepAxisConfig | None = None
    schema_version: str = SCHEMA_VERSION
    notes: str = ""
    claim_guardrail: str = CLAIM_GUARDRAIL

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "mode": self.mode,
            "seed": self.seed,
            "discretization": self.discretization.to_dict(),
            "initial_condition": self.initial_condition.to_dict(),
            "model": self.model.to_dict(),
            "solver": self.solver.to_dict(),
            "notes": self.notes,
            "claim_guardrail": self.claim_guardrail,
            "unavailable_fields": dict(UNAVAILABLE_FIELDS),
        }
        if self.sweep is not None:
            payload["sweep"] = self.sweep.to_dict()
        return payload


_SUPPORTED_SWEEP_AXES = frozenset(
    {"f_pi", "e", "max_iterations", "initial_step", "dt", "steps"}
)


def _parse_sweep(raw: Mapping[str, Any] | None) -> SweepAxisConfig | None:
    if raw is None:
        return None
    axes = raw.get("axes", raw)
    axes_map = _require_mapping(axes, "sweep.axes")
    unknown = set(axes_map) - _SUPPORTED_SWEEP_AXES
    if unknown:
        raise ExperimentConfigError(
            f"unsupported sweep axes {sorted(unknown)}; "
            f"supported={sorted(_SUPPORTED_SWEEP_AXES)}; "
            "additional solver axes are unavailable in this layer"
        )

    def _float_axis(name: str, default: tuple[float, ...]) -> tuple[float, ...]:
        if name not in axes_map:
            return default
        values = axes_map[name]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ExperimentConfigError(f"sweep.axes.{name} must be a nonempty sequence")
        if not values:
            raise ExperimentConfigError(f"sweep.axes.{name} must be a nonempty sequence")
        parsed = tuple(_as_finite_float(v, f"sweep.axes.{name}", positive=True) for v in values)
        if len(set(parsed)) != len(parsed):
            raise ExperimentConfigError(f"sweep.axes.{name} must not contain duplicates")
        return parsed

    def _int_axis(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
        if name not in axes_map:
            return default
        values = axes_map[name]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ExperimentConfigError(f"sweep.axes.{name} must be a nonempty sequence")
        if not values:
            raise ExperimentConfigError(f"sweep.axes.{name} must be a nonempty sequence")
        parsed = tuple(_as_positive_int(v, f"sweep.axes.{name}") for v in values)
        if len(set(parsed)) != len(parsed):
            raise ExperimentConfigError(f"sweep.axes.{name} must not contain duplicates")
        return parsed

    dt_axis = None
    if "dt" in axes_map:
        dt_axis = _float_axis("dt", (1.0e-3,))
    steps_axis = None
    if "steps" in axes_map:
        steps_axis = _int_axis("steps", (1,))

    sweep = SweepAxisConfig(
        f_pi=_float_axis("f_pi", (1.0,)),
        e=_float_axis("e", (1.0,)),
        max_iterations=_int_axis("max_iterations", (2,)),
        initial_step=_float_axis("initial_step", (1.0e-3,)),
        dt=dt_axis,
        steps=steps_axis,
    )
    if sweep.point_count > 64:
        raise ExperimentConfigError(
            f"sweep point_count={sweep.point_count} exceeds smoke cap of 64; "
            "narrow axes for local runs"
        )
    return sweep


def validate_experiment_config(raw: Mapping[str, Any]) -> ExperimentConfig:
    """Validate and normalize a raw mapping into ``ExperimentConfig``."""
    data = dict(_require_mapping(raw, "config"))

    # Reject explicitly unavailable top-level keys rather than silently ignoring.
    for banned in (
        "constrained_pair_relaxation",
        "interaction_sweep",
        "fixed_mask",
        "visualization",
        "multi_hedgehog",
    ):
        if banned in data:
            raise ExperimentConfigError(
                f"field {banned!r} is unavailable in this experiment layer: "
                f"{UNAVAILABLE_FIELDS.get(banned, 'not supported')}"
            )

    schema_version = str(data.get("schema_version", SCHEMA_VERSION))
    if schema_version != SCHEMA_VERSION:
        raise ExperimentConfigError(
            f"unsupported schema_version={schema_version!r}; expected {SCHEMA_VERSION!r}"
        )

    experiment_id = data.get("experiment_id")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ExperimentConfigError("experiment_id must be a nonempty string")

    mode = data.get("mode")
    if mode not in SUPPORTED_MODES:
        raise ExperimentConfigError(
            f"mode must be one of {sorted(SUPPORTED_MODES)}; got {mode!r}"
        )

    seed = _as_nonnegative_int(data.get("seed", 0), "seed")
    # Seed semantics: vacuum/hedgehog ICs are deterministic and seed-independent on
    # the live solver path. Seed still participates in provenance / config hash and
    # drives synthetic stub diagnostics. Multi-seed staging = separate configs (or
    # repeated runs) with distinct seed values; there is no seed sweep axis yet.

    disc_raw = _require_mapping(data.get("discretization", {}), "discretization")
    discretization = DiscretizationConfig(
        shape=_as_shape(disc_raw.get("shape", [4, 4, 4])),
        spacing=_as_triplet(disc_raw.get("spacing", [1.0, 1.0, 1.0]), "discretization.spacing", positive=True),
        boundary=str(disc_raw.get("boundary", "fixed_vacuum")),
        length_unit=str(disc_raw.get("length_unit", "dimensionless")),
    )
    if discretization.boundary not in {"fixed_vacuum", "periodic"}:
        raise ExperimentConfigError("discretization.boundary must be fixed_vacuum or periodic")
    if not discretization.length_unit.strip():
        raise ExperimentConfigError("discretization.length_unit must be nonempty")

    # Smoke memory guard: keep default experiment grids tiny.
    node_count = discretization.shape[0] * discretization.shape[1] * discretization.shape[2]
    if node_count > 4096:
        raise ExperimentConfigError(
            f"discretization node_count={node_count} exceeds experiment-layer cap 4096; "
            "use a smaller smoke grid or call the solver API directly"
        )

    ic_raw = _require_mapping(data.get("initial_condition", {}), "initial_condition")
    ic_kind = str(ic_raw.get("kind", "hedgehog"))
    if ic_kind not in SUPPORTED_IC_KINDS:
        raise ExperimentConfigError(
            f"initial_condition.kind must be one of {sorted(SUPPORTED_IC_KINDS)}; "
            f"got {ic_kind!r} (multi_hedgehog is unavailable in this schema)"
        )
    radius = None
    if ic_kind == "hedgehog":
        if "radius" not in ic_raw:
            raise ExperimentConfigError("initial_condition.radius is required for hedgehog")
        radius = _as_finite_float(ic_raw["radius"], "initial_condition.radius", positive=True)
    elif "radius" in ic_raw and ic_raw["radius"] is not None:
        raise ExperimentConfigError("initial_condition.radius is only valid for hedgehog")

    model_raw = _require_mapping(data.get("model", {}), "model")
    model = ModelConfig(
        f_pi=_as_finite_float(model_raw.get("f_pi", 1.0), "model.f_pi", positive=True),
        e=_as_finite_float(model_raw.get("e", 1.0), "model.e", positive=True),
        damping=_as_finite_float(model_raw.get("damping", 0.0), "model.damping"),
    )
    if model.damping < 0.0:
        raise ExperimentConfigError("model.damping must be nonnegative")

    solver_raw = _require_mapping(data.get("solver", {}), "solver")
    solver = SolverSettings(
        max_iterations=_as_positive_int(solver_raw.get("max_iterations", 2), "solver.max_iterations"),
        initial_step=_as_finite_float(solver_raw.get("initial_step", 1.0e-3), "solver.initial_step", positive=True),
        gradient_tolerance=_as_finite_float(
            solver_raw.get("gradient_tolerance", 1.0e-7),
            "solver.gradient_tolerance",
            positive=True,
        ),
        max_backtracks=_as_nonnegative_int(solver_raw.get("max_backtracks", 4), "solver.max_backtracks"),
        dt=(
            None
            if solver_raw.get("dt", None) is None
            else _as_finite_float(solver_raw["dt"], "solver.dt", positive=True)
        ),
        steps=(
            None
            if solver_raw.get("steps", None) is None
            else _as_positive_int(solver_raw["steps"], "solver.steps")
        ),
        save_every=(
            None
            if solver_raw.get("save_every", None) is None
            else _as_positive_int(solver_raw["save_every"], "solver.save_every")
        ),
        stationarity_metric=str(solver_raw.get("stationarity_metric", "euclidean")),
        descent_metric=str(solver_raw.get("descent_metric", "euclidean")),
    )
    if solver.stationarity_metric not in {"euclidean", "continuum_l2"}:
        raise ExperimentConfigError("solver.stationarity_metric must be euclidean or continuum_l2")
    if solver.descent_metric not in {"euclidean", "continuum_l2"}:
        raise ExperimentConfigError("solver.descent_metric must be euclidean or continuum_l2")

    if mode == "lorentzian_evolve":
        if solver.dt is None or solver.steps is None:
            raise ExperimentConfigError(
                "lorentzian_evolve requires solver.dt and solver.steps"
            )
        if solver.save_every is None:
            solver = SolverSettings(
                **{
                    **asdict(solver),
                    "save_every": 1,
                }
            )
    elif mode in {"nearest_neighbor_relax", "nearest_neighbor_sweep"}:
        if model.damping != 0.0:
            raise ExperimentConfigError(
                "model.damping is only valid for lorentzian_evolve "
                "(unavailable for static relax modes)"
            )

    sweep = _parse_sweep(data.get("sweep"))
    if mode == "nearest_neighbor_sweep" and sweep is None:
        raise ExperimentConfigError("nearest_neighbor_sweep requires a sweep block")
    if mode != "nearest_neighbor_sweep" and sweep is not None and mode != "lorentzian_evolve":
        # Allow optional sweep only for dedicated sweep mode; single-run modes reject it.
        if mode == "nearest_neighbor_relax":
            raise ExperimentConfigError(
                "nearest_neighbor_relax rejects sweep; use mode=nearest_neighbor_sweep"
            )

    return ExperimentConfig(
        experiment_id=experiment_id.strip(),
        mode=str(mode),
        seed=seed,
        discretization=discretization,
        initial_condition=InitialConditionConfig(kind=ic_kind, radius=radius),
        model=model,
        solver=solver,
        sweep=sweep,
        schema_version=schema_version,
        notes=str(data.get("notes", "")),
        claim_guardrail=str(data.get("claim_guardrail", CLAIM_GUARDRAIL)),
    )


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    """Load YAML or JSON experiment config from disk."""
    target = Path(path)
    if not target.is_file():
        raise ExperimentConfigError(f"config file not found: {target}")
    text = target.read_text(encoding="utf-8")
    suffix = target.suffix.lower()
    raw: MutableMapping[str, Any]
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ExperimentConfigError(
                "PyYAML is required to load .yaml configs; use JSON or install PyYAML"
            ) from exc
        loaded = yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise ExperimentConfigError("YAML config root must be a mapping")
        raw = loaded
    elif suffix == ".json":
        import json

        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ExperimentConfigError("JSON config root must be a mapping")
        raw = loaded
    else:
        raise ExperimentConfigError("config path must end in .yaml, .yml, or .json")
    return validate_experiment_config(raw)
