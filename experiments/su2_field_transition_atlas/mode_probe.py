"""Bounded mode-following probe with finite-difference directional curvature.

Perturbs a stationary oracle field along a declared tangent direction and an
L2-orthogonal control, using the production forward-link energy, active-site
mask, boundary conventions, and geodesic map from
``field_theory.su2.nearest_neighbor``.

A Riemannian Hessian-vector product / eigenmode solver is **not** available on
``origin/main`` at the base SHA this package targets. Curvature is therefore the
explicit central geodesic second difference

    kappa(v) = [E(exp_n(+s v)) + E(exp_n(-s v)) - 2 E(n)] / s^2

with the same geodesic convention as ``probe_nearest_neighbor_curvature``.
This is a named finite-difference directional-curvature probe, not a Rayleigh
quotient from an analytic H_R, not a transition path, and not a metastable
barrier or physical frequency.
"""

from __future__ import annotations

import json
import resource
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from field_theory.su2 import SU2GridField
from field_theory.su2.nearest_neighbor import (
    _active_mask,
    _geodesic_perturbation,
    _total_energy_for_values,
    nearest_neighbor_energy_gradient,
)

OracleName = Literal["periodic_checkerboard"]


@dataclass(frozen=True)
class ModeProbeConfig:
    """Configuration for one bounded mode-follow run."""

    oracle: OracleName = "periodic_checkerboard"
    shape: tuple[int, int, int] = (8, 4, 4)
    spacing: tuple[float, float, float] = (1.0, 1.0, 1.0)
    f_pi: float = 1.0
    e: float = 1.0
    step_sizes: tuple[float, ...] = (2.0e-2, 5.0e-2, 1.0e-1)
    n_steps: int = 8
    curvature_probe_step: float = 5.0e-3
    gradient_stationarity_tol: float = 1.0e-10
    seed: int = 0
    schema_version: str = "fta.mode_follow.0.1.0"


@dataclass(frozen=True)
class ModeProbeResult:
    """Machine-readable probe output. Explicitly not a path/barrier certificate."""

    schema_version: str
    classification: str
    objective: str
    curvature_method: str
    hessian_status: str
    base_sha_note: str
    oracle: str
    initial_energy: float
    initial_gradient_norm: float
    declared_directional_curvature0: float
    control_directional_curvature0: float
    declared_predicted_larger_drop: bool | None
    records: dict[str, Any]
    limitations: tuple[str, ...]


def _project(values: np.ndarray, vectors: np.ndarray, active: np.ndarray) -> np.ndarray:
    out = vectors - values * np.sum(values * vectors, axis=-1, keepdims=True)
    out = out.copy()
    out[~active] = 0.0
    return out


def _normalize(active: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    out = vectors.copy()
    norm = float(np.linalg.norm(out[active]))
    if norm <= np.finfo(np.float64).eps:
        raise ValueError("cannot normalize a vanishing tangent vector")
    out /= norm
    return out


def _inner(active: np.ndarray, u: np.ndarray, v: np.ndarray) -> float:
    return float(np.sum(u[active] * v[active]))


def finite_difference_directional_curvature(
    field: SU2GridField,
    direction: np.ndarray,
    *,
    f_pi: float,
    e: float,
    probe_step: float,
) -> float:
    """Central geodesic second difference along a unit tangent direction.

    Named explicitly: this is **not** an analytic Riemannian HVP Rayleigh
    quotient. Uses production ``_geodesic_perturbation`` and
    ``_total_energy_for_values`` (forward-link objective).
    """
    if probe_step <= 0.0 or probe_step > 0.1:
        raise ValueError("probe_step must lie in (0, 0.1]")
    values = np.array(field.components, dtype=np.float64, copy=True)
    active = _active_mask(field)
    direction = _normalize(active, _project(values, direction, active))
    base = _total_energy_for_values(values, field, f_pi, e)
    plus = _geodesic_perturbation(values, direction, probe_step, 1.0)
    minus = _geodesic_perturbation(values, direction, probe_step, -1.0)
    # Renormalize after geodesic map (production probe does not always, but
    # floating drift is clipped to the unit sphere for active sites).
    for candidate in (plus, minus):
        norms = np.linalg.norm(candidate, axis=-1, keepdims=True)
        np.divide(candidate, norms, out=candidate, where=norms > 0.0)
        candidate[~active] = values[~active]
    kappa = (
        _total_energy_for_values(plus, field, f_pi, e)
        + _total_energy_for_values(minus, field, f_pi, e)
        - 2.0 * base
    ) / (probe_step * probe_step)
    if not np.isfinite(kappa):
        raise FloatingPointError("non-finite finite-difference directional curvature")
    return float(kappa)


def _resource_snapshot(t0: float) -> dict[str, float]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "wall_seconds": float(time.perf_counter() - t0),
        "ru_maxrss_kib": float(usage.ru_maxrss),
        "ru_utime_seconds": float(usage.ru_utime),
        "ru_stime_seconds": float(usage.ru_stime),
    }


def _checkerboard_field(
    shape: tuple[int, int, int], spacing: tuple[float, float, float]
) -> SU2GridField:
    values = np.zeros(shape + (4,), dtype=np.float64)
    pattern = ((-1.0) ** np.arange(shape[0], dtype=np.float64))[:, None, None]
    values[..., 0] = np.broadcast_to(pattern, shape)
    return SU2GridField(values, spacing=spacing, boundary="periodic")


def _declared_soft_direction(values: np.ndarray, active: np.ndarray) -> np.ndarray:
    """Declared tangent: ambient e1 projected at each site (known soft probe)."""
    direction = -values * values[..., 1, None]
    direction = direction.copy()
    direction[..., 1] += 1.0
    return _normalize(active, _project(values, direction, active))


def _orthogonal_control(
    values: np.ndarray,
    active: np.ndarray,
    declared: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    best = None
    best_score = -np.inf
    for _ in range(16):
        raw = rng.normal(size=values.shape)
        cand = _project(values, raw, active)
        cand -= declared * _inner(active, declared, cand)
        cand = _project(values, cand, active)
        if float(np.linalg.norm(cand[active])) <= np.finfo(np.float64).eps:
            continue
        cand = _normalize(active, cand)
        rank = -abs(_inner(active, declared, cand))
        if rank > best_score:
            best_score = rank
            best = cand
    if best is None:
        raise RuntimeError("failed to construct an orthogonal control direction")
    return best


def _follow_direction(
    values0: np.ndarray,
    spacing: tuple[float, float, float],
    boundary: str,
    direction0: np.ndarray,
    *,
    step: float,
    n_steps: int,
    f_pi: float,
    e: float,
    curvature_probe_step: float,
) -> tuple[list[dict[str, float]], dict[str, float]]:
    """Geodesic steps along a fixed initial tangent, reprojected each step."""
    t0 = time.perf_counter()
    values = values0.copy()
    direction = direction0.copy()
    records: list[dict[str, float]] = []
    for index in range(n_steps + 1):
        field = SU2GridField(values, spacing=spacing, boundary=boundary)
        active = _active_mask(field)
        direction = _normalize(active, _project(values, direction, active))
        grad = nearest_neighbor_energy_gradient(field, f_pi=f_pi, e=e)
        energy = _total_energy_for_values(values, field, f_pi, e)
        kappa = finite_difference_directional_curvature(
            field,
            direction,
            f_pi=f_pi,
            e=e,
            probe_step=curvature_probe_step,
        )
        overlap = _inner(active, direction, direction0)
        records.append(
            {
                "s_index": float(index),
                "step_size": float(step),
                "energy": float(energy),
                "gradient_residual_norm": float(np.linalg.norm(grad[active])),
                "fd_directional_curvature": float(kappa),
                "mode_overlap_with_initial": float(overlap),
                "direction_norm": float(np.linalg.norm(direction[active])),
            }
        )
        if index == n_steps:
            break
        values = _geodesic_perturbation(values, direction, step, 1.0)
        norms = np.linalg.norm(values, axis=-1, keepdims=True)
        np.divide(values, norms, out=values, where=norms > 0.0)
        values[~active] = values0[~active]
    return records, _resource_snapshot(t0)


def run_mode_probe(config: ModeProbeConfig) -> ModeProbeResult:
    if config.oracle != "periodic_checkerboard":
        raise ValueError(f"unsupported oracle {config.oracle!r}")
    if config.n_steps < 1:
        raise ValueError("n_steps must be >= 1")
    if not config.step_sizes:
        raise ValueError("step_sizes must be nonempty")

    field0 = _checkerboard_field(config.shape, config.spacing)
    values0 = np.array(field0.components, dtype=np.float64, copy=True)
    active = _active_mask(field0)
    grad0 = nearest_neighbor_energy_gradient(field0, f_pi=config.f_pi, e=config.e)
    gnorm0 = float(np.linalg.norm(grad0[active]))
    energy0 = _total_energy_for_values(values0, field0, config.f_pi, config.e)

    declared = _declared_soft_direction(values0, active)
    rng = np.random.default_rng(config.seed)
    control = _orthogonal_control(values0, active, declared, rng)
    control -= declared * _inner(active, declared, control)
    control = _normalize(active, _project(values0, control, active))

    kappa_decl = finite_difference_directional_curvature(
        field0,
        declared,
        f_pi=config.f_pi,
        e=config.e,
        probe_step=config.curvature_probe_step,
    )
    kappa_ctrl = finite_difference_directional_curvature(
        field0,
        control,
        f_pi=config.f_pi,
        e=config.e,
        probe_step=config.curvature_probe_step,
    )

    by_step: dict[str, Any] = {}
    decl_best_drop: float | None = None
    ctrl_best_drop: float | None = None
    for step in config.step_sizes:
        decl_rec, decl_res = _follow_direction(
            values0,
            config.spacing,
            field0.boundary,
            declared,
            step=float(step),
            n_steps=config.n_steps,
            f_pi=config.f_pi,
            e=config.e,
            curvature_probe_step=config.curvature_probe_step,
        )
        ctrl_rec, ctrl_res = _follow_direction(
            values0,
            config.spacing,
            field0.boundary,
            control,
            step=float(step),
            n_steps=config.n_steps,
            f_pi=config.f_pi,
            e=config.e,
            curvature_probe_step=config.curvature_probe_step,
        )
        decl_drop = decl_rec[0]["energy"] - decl_rec[-1]["energy"]
        ctrl_drop = ctrl_rec[0]["energy"] - ctrl_rec[-1]["energy"]
        by_step[f"{step:.6g}"] = {
            "declared": decl_rec,
            "control": ctrl_rec,
            "declared_energy_drop": decl_drop,
            "control_energy_drop": ctrl_drop,
            "declared_drop_minus_control": decl_drop - ctrl_drop,
            "resource_declared": decl_res,
            "resource_control": ctrl_res,
        }
        decl_best_drop = decl_drop if decl_best_drop is None else max(decl_best_drop, decl_drop)
        ctrl_best_drop = ctrl_drop if ctrl_best_drop is None else max(ctrl_best_drop, ctrl_drop)

    predicted: bool | None
    if decl_best_drop is None or ctrl_best_drop is None:
        predicted = None
    else:
        predicted = bool(decl_best_drop > ctrl_best_drop + 1.0e-9)

    limitations = (
        "Bounded geodesic mode-following probe only; not a converged transition path.",
        "Not a metastable-barrier, physical-frequency, or soliton certificate.",
        "Curvature is finite-difference directional curvature, not an analytic H_R eigenmode.",
        "Riemannian HVP / eigenmode solver unavailable on this main base; dependency reported.",
        "Declared-vs-control comparison scores relative energy drop only.",
        "Periodic checkerboard oracle; fixed-vacuum faces are inactive via production mask when used.",
        "No physical time, neural, clinical, or consciousness interpretation.",
    )

    return ModeProbeResult(
        schema_version=config.schema_version,
        classification="bounded_mode_following_fd_curvature_probe",
        objective="field_theory.su2.nearest_neighbor forward-link energy",
        curvature_method=(
            "finite_difference_directional_curvature "
            "(central geodesic second difference)"
        ),
        hessian_status=(
            "unavailable_on_base; using finite_difference_directional_curvature"
        ),
        base_sha_note="intended base origin/main 893344e8479008e04a39b7ea49511d62f10e0cca",
        oracle=config.oracle,
        initial_energy=energy0,
        initial_gradient_norm=gnorm0,
        declared_directional_curvature0=kappa_decl,
        control_directional_curvature0=kappa_ctrl,
        declared_predicted_larger_drop=predicted,
        records={
            "config": asdict(config),
            "declared_control_inner": _inner(active, declared, control),
            "by_step_size": by_step,
            "stationarity_ok": gnorm0 <= config.gradient_stationarity_tol,
            "active_site_count": int(np.count_nonzero(active)),
            "boundary": field0.boundary,
        },
        limitations=limitations,
    )


def result_to_dict(result: ModeProbeResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["limitations"] = list(result.limitations)
    return payload


def write_result(result: ModeProbeResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_to_dict(result), indent=2, sort_keys=True) + "\n")
