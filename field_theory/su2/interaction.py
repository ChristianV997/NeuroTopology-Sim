"""Static dimensionless excess energy for a two-hedgehog product ansatz.

This evaluator compares one unrelaxed product field with its two isolated
factors on identical fixed-vacuum grids using the nearest-neighbor lattice
functional. Its result is a synthetic ansatz energy difference, not a force,
relaxed potential, stability result, or physical time evolution.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from math import prod
from typing import Optional

import numpy as np

from .field import validate_spacing
from .generators import multi_hedgehog
from .nearest_neighbor import (
    NearestNeighborDiagnostics,
    _link_mask,
    compute_nearest_neighbor_diagnostics,
)

_MAX_GRID_NODES = 262_144
_INPUT_SCHEMA = "su2.two_hedgehog_interaction.input.v1"
_RESULT_SCHEMA = "su2.two_hedgehog_interaction.result.v1"
_VACUUM = (1.0, 0.0, 0.0, 0.0)
_IDENTITY_ISOROTATION = (1.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class EnergyBreakdown:
    """Nearest-neighbor energy components and unrounded charge estimate."""

    energy_sigma: float
    energy_skyrme: float
    energy_total: float
    topological_charge: float


@dataclass(frozen=True)
class TwoHedgehogInteractionResult:
    """Deterministic comparison of pair and isolated product-ansatz energies."""

    energy_a: EnergyBreakdown
    energy_b: EnergyBreakdown
    energy_pair: EnergyBreakdown
    delta_energy_sigma: float
    delta_energy_skyrme: float
    delta_energy_total: float
    energy_scale: float
    v_h: float
    stencil_overlap: bool
    input_metadata_json: str
    input_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Return a finite, JSON-compatible result record."""
        result = {
            "schema_version": _RESULT_SCHEMA,
            "status": "SYNTHETIC_STATIC_PRODUCT_ANSATZ",
            "evidence_class": "synthetic_static_model",
            "scientific_pass": False,
            "input_metadata": json.loads(self.input_metadata_json),
            "input_sha256": self.input_sha256,
            "energy_a": asdict(self.energy_a),
            "energy_b": asdict(self.energy_b),
            "energy_pair": asdict(self.energy_pair),
            "excess": {
                "delta_energy_sigma": self.delta_energy_sigma,
                "delta_energy_skyrme": self.delta_energy_skyrme,
                "delta_energy_total": self.delta_energy_total,
                "energy_scale_E0": self.energy_scale,
                "V_h": self.v_h,
            },
            "support_stencils_overlap": self.stencil_overlap,
            "limitations": [
                "unrelaxed compact-C1 product ansatz only",
                "not a force or a relaxed interaction potential",
                "not a stability result or physical time evolution",
                "compact support does not model long-range tails",
                "no opposite-charge, physical, or biological claim",
            ],
        }
        json.dumps(result, sort_keys=True, allow_nan=False)
        return result


def _shape3(value: object) -> tuple[int, int, int]:
    try:
        shape = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError("shape must contain three integers >= 2") from exc
    if len(shape) != 3 or any(
        isinstance(size, (bool, np.bool_))
        or not isinstance(size, (int, np.integer))
        or int(size) < 2
        for size in shape
    ):
        raise ValueError("shape must contain three integers >= 2")
    return tuple(int(size) for size in shape)


def _positive_real(value: object, name: str) -> float:
    raw = np.asarray(value)
    if raw.ndim != 0 or raw.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a positive finite real scalar")
    result = float(raw)
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a positive finite real scalar")
    return result


def _real_vector(value: object, name: str, length: int) -> tuple[float, ...]:
    try:
        objects = np.asarray(value, dtype=object)
        if any(isinstance(item, (bool, np.bool_)) for item in objects.flat):
            raise ValueError(f"{name} must not contain booleans")
        raw = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real vector of length {length}") from exc
    if raw.shape != (length,) or raw.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a finite real vector of length {length}")
    values = raw.astype(np.float64, copy=False)
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{name} must be finite")
    return tuple(float(item) for item in values)


def _rotation(value: object) -> tuple[tuple[float, ...], tuple[float, ...]]:
    raw = _real_vector(value, "relative_isorotation", 4)
    values = np.asarray(raw, dtype=np.float64)
    norm = float(np.linalg.norm(values))
    if not np.isfinite(norm) or abs(norm - 1.0) > 1.0e-10:
        raise ValueError("relative_isorotation must have unit norm")
    normalized = values / norm
    return raw, tuple(float(item) for item in normalized)


def _energy_snapshot(diagnostics: NearestNeighborDiagnostics) -> EnergyBreakdown:
    return EnergyBreakdown(
        energy_sigma=float(diagnostics.energy_sigma),
        energy_skyrme=float(diagnostics.energy_skyrme),
        energy_total=float(diagnostics.energy_total),
        topological_charge=float(diagnostics.topological_charge),
    )


def _support_mask(
    shape: tuple[int, int, int],
    spacing: tuple[float, float, float],
    center: tuple[float, float, float],
    radius: float,
) -> np.ndarray:
    coordinates = tuple(
        (np.arange(size, dtype=np.float64) - (size - 1) / 2.0) * step
        for size, step in zip(shape, spacing)
    )
    dx = coordinates[0][:, None, None] - center[0]
    dy = coordinates[1][None, :, None] - center[1]
    dz = coordinates[2][None, None, :] - center[2]
    distance = np.hypot(np.hypot(dx, dy), dz)
    return distance < radius


def _stencil_contains_both(
    support_a: np.ndarray, support_b: np.ndarray, axes: tuple[int, ...]
) -> bool:
    """Test node membership in the actual forward stencil at each anchor."""
    shape = support_a.shape
    neighborhood_a = support_a.copy()
    neighborhood_b = support_b.copy()
    for axis in axes:
        neighborhood_a |= np.roll(support_a, -1, axis=axis)
        neighborhood_b |= np.roll(support_b, -1, axis=axis)
    # Share the nearest-neighbor energy's valid-anchor rule so this diagnostic
    # cannot silently substitute a different boundary stencil.
    valid = _link_mask(shape, axes, "fixed_vacuum")
    return bool(np.any(valid & neighborhood_a & neighborhood_b))


def _supports_share_energy_stencil(
    support_a: np.ndarray, support_b: np.ndarray
) -> bool:
    for axis in range(3):
        if _stencil_contains_both(support_a, support_b, (axis,)):
            return True
    for first in range(3):
        for second in range(first + 1, 3):
            if _stencil_contains_both(support_a, support_b, (first, second)):
                return True
    return False


def evaluate_two_hedgehog_interaction(
    *,
    shape: tuple[int, int, int],
    spacing,
    radius: float,
    separation_vector,
    relative_isorotation=_IDENTITY_ISOROTATION,
    f_pi: float = 1.0,
    e: float = 1.0,
    code_revision: Optional[str] = None,
) -> TwoHedgehogInteractionResult:
    """Evaluate pair-minus-isolated static energy in dimensionless lattice units.

    The centers are ``-separation_vector/2`` and ``+separation_vector/2``.
    The pair is composed as ``U_A * (G U_B G†)`` under the repository
    convention ``U=q0 I+i q·sigma``; a quaternion with axis-angle parameters
    ``(cos(theta/2), sin(theta/2)*axis)`` induces Rodrigues ``R(-theta)``.

    The first isorotation is identity. The second is a unit quaternion.
    Supports may overlap and are intentionally passed to the product ansatz
    with overlap enabled. This computes no relaxation or dynamics.
    """
    grid_shape = _shape3(shape)
    node_count = prod(grid_shape)
    if node_count > _MAX_GRID_NODES:
        raise ValueError(f"grid exceeds the {_MAX_GRID_NODES}-node interaction limit")
    grid_spacing = validate_spacing(spacing)
    length_radius = _positive_real(radius, "radius")
    separation = _real_vector(separation_vector, "separation_vector", 3)
    rotation_input, rotation_used = _rotation(relative_isorotation)
    f_value = _positive_real(f_pi, "f_pi")
    e_value = _positive_real(e, "e")
    if code_revision is not None and (
        not isinstance(code_revision, str) or not code_revision.strip()
    ):
        raise ValueError("code_revision must be a nonempty string or None")

    distance = float(np.hypot(np.hypot(separation[0], separation[1]), separation[2]))
    centers = (
        tuple(-component / 2.0 for component in separation),
        tuple(component / 2.0 for component in separation),
    )
    box_extent = tuple(
        float((size - 1) * step) for size, step in zip(grid_shape, grid_spacing)
    )
    half_extent = np.asarray(box_extent, dtype=np.float64) / 2.0
    if not np.all(np.isfinite(half_extent)) or not np.isfinite(distance):
        raise ValueError("grid extent and separation must be finite")
    for center in centers:
        available = half_extent - np.abs(center)
        if np.any(available <= 0.0) or np.any(length_radius >= available):
            raise ValueError("both support radii must fit strictly inside every grid face")

    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        lambda_value = e_value * f_value
        energy_scale = f_value / e_value
        rho = lambda_value * length_radius
        scaled_separation = distance / length_radius
    controls = (lambda_value, energy_scale, rho, scaled_separation)
    if not np.all(np.isfinite(controls)) or any(item <= 0.0 for item in controls[:3]):
        raise ValueError("dimensionless controls must be finite and positive")
    if not np.isfinite(scaled_separation) or scaled_separation < 0.0:
        raise ValueError("scaled separation must be finite and nonnegative")

    identity = _IDENTITY_ISOROTATION
    pair_field = multi_hedgehog(
        grid_shape,
        centers=centers,
        radii=(length_radius, length_radius),
        spacing=grid_spacing,
        isorotations=(identity, rotation_input),
        length_unit="dimensionless",
        allow_overlaps=True,
    )
    field_a = multi_hedgehog(
        grid_shape,
        centers=(centers[0],),
        radii=(length_radius,),
        spacing=grid_spacing,
        isorotations=(identity,),
        length_unit="dimensionless",
    )
    field_b = multi_hedgehog(
        grid_shape,
        centers=(centers[1],),
        radii=(length_radius,),
        spacing=grid_spacing,
        isorotations=(rotation_input,),
        length_unit="dimensionless",
    )

    diagnostic_a = compute_nearest_neighbor_diagnostics(
        field_a, f_pi=f_value, e=e_value, vacuum=_VACUUM
    )
    diagnostic_b = compute_nearest_neighbor_diagnostics(
        field_b, f_pi=f_value, e=e_value, vacuum=_VACUUM
    )
    diagnostic_pair = compute_nearest_neighbor_diagnostics(
        pair_field, f_pi=f_value, e=e_value, vacuum=_VACUUM
    )
    energy_a = _energy_snapshot(diagnostic_a)
    energy_b = _energy_snapshot(diagnostic_b)
    energy_pair = _energy_snapshot(diagnostic_pair)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        delta_sigma = float(
            energy_pair.energy_sigma - energy_a.energy_sigma - energy_b.energy_sigma
        )
        delta_skyrme = float(
            energy_pair.energy_skyrme - energy_a.energy_skyrme - energy_b.energy_skyrme
        )
        delta_total = float(
            energy_pair.energy_total - energy_a.energy_total - energy_b.energy_total
        )
        dimensionless_potential = float(delta_total / energy_scale)
    if not np.all(np.isfinite((delta_sigma, delta_skyrme, delta_total, dimensionless_potential))):
        raise FloatingPointError("non-finite pair-minus-isolated energy")

    masks = tuple(
        _support_mask(grid_shape, grid_spacing, center, length_radius) for center in centers
    )
    stencil_overlap = _supports_share_energy_stencil(masks[0], masks[1])
    input_metadata = {
        "schema_version": _INPUT_SCHEMA,
        "code_revision": code_revision,
        "ansatz": "compact_c1_hedgehog_v1",
        "energy_method": "nearest_neighbor_forward_link_v1",
        "shape": list(grid_shape),
        "grid_node_count": node_count,
        "spacing": list(grid_spacing),
        "box_extent": list(box_extent),
        "length_unit": "dimensionless",
        "energy_unit": "dimensionless_lattice",
        "boundary": "fixed_vacuum",
        "vacuum": list(_VACUUM),
        "radius": length_radius,
        "separation_vector": list(separation),
        "separation_distance": distance,
        "centers": [list(centers[0]), list(centers[1])],
        "isorotation_a": list(identity),
        "isorotation_b_input": list(rotation_input),
        "isorotation_b_used": list(rotation_used),
        "composition_order": "U_A * (G U_B G†)",
        "allow_overlaps_in_product_ansatz": True,
        "f_pi": f_value,
        "e": e_value,
        "dimensionless_controls": {
            "lambda": float(lambda_value),
            "E0": float(energy_scale),
            "rho": float(rho),
            "s": float(scaled_separation),
        },
        "grid_node_limit": _MAX_GRID_NODES,
    }
    metadata_json = json.dumps(
        input_metadata, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    checksum = hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()
    return TwoHedgehogInteractionResult(
        energy_a=energy_a,
        energy_b=energy_b,
        energy_pair=energy_pair,
        delta_energy_sigma=delta_sigma,
        delta_energy_skyrme=delta_skyrme,
        delta_energy_total=delta_total,
        energy_scale=float(energy_scale),
        v_h=dimensionless_potential,
        stencil_overlap=stencil_overlap,
        input_metadata_json=metadata_json,
        input_sha256=checksum,
    )
