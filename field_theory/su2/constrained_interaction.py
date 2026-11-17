"""Bounded fixed-anchor pair-versus-isolated SU(2) relaxation.

This is a synthetic finite-grid optimization comparison. Frozen local
Dirichlet patches define the constraint set; they do not define a verified
fixed-separation/fixed-isorotation collective-coordinate minimum.
"""
from __future__ import annotations

import hashlib
import json
import re
from math import prod
from typing import Sequence

import numpy as np

from .field import SU2GridField, validate_spacing
from .generators import multi_hedgehog
from .nearest_neighbor import (
    _cell_volume,
    _gradient_coefficients,
    _forward_differences,
    _link_mask,
    compute_nearest_neighbor_diagnostics,
    relax_skyrme_field_nearest_neighbor,
)

_INPUT_SCHEMA = "su2.constrained_pair_relaxation.input.v1"
_RESULT_SCHEMA = "su2.constrained_pair_relaxation.result.v1"
_MAX_GRID_NODES = 32_768
_MAX_ITERATIONS = 100
_MAX_BACKTRACKS = 12
_MAX_ESTIMATED_NODE_VISITS = 75_000_000
_ANCHOR_MATCH_ABS_TOLERANCE = 1.0e-12
_VACUUM = (1.0, 0.0, 0.0, 0.0)
_IDENTITY = (1.0, 0.0, 0.0, 0.0)
_NUMERICAL_EXCEPTIONS = (
    FloatingPointError,
    np.linalg.LinAlgError,
    ZeroDivisionError,
    OverflowError,
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _real_scalar(value: object, name: str, *, positive: bool = False) -> float:
    raw = np.asarray(value)
    if raw.ndim != 0 or raw.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a real numeric scalar")
    number = float(raw)
    if not np.isfinite(number) or (positive and number <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{name} must be {qualifier}")
    return number


def _integer(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    number = int(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def _shape3(value: object) -> tuple[int, int, int]:
    try:
        parts = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError("shape must contain three integers >= 5") from exc
    if len(parts) != 3 or any(
        isinstance(item, (bool, np.bool_))
        or not isinstance(item, (int, np.integer))
        or int(item) < 5
        for item in parts
    ):
        raise ValueError("shape must contain three integers >= 5")
    result = tuple(int(item) for item in parts)
    if prod(result) > _MAX_GRID_NODES:
        raise ValueError(f"grid exceeds the {_MAX_GRID_NODES}-node limit")
    return result


def _real_vector(value: object, name: str, length: int) -> tuple[float, ...]:
    try:
        objects = np.asarray(value, dtype=object)
        if any(isinstance(item, (bool, np.bool_)) for item in objects.flat):
            raise ValueError
        raw = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real vector of length {length}") from exc
    if raw.shape != (length,) or raw.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a finite real vector of length {length}")
    numbers = raw.astype(np.float64, copy=False)
    if not np.all(np.isfinite(numbers)):
        raise ValueError(f"{name} must be finite")
    return tuple(float(item) for item in numbers)


def _unit_quaternion(value: object) -> tuple[tuple[float, ...], tuple[float, ...]]:
    supplied = _real_vector(value, "relative_isorotation", 4)
    raw = np.asarray(supplied, dtype=np.float64)
    scale = float(np.max(np.abs(raw)))
    norm = 0.0 if scale == 0.0 else scale * float(np.linalg.norm(raw / scale))
    if not np.isfinite(norm) or abs(norm - 1.0) > 1.0e-10:
        raise ValueError("relative_isorotation must have unit norm")
    used = raw / norm
    return supplied, tuple(float(item) for item in used)


def _coordinates(
    shape: tuple[int, int, int], spacing: tuple[float, float, float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    axes = tuple(
        (np.arange(size, dtype=np.float64) - (size - 1) / 2.0) * step
        for size, step in zip(shape, spacing)
    )
    return tuple(np.meshgrid(*axes, indexing="ij"))  # type: ignore[return-value]


def _anchor_masks(
    shape: tuple[int, int, int],
    spacing: tuple[float, float, float],
    centers: tuple[tuple[float, float, float], tuple[float, float, float]],
    anchor_radius: float,
) -> tuple[np.ndarray, np.ndarray]:
    grid = _coordinates(shape, spacing)
    masks = []
    for center in centers:
        distance = np.hypot(
            np.hypot(grid[0] - center[0], grid[1] - center[1]),
            grid[2] - center[2],
        )
        masks.append(distance <= anchor_radius)
    return masks[0], masks[1]


def _fit_anchor_rotation(
    before: np.ndarray,
    after: np.ndarray,
    mask: np.ndarray,
    coordinates: tuple[np.ndarray, np.ndarray, np.ndarray],
    center: tuple[float, float, float],
    anchor_radius: float,
) -> tuple[np.ndarray, dict[str, object]]:
    """Weighted SO(3) Procrustes fit of local pion vectors, column convention."""
    source = np.asarray(before[mask, 1:], dtype=np.float64)
    target = np.asarray(after[mask, 1:], dtype=np.float64)
    x, y, z = (axis[mask] for axis in coordinates)
    radius_squared = (x - center[0]) ** 2 + (y - center[1]) ** 2 + (z - center[2]) ** 2
    weights = np.exp(-radius_squared / (2.0 * anchor_radius * anchor_radius))
    covariance = source.T @ (weights[:, None] * source)
    eigenvalues = np.linalg.eigvalsh(covariance)
    largest = float(eigenvalues[-1])
    span_ratio = 0.0 if largest <= 0.0 else float(eigenvalues[-2] / largest)
    if not np.isfinite(span_ratio) or span_ratio <= 1.0e-8:
        raise ValueError("anchor pion vectors do not span two non-collinear directions")

    cross = source.T @ (weights[:, None] * target)
    left, _, right_t = np.linalg.svd(cross)
    right = right_t.T
    correction = np.eye(3)
    correction[-1, -1] = 1.0 if np.linalg.det(right @ left.T) >= 0.0 else -1.0
    rotation = right @ correction @ left.T
    residual = target - source @ rotation.T
    denominator = float(np.sum(weights * np.sum(target * target, axis=1)))
    if denominator <= np.finfo(np.float64).tiny:
        raise ValueError("anchor pion vectors have insufficient nonzero magnitude")
    relative_residual = float(
        np.sqrt(np.sum(weights * np.sum(residual * residual, axis=1)) / denominator)
    )
    cosine = float(np.clip((np.trace(rotation) - 1.0) / 2.0, -1.0, 1.0))
    angle = float(np.arccos(cosine))
    details: dict[str, object] = {
        "status": "FIT",
        "rotation_matrix": rotation.tolist(),
        "rotation_angle_rad": angle,
        "weighted_relative_residual": relative_residual,
        "second_to_first_span_eigenvalue_ratio": span_ratio,
        "sample_count": int(source.shape[0]),
    }
    if not np.all(np.isfinite((angle, relative_residual, span_ratio))):
        raise FloatingPointError("non-finite anchor orientation diagnostic")
    return rotation, details


def _component_charges(
    field: SU2GridField, centers: tuple[tuple[float, float, float], ...]
) -> tuple[float, ...]:
    values = np.asarray(field.components, dtype=np.float64)
    differences = _forward_differences(values, field.spacing)
    determinant = np.linalg.det(np.stack((values, *differences), axis=-1))
    cell_volume = float(np.prod(field.spacing))
    density = determinant * cell_volume / (2.0 * np.pi**2)
    valid = _link_mask(values.shape[:3], (0, 1, 2), field.boundary)
    grid = _coordinates(values.shape[:3], field.spacing)
    if len(centers) == 1:
        charges = (float(np.sum(density[valid])),)
    else:
        distance0 = np.hypot(
            np.hypot(grid[0] - centers[0][0], grid[1] - centers[0][1]),
            grid[2] - centers[0][2],
        )
        distance1 = np.hypot(
            np.hypot(grid[0] - centers[1][0], grid[1] - centers[1][1]),
            grid[2] - centers[1][2],
        )
        first = distance0 <= distance1
        charges = (
            float(np.sum(density[valid & first])),
            float(np.sum(density[valid & ~first])),
        )
    if not np.all(np.isfinite(charges)):
        raise FloatingPointError("non-finite component charge diagnostic")
    return charges


def _mark_numerical_failure(
    result: dict[str, object], stage: str, error: BaseException
) -> dict[str, object]:
    """Return a finite, serializable run record for a numerical failure."""
    result.update(
        {
            "status": "NUMERICAL_FAILURE",
            "failure_class": type(error).__name__,
            "termination": stage,
            "final_energy": None,
        }
    )
    return result


def _one_relaxation(
    name: str,
    field: SU2GridField,
    fixed_mask: np.ndarray,
    anchor_masks: tuple[np.ndarray, ...],
    anchor_centers: tuple[tuple[float, float, float], ...],
    charge_centers: tuple[tuple[float, float, float], ...],
    coordinates: tuple[np.ndarray, np.ndarray, np.ndarray],
    anchor_radius: float,
    orientation_tolerance_rad: float,
    residual_tolerance: float,
    charge_drift_tolerance: float,
    f_pi: float,
    e: float,
    max_iterations: int,
    initial_step: float,
    gradient_tolerance: float,
    max_backtracks: int,
) -> dict[str, object]:
    initial = field.components.copy()
    base: dict[str, object] = {
        "name": name,
        "initial_energy": None,
        "initial_total_approximate_charge": None,
        "initial_component_approximate_charges": None,
        "energy_history": [],
        "total_approximate_charge_history": [],
        "iterations": 0,
        "termination": "not_run",
        "stationarity_status": "not_established",
        "minimum_certified": False,
        "constraints": {
            "fixed_site_count": int(np.count_nonzero(fixed_mask)),
            "fixed_sites_unchanged": False,
            "maximum_fixed_site_absolute_deviation": None,
        },
        "orientation_fits": [],
        "component_charge_drift": None,
        "charge_drift_status": "NOT_ASSESSED",
        "final_energy": None,
        "final_total_approximate_charge": None,
        "final_component_approximate_charges": None,
        "curvature_screen": None,
        "relative_anchor_frame_change_rad": None,
    }

    try:
        initial_diagnostics = compute_nearest_neighbor_diagnostics(field, f_pi=f_pi, e=e)
        initial_energy = float(initial_diagnostics.energy_total)
        initial_charge = float(initial_diagnostics.topological_charge)
        if not np.all(np.isfinite((initial_energy, initial_charge))):
            raise FloatingPointError("non-finite initial diagnostic")
        base.update(
            {
                "initial_energy": initial_energy,
                "initial_total_approximate_charge": initial_charge,
                "energy_history": [initial_energy],
                "total_approximate_charge_history": [initial_charge],
            }
        )
        initial_charges = _component_charges(field, charge_centers)
        base["initial_component_approximate_charges"] = list(initial_charges)
    except _NUMERICAL_EXCEPTIONS as exc:
        return _mark_numerical_failure(base, "initial_diagnostics_failure", exc)

    try:
        relaxed = relax_skyrme_field_nearest_neighbor(
            field,
            f_pi=f_pi,
            e=e,
            max_iterations=max_iterations,
            initial_step=initial_step,
            gradient_tolerance=gradient_tolerance,
            max_backtracks=max_backtracks,
            fixed_mask=fixed_mask,
        )
    except _NUMERICAL_EXCEPTIONS as exc:
        return _mark_numerical_failure(base, "optimization_failure", exc)

    try:
        final = relaxed.field.components
        fixed_values = final[fixed_mask] - initial[fixed_mask]
        maximum_deviation = (
            0.0 if fixed_values.size == 0 else float(np.max(np.abs(fixed_values)))
        )
        if not np.isfinite(maximum_deviation):
            raise FloatingPointError("non-finite fixed-site deviation")
        fixed_unchanged = bool(np.array_equal(final[fixed_mask], initial[fixed_mask]))
        fits = []
        rotations = []
        for mask, center in zip(anchor_masks, anchor_centers):
            rotation, fit = _fit_anchor_rotation(
                initial, final, mask, coordinates, center, anchor_radius
            )
            fits.append(fit)
            rotations.append(rotation)
        relative_angle = None
        if len(rotations) == 2:
            relative_change = rotations[1] @ rotations[0].T
            relative_angle = float(
                np.arccos(
                    np.clip((np.trace(relative_change) - 1.0) / 2.0, -1.0, 1.0)
                )
            )
            if not np.isfinite(relative_angle):
                raise FloatingPointError("non-finite relative anchor orientation diagnostic")
        orientation_ok = all(
            float(item["rotation_angle_rad"]) <= orientation_tolerance_rad
            and float(item["weighted_relative_residual"]) <= residual_tolerance
            for item in fits
        ) and (relative_angle is None or relative_angle <= orientation_tolerance_rad)

        final_diagnostics = compute_nearest_neighbor_diagnostics(
            relaxed.field, f_pi=f_pi, e=e
        )
        final_energy = float(final_diagnostics.energy_total)
        final_total_charge = float(final_diagnostics.topological_charge)
        if not np.all(np.isfinite((final_energy, final_total_charge))):
            raise FloatingPointError("non-finite final diagnostic")
        final_charges = _component_charges(relaxed.field, charge_centers)
        drifts = tuple(
            final_value - initial_value
            for final_value, initial_value in zip(final_charges, initial_charges)
        )
        if not np.all(np.isfinite(drifts)):
            raise FloatingPointError("non-finite component charge drift")
        drift_status = (
            "DRIFT_EXCEEDS_DECLARED_SCREEN"
            if any(abs(value) > charge_drift_tolerance for value in drifts)
            else "DRIFT_WITHIN_DECLARED_SCREEN"
        )
        converged = (
            relaxed.termination == "gradient_tolerance"
            and relaxed.stationarity_status == "first_order_stationary"
        )
        if not fixed_unchanged:
            status = "CONSTRAINT_FAILURE"
        elif not orientation_ok:
            status = "ORIENTATION_UNVERIFIED"
        elif not converged:
            status = "NOT_CONVERGED"
        else:
            status = "CONVERGED_TO_DECLARED_FIRST_ORDER_TOLERANCE"

        energy_history = [float(value) for value in relaxed.energy_history]
        charge_history = [float(value) for value in relaxed.topological_charge_history]
        if not energy_history or not np.all(np.isfinite(energy_history)):
            raise FloatingPointError("non-finite relaxation energy history")
        if not charge_history or not np.all(np.isfinite(charge_history)):
            raise FloatingPointError("non-finite relaxation charge history")
        base.update(
            {
                "status": status,
                "initial_energy": energy_history[0],
                "final_energy": final_energy,
                "energy_history": energy_history,
                "total_approximate_charge_history": charge_history,
                "final_total_approximate_charge": final_total_charge,
                "final_component_approximate_charges": list(final_charges),
                "component_charge_drift": list(drifts),
                "charge_drift_status": drift_status,
                "iterations": int(relaxed.iterations),
                "termination": relaxed.termination,
                "stationarity_status": relaxed.stationarity_status,
                "minimum_certified": False,
                "curvature_screen": (
                    None
                    if relaxed.curvature_diagnostics is None
                    else {
                        "assessment": relaxed.curvature_diagnostics.assessment,
                        "probe_count": relaxed.curvature_diagnostics.probe_count,
                        "most_negative_directional_curvature": relaxed.curvature_diagnostics.most_negative_directional_curvature,
                        "minimum_certified": False,
                    }
                ),
                "constraints": {
                    "fixed_site_count": int(np.count_nonzero(fixed_mask)),
                    "fixed_sites_unchanged": fixed_unchanged,
                    "maximum_fixed_site_absolute_deviation": maximum_deviation,
                },
                "orientation_fits": fits,
                "relative_anchor_frame_change_rad": relative_angle,
            }
        )
    except _NUMERICAL_EXCEPTIONS as exc:
        return _mark_numerical_failure(base, "final_diagnostics_failure", exc)

    return base


def run_constrained_two_hedgehog_relaxation(
    *,
    shape: Sequence[int],
    spacing: Sequence[float],
    radius: float,
    separation_vector: Sequence[float],
    relative_isorotation: Sequence[float],
    anchor_radius: float,
    code_revision: str,
    f_pi: float = 1.0,
    e: float = 1.0,
    max_iterations: int = 40,
    initial_step: float = 1.0e-3,
    gradient_tolerance: float = 1.0e-7,
    max_backtracks: int = 8,
    orientation_tolerance_rad: float = 1.0e-6,
    orientation_residual_tolerance: float = 1.0e-8,
    charge_drift_tolerance: float = 0.25,
) -> dict[str, object]:
    """Relax a two-hedgehog field and two corresponding isolated controls.

    Each work unit uses the same grid, nearest-neighbor objective, couplings,
    iteration limit, line-search settings, and local Dirichlet anchor patches.
    The pair freezes both patches; each isolated control freezes its matching
    patch. A final pair-minus-isolated value is emitted only when all three
    runs reach the declared first-order gradient tolerance and preserve their
    constraints/orientation checks. This does not certify a minimum.
    """
    grid_shape = _shape3(shape)
    node_count = prod(grid_shape)
    grid_spacing = validate_spacing(spacing)
    _cell_volume(grid_spacing)
    length_radius = _real_scalar(radius, "radius", positive=True)
    patch_radius = _real_scalar(anchor_radius, "anchor_radius", positive=True)
    if patch_radius >= length_radius:
        raise ValueError("anchor_radius must be smaller than radius")
    separation = _real_vector(separation_vector, "separation_vector", 3)
    supplied_rotation, used_rotation = _unit_quaternion(relative_isorotation)
    coupling_f_pi = _real_scalar(f_pi, "f_pi", positive=True)
    coupling_e = _real_scalar(e, "e", positive=True)
    _gradient_coefficients(coupling_f_pi, coupling_e)
    step = _real_scalar(initial_step, "initial_step", positive=True)
    tolerance = _real_scalar(gradient_tolerance, "gradient_tolerance", positive=True)
    angle_tolerance = _real_scalar(
        orientation_tolerance_rad, "orientation_tolerance_rad", positive=True
    )
    residual_tolerance = _real_scalar(
        orientation_residual_tolerance, "orientation_residual_tolerance", positive=True
    )
    charge_tolerance = _real_scalar(
        charge_drift_tolerance, "charge_drift_tolerance", positive=True
    )
    iteration_limit = _integer(
        max_iterations, "max_iterations", minimum=1, maximum=_MAX_ITERATIONS
    )
    backtrack_limit = _integer(
        max_backtracks, "max_backtracks", minimum=0, maximum=_MAX_BACKTRACKS
    )
    if not isinstance(code_revision, str) or re.fullmatch(r"[0-9a-fA-F]{40}", code_revision) is None:
        raise ValueError("code_revision must be a full 40-character commit SHA")

    estimated_visits = (
        3
        * node_count
        * (1 + iteration_limit * (backtrack_limit + 2) + 40)
    )
    if estimated_visits > _MAX_ESTIMATED_NODE_VISITS:
        raise ValueError("estimated work exceeds the bounded node-visit budget")

    half_extents = np.asarray(
        [(size - 1) * step_size / 2.0 for size, step_size in zip(grid_shape, grid_spacing)],
        dtype=np.float64,
    )
    distance = float(np.hypot(np.hypot(*separation[:2]), separation[2]))
    centers = (
        tuple(-component / 2.0 for component in separation),
        tuple(component / 2.0 for component in separation),
    )
    stencil_margin = max(grid_spacing)
    if distance <= 2.0 * patch_radius + 2.0 * stencil_margin:
        raise ValueError("anchor patches must not overlap within the stencil margin")
    if distance <= length_radius + patch_radius + stencil_margin:
        raise ValueError("each anchor patch must clear the other hedgehog support and stencil")
    for center in centers:
        available = half_extents - np.abs(np.asarray(center))
        if np.any(available <= patch_radius + stencil_margin):
            raise ValueError("anchor patches must clear every box boundary by a stencil margin")

    identity = _IDENTITY
    pair = multi_hedgehog(
        grid_shape,
        centers=centers,
        radii=(length_radius, length_radius),
        spacing=grid_spacing,
        isorotations=(identity, used_rotation),
        length_unit="dimensionless",
        allow_overlaps=True,
    )
    isolated_a = multi_hedgehog(
        grid_shape,
        centers=(centers[0],),
        radii=(length_radius,),
        spacing=grid_spacing,
        isorotations=(identity,),
        length_unit="dimensionless",
    )
    isolated_b = multi_hedgehog(
        grid_shape,
        centers=(centers[1],),
        radii=(length_radius,),
        spacing=grid_spacing,
        isorotations=(used_rotation,),
        length_unit="dimensionless",
    )

    masks = _anchor_masks(grid_shape, grid_spacing, centers, patch_radius)
    coordinates = _coordinates(grid_shape, grid_spacing)
    anchor_match_deviations = []
    for index, isolated in enumerate((isolated_a, isolated_b)):
        if not np.any(masks[index]):
            raise ValueError("each anchor patch must contain sampled grid sites")
        _fit_anchor_rotation(
            pair.components,
            pair.components,
            masks[index],
            coordinates,
            centers[index],
            patch_radius,
        )
        deviation = float(
            np.max(np.abs(pair.components[masks[index]] - isolated.components[masks[index]]))
        )
        anchor_match_deviations.append(deviation)
        if not np.isfinite(deviation):
            raise ValueError("pair and isolated initial anchor mismatch must be finite")
        if deviation > _ANCHOR_MATCH_ABS_TOLERANCE:
            raise ValueError("pair and isolated initial anchor patches disagree beyond tolerance")

    pair_mask = masks[0] | masks[1]
    input_record: dict[str, object] = {
        "schema_version": _INPUT_SCHEMA,
        "code_revision": code_revision.lower(),
        "data_mode": "synthetic_only",
        "randomness": "none_deterministic",
        "seed": None,
        "shape": list(grid_shape),
        "grid_node_count": node_count,
        "spacing": list(grid_spacing),
        "length_unit": "dimensionless",
        "energy_unit": "dimensionless_lattice",
        "boundary": "fixed_vacuum",
        "radius": length_radius,
        "anchor_radius": patch_radius,
        "separation_vector": list(separation),
        "centers": [list(centers[0]), list(centers[1])],
        "relative_isorotation_input": list(supplied_rotation),
        "relative_isorotation_used": list(used_rotation),
        "anchor_pair_isolated_match_abs_tolerance": _ANCHOR_MATCH_ABS_TOLERANCE,
        "anchor_pair_isolated_max_abs_deviation": anchor_match_deviations,
        "f_pi": coupling_f_pi,
        "e": coupling_e,
        "solver": "nearest_neighbor_forward_link_v1",
        "max_iterations_per_run": iteration_limit,
        "initial_step": step,
        "gradient_tolerance": tolerance,
        "max_backtracks_per_iteration": backtrack_limit,
        "orientation_tolerance_rad": angle_tolerance,
        "orientation_residual_tolerance": residual_tolerance,
        "charge_drift_tolerance": charge_tolerance,
        "work_limits": {
            "run_count": 3,
            "max_grid_nodes": _MAX_GRID_NODES,
            "max_estimated_node_visits": _MAX_ESTIMATED_NODE_VISITS,
            "estimated_node_visits_upper_bound": estimated_visits,
        },
    }
    input_digest = _sha256(input_record)
    common = dict(
        anchor_radius=patch_radius,
        orientation_tolerance_rad=angle_tolerance,
        residual_tolerance=residual_tolerance,
        charge_drift_tolerance=charge_tolerance,
        f_pi=coupling_f_pi,
        e=coupling_e,
        max_iterations=iteration_limit,
        initial_step=step,
        gradient_tolerance=tolerance,
        max_backtracks=backtrack_limit,
    )
    runs = {
        "isolated_a": _one_relaxation(
            "isolated_a",
            isolated_a,
            masks[0],
            (masks[0],),
            (centers[0],),
            (centers[0],),
            coordinates,
            **common,
        ),
        "isolated_b": _one_relaxation(
            "isolated_b",
            isolated_b,
            masks[1],
            (masks[1],),
            (centers[1],),
            (centers[1],),
            coordinates,
            **common,
        ),
        "pair": _one_relaxation(
            "pair",
            pair,
            pair_mask,
            masks,
            centers,
            centers,
            coordinates,
            **common,
        ),
    }
    all_converged = all(
        item.get("status") == "CONVERGED_TO_DECLARED_FIRST_ORDER_TOLERANCE"
        for item in runs.values()
    )
    initial_energies = (
        runs["pair"].get("initial_energy"),
        runs["isolated_a"].get("initial_energy"),
        runs["isolated_b"].get("initial_energy"),
    )
    initial_available = all(
        value is not None and bool(np.isfinite(value))
        for value in initial_energies
    )
    initial_excess = (
        float(initial_energies[0] - initial_energies[1] - initial_energies[2])
        if initial_available
        else None
    )
    if initial_excess is not None and not np.isfinite(initial_excess):
        initial_excess = None

    final_energies = (
        runs["pair"].get("final_energy"),
        runs["isolated_a"].get("final_energy"),
        runs["isolated_b"].get("final_energy"),
    )
    comparison_available = all_converged and all(
        value is not None and bool(np.isfinite(value))
        for value in final_energies
    )
    final_excess = (
        float(final_energies[0] - final_energies[1] - final_energies[2])
        if comparison_available
        else None
    )
    if final_excess is not None and not np.isfinite(final_excess):
        final_excess = None
        comparison_available = False
    result: dict[str, object] = {
        "schema_version": _RESULT_SCHEMA,
        "status": "COMPARISON_AVAILABLE" if comparison_available else "COMPARISON_WITHHELD",
        "evidence_class": "synthetic_constrained_lattice_optimization",
        "scientific_pass": False,
        "claim_scope": "finite-grid, finite-box excess energy conditional on the specified frozen anchor patches",
        "input": input_record,
        "input_sha256": input_digest,
        "runs": runs,
        "comparison": {
            "initial_pair_minus_isolated_energy": initial_excess,
            "final_pair_minus_isolated_energy": final_excess,
            "available_only_if_all_three_converged_and_constraints_pass": comparison_available,
        },
        "limitations": [
            "frozen local Dirichlet patches are not a fixed-separation/fixed-isorotation collective-coordinate minimum",
            "first-order stationarity and the bounded curvature screen do not certify a local or global minimum",
            "no multistart or grid-refinement study is performed",
            "anchor-size and anchor-placement sensitivity remain required validation",
            "approximate component charges use a grid-anchor Voronoi partition and are not integer-sector proofs",
            "approximate charge drift is compared only with a declared numerical screen and does not establish integer-sector preservation",
            "not a force, free-pair potential, binding energy, physical energy, or physical time evolution",
            "synthetic engineering evidence only; no biological or empirical inference",
        ],
    }
    result["result_sha256"] = _sha256(result)
    serialize_constrained_result(result)
    return result


def serialize_constrained_result(result: dict[str, object]) -> str:
    """Verify the self-excluding SHA-256 and serialize finite JSON deterministically."""
    if not isinstance(result, dict) or result.get("schema_version") != _RESULT_SCHEMA:
        raise ValueError("unsupported constrained-relaxation result schema")
    input_record = result.get("input")
    if not isinstance(input_record, dict) or result.get("input_sha256") != _sha256(input_record):
        raise ValueError("input checksum mismatch")
    expected = result.get("result_sha256")
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    if not isinstance(expected, str) or expected != _sha256(payload):
        raise ValueError("result checksum mismatch")
    return _canonical_json(result)


