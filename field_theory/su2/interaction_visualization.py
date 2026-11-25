"""Optional headless plots for synthetic static interaction sweeps.

The data builder is pure Python and does not import Matplotlib. The optional
renderer attaches ``FigureCanvasAgg`` directly to a ``Figure``; it does not
import pyplot or change Matplotlib's process-wide backend.
"""

from __future__ import annotations

import math
import hashlib
import json
from numbers import Real
from pathlib import Path
from typing import Any

from .interaction_sweep import (
    InteractionGridLevel,
    SWEEP_SCHEMA_VERSION,
    TwoHedgehogSweepPoint,
    TwoHedgehogSweepResult,
    TwoHedgehogSweepSpec,
    _validate_spec,
)


PLOT_DATA_SCHEMA_VERSION = "su2.two_hedgehog_interaction_plot_data.v1"


class InteractionSweepVisualizationUnavailable(ImportError):
    """Raised when optional Matplotlib support is unavailable."""


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _orientation_label(value: tuple[float, ...], index: int) -> str:
    formatted = ", ".join(f"{component:.6g}" for component in value)
    return f"orientation[{index:02d}] q=({formatted})"


def _numeric_sequence(value: object, name: str, length: int) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a finite numeric sequence")
    if len(value) != length:
        raise ValueError(f"{name} must contain {length} values")
    return tuple(_finite_number(item, name) for item in value)


def _check_close(
    actual: object,
    expected: float,
    point_id: str,
    name: str,
    *,
    context: str = "evaluator input metadata",
) -> None:
    value = _finite_number(actual, name)
    if not math.isclose(value, expected, rel_tol=1.0e-12, abs_tol=1.0e-12):
        raise ValueError(f"point {point_id} {name} does not match {context}")


def _check_sequence(
    actual: object, expected: tuple[float, ...], point_id: str, name: str
) -> None:
    values = _numeric_sequence(actual, name, len(expected))
    if any(
        not math.isclose(value, target, rel_tol=1.0e-12, abs_tol=1.0e-12)
        for value, target in zip(values, expected)
    ):
        raise ValueError(
            f"point {point_id} {name} does not match evaluator input metadata"
        )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_point_metadata(
    point: TwoHedgehogSweepPoint,
    spec: TwoHedgehogSweepSpec,
    orientation: tuple[float, ...],
    separation: float,
    expected_vector: tuple[float, float, float],
    level: InteractionGridLevel,
    evaluator_result: dict[str, Any],
) -> None:
    point_id = point.point_id
    metadata = evaluator_result.get("input_metadata")
    if not isinstance(metadata, dict):
        raise ValueError(f"point {point_id} is missing evaluator input metadata")
    if _canonical_sha256(metadata) != evaluator_result.get("input_sha256"):
        raise ValueError(f"point {point_id} evaluator input metadata checksum is invalid")
    if _canonical_sha256(evaluator_result) != point.result_sha256:
        raise ValueError(f"point {point_id} evaluator result checksum is invalid")

    if metadata.get("schema_version") != "su2.two_hedgehog_interaction.input.v1":
        raise ValueError(f"point {point_id} has unsupported evaluator input metadata")
    if metadata.get("ansatz") != "compact_c1_hedgehog_v1":
        raise ValueError(f"point {point_id} has unsupported evaluator input metadata ansatz")
    if metadata.get("energy_method") != "nearest_neighbor_forward_link_v1":
        raise ValueError(f"point {point_id} has unsupported evaluator input metadata energy method")
    if metadata.get("vacuum") != [1.0, 0.0, 0.0, 0.0]:
        raise ValueError(f"point {point_id} has unsupported evaluator input metadata vacuum")
    if metadata.get("composition_order") != "U_A * (G U_B G†)":
        raise ValueError(f"point {point_id} has unsupported evaluator input metadata composition order")
    if metadata.get("allow_overlaps_in_product_ansatz") is not True:
        raise ValueError(f"point {point_id} has unsupported evaluator input metadata overlap mode")
    if metadata.get("code_revision") != spec.code_revision:
        raise ValueError(f"point {point_id} code revision does not match evaluator input metadata")
    if metadata.get("length_unit") != "dimensionless":
        raise ValueError(f"point {point_id} length unit does not match evaluator input metadata")
    if metadata.get("energy_unit") != "dimensionless_lattice":
        raise ValueError(f"point {point_id} energy unit does not match evaluator input metadata")
    if metadata.get("boundary") != "fixed_vacuum":
        raise ValueError(f"point {point_id} boundary does not match evaluator input metadata")
    supported_metadata = {
        "ansatz": "compact_c1_hedgehog_v1",
        "energy_method": "nearest_neighbor_forward_link_v1",
        "vacuum": [1.0, 0.0, 0.0, 0.0],
        "composition_order": "U_A * (G U_B G†)",
        "allow_overlaps_in_product_ansatz": True,
        "isorotation_a": [1.0, 0.0, 0.0, 0.0],
    }
    if any(metadata.get(key) != expected for key, expected in supported_metadata.items()):
        raise ValueError(f"point {point_id} has unsupported evaluator input metadata values")

    if metadata.get("shape") != list(level.shape):
        raise ValueError(f"point {point_id} grid shape does not match evaluator input metadata")
    node_count = math.prod(level.shape)
    if metadata.get("grid_node_count") != node_count:
        raise ValueError(f"point {point_id} grid node count does not match evaluator input metadata")
    spacing = _numeric_sequence(level.spacing, "grid spacing", 3)
    extent = tuple((size - 1) * step for size, step in zip(level.shape, spacing))
    _check_sequence(metadata.get("spacing"), spacing, point_id, "grid spacing")
    _check_sequence(metadata.get("box_extent"), extent, point_id, "grid box extent")

    _check_close(metadata.get("radius"), spec.radius, point_id, "radius")
    _check_close(metadata.get("f_pi"), spec.f_pi, point_id, "f_pi")
    _check_close(metadata.get("e"), spec.e, point_id, "e")
    _check_sequence(point.separation_vector, expected_vector, point_id, "point separation vector")
    _check_sequence(metadata.get("separation_vector"), expected_vector, point_id, "separation vector")
    distance = math.hypot(math.hypot(*expected_vector[:2]), expected_vector[2])
    _check_close(metadata.get("separation_distance"), distance, point_id, "separation distance")
    expected_centers = tuple(
        tuple(sign * component / 2.0 for component in expected_vector)
        for sign in (-1.0, 1.0)
    )
    centers = metadata.get("centers")
    if not isinstance(centers, (list, tuple)) or len(centers) != 2:
        raise ValueError(f"point {point_id} centers do not match evaluator input metadata")
    for actual, expected in zip(centers, expected_centers):
        _check_sequence(actual, expected, point_id, "centers")

    _check_sequence(metadata.get("isorotation_b_input"), orientation, point_id, "isorotation input")
    _check_sequence(metadata.get("isorotation_b_used"), orientation, point_id, "isorotation used")
    controls = metadata.get("dimensionless_controls")
    if not isinstance(controls, dict):
        raise ValueError(f"point {point_id} is missing evaluator dimensionless controls")
    lambda_value = spec.e * spec.f_pi
    energy_scale = spec.f_pi / spec.e
    _check_close(controls.get("lambda"), lambda_value, point_id, "dimensionless lambda")
    _check_close(controls.get("E0"), energy_scale, point_id, "dimensionless E0")
    _check_close(controls.get("rho"), lambda_value * spec.radius, point_id, "dimensionless rho")
    _check_close(controls.get("s"), distance / spec.radius, point_id, "dimensionless s")
    excess = evaluator_result.get("excess")
    if not isinstance(excess, dict):
        raise ValueError(f"point {point_id} is missing evaluator excess metadata")
    _check_close(excess.get("energy_scale_E0"), energy_scale, point_id, "energy scale E0")


def _validate_energy_payload(
    evaluator_result: dict[str, Any], spec: TwoHedgehogSweepSpec, point_id: str
) -> None:
    energies: dict[str, dict[str, float]] = {}
    for label in ("energy_a", "energy_b", "energy_pair"):
        record = evaluator_result.get(label)
        if not isinstance(record, dict):
            raise ValueError(f"point {point_id} is missing {label} energy breakdown")
        sigma = _finite_number(record.get("energy_sigma"), f"{label} sigma energy")
        skyrme = _finite_number(record.get("energy_skyrme"), f"{label} Skyrme energy")
        total = _finite_number(record.get("energy_total"), f"{label} total energy")
        _finite_number(record.get("topological_charge"), f"{label} topological charge")
        _check_close(
            total,
            sigma + skyrme,
            point_id,
            f"{label} energy_total",
            context="energy breakdown arithmetic",
        )
        energies[label] = {
            "energy_sigma": sigma,
            "energy_skyrme": skyrme,
            "energy_total": total,
        }

    excess = evaluator_result.get("excess")
    if not isinstance(excess, dict):
        raise ValueError(f"point {point_id} is missing excess-energy arithmetic")
    expected_deltas = {
        "delta_energy_sigma": (
            energies["energy_pair"]["energy_sigma"]
            - energies["energy_a"]["energy_sigma"]
            - energies["energy_b"]["energy_sigma"]
        ),
        "delta_energy_skyrme": (
            energies["energy_pair"]["energy_skyrme"]
            - energies["energy_a"]["energy_skyrme"]
            - energies["energy_b"]["energy_skyrme"]
        ),
        "delta_energy_total": (
            energies["energy_pair"]["energy_total"]
            - energies["energy_a"]["energy_total"]
            - energies["energy_b"]["energy_total"]
        ),
    }
    deltas = {
        name: _finite_number(excess.get(name), name) for name in expected_deltas
    }
    for name, expected in expected_deltas.items():
        _check_close(
            deltas[name],
            expected,
            point_id,
            name,
            context="pair-minus-isolated energy arithmetic",
        )
    _check_close(
        deltas["delta_energy_total"],
        deltas["delta_energy_sigma"] + deltas["delta_energy_skyrme"],
        point_id,
        "delta_energy_total component sum",
        context="energy component arithmetic",
    )

    energy_scale = _finite_number(excess.get("energy_scale_E0"), "energy scale E0")
    if energy_scale <= 0.0:
        raise ValueError(f"point {point_id} energy scale E0 must be positive")
    _check_close(
        energy_scale,
        spec.f_pi / spec.e,
        point_id,
        "energy scale E0",
    )
    v_h = _finite_number(excess.get("V_h"), "dimensionless lattice excess V_h")
    _check_close(
        v_h,
        deltas["delta_energy_total"] / energy_scale,
        point_id,
        "V_h",
        context="energy ratio arithmetic",
    )


def build_interaction_sweep_plot_data(
    result: TwoHedgehogSweepResult,
) -> dict[str, Any]:
    """Return deterministic, Matplotlib-free curve data and scope metadata.

    One curve is produced for each declared relative isorotation and grid
    level. Samples are sorted by dimensionless separation ``s=d/R`` even if
    the input separation axis was declared in another order. The sweep ID is
    the deterministic digest of the schema version, declared spec, and
    point-result checksums ordered by canonical axis keys after validation. It
    identifies canonical axis-keyed logical content, not the byte-for-byte
    order of the point array serialized by ``TwoHedgehogSweepResult.to_json``;
    this builder is invariant to point storage order. The ID does not
    authenticate code or the runtime environment.
    """
    if not isinstance(result, TwoHedgehogSweepResult):
        raise ValueError("result must be a TwoHedgehogSweepResult")
    spec = result.spec
    if not isinstance(spec, TwoHedgehogSweepSpec):
        raise ValueError("result must contain a TwoHedgehogSweepSpec")
    _validate_spec(spec)

    orientations = tuple(tuple(value) for value in spec.relative_isorotations)
    levels = tuple(spec.grid_levels)
    separations = tuple(float(value) for value in spec.separation_values)
    if len(result.points) != spec.point_count:
        raise ValueError("result points do not cover the declared sweep axes")

    groups: dict[tuple[tuple[float, ...], str], list[tuple[float, float, dict[str, str]]]] = {
        (orientation, level.level_id): []
        for orientation in orientations
        for level in levels
    }
    expected = {
        (orientation, level.level_id, separation)
        for orientation in orientations
        for level in levels
        for separation in separations
    }
    canonical_point_keys = [
        (orientation, level.level_id, separation)
        for separation in separations
        for orientation in orientations
        for level in levels
    ]
    point_id_by_key = {
        key: f"point-{index:04d}"
        for index, key in enumerate(canonical_point_keys)
    }
    seen: set[tuple[tuple[float, ...], str, float]] = set()
    seen_point_ids: set[str] = set()
    points_by_key: dict[
        tuple[tuple[float, ...], str, float], TwoHedgehogSweepPoint
    ] = {}

    for point in result.points:
        if not isinstance(point, TwoHedgehogSweepPoint):
            raise ValueError("result points must be TwoHedgehogSweepPoint values")
        orientation = tuple(point.relative_isorotation)
        if orientation not in orientations:
            raise ValueError("point relative isorotation is outside the declared axes")
        if not isinstance(point.grid_level, InteractionGridLevel):
            raise ValueError("point grid level must be an InteractionGridLevel")
        matching_level = next(
            (
                level
                for level in levels
                if level.level_id == point.grid_level.level_id
            ),
            None,
        )
        if matching_level is None or matching_level != point.grid_level:
            raise ValueError("point grid level is outside the declared axes")

        separation = _finite_number(point.separation, "point separation")
        if separation not in separations:
            raise ValueError("point separation is outside the declared axis")
        s_value = separation / spec.radius
        if not math.isfinite(s_value):
            raise ValueError("dimensionless separation must be finite")
        key = (orientation, point.grid_level.level_id, separation)
        if key not in expected or key in seen:
            raise ValueError("result contains an unexpected or duplicate sweep point")
        seen.add(key)

        evaluator_result = point.evaluator_result
        expected_vector = tuple(
            separation * direction
            for direction in spec.separation_direction
        )
        if not all(math.isfinite(value) for value in expected_vector):
            raise ValueError("sweep separation vector must be finite")
        _validate_point_metadata(
            point,
            spec,
            orientation,
            separation,
            expected_vector,
            matching_level,
            evaluator_result,
        )
        if evaluator_result.get("schema_version") != "su2.two_hedgehog_interaction.result.v1":
            raise ValueError(f"point {point.point_id} has unsupported evaluator result schema")
        if (
            evaluator_result.get("status") != "SYNTHETIC_STATIC_PRODUCT_ANSATZ"
            or evaluator_result.get("evidence_class") != "synthetic_static_model"
            or evaluator_result.get("scientific_pass") is not False
        ):
            raise ValueError(
                f"point {point.point_id} has unsupported evaluator evidence status"
            )
        _validate_energy_payload(evaluator_result, spec, point.point_id)
        excess = evaluator_result.get("excess")
        if not isinstance(excess, dict):
            raise ValueError("evaluator result is missing excess-energy metadata")
        v_h = _finite_number(excess.get("V_h"), "dimensionless lattice excess V_h")
        input_sha256 = evaluator_result.get("input_sha256")
        if not isinstance(input_sha256, str):
            raise ValueError("evaluator result is missing its input checksum")
        expected_point_id = point_id_by_key[key]
        if not isinstance(point.point_id, str) or point.point_id != expected_point_id:
            raise ValueError("sweep point ids must match canonical axis keys")
        if point.point_id in seen_point_ids:
            raise ValueError("sweep point ids must be unique strings")
        seen_point_ids.add(point.point_id)
        points_by_key[key] = point
        groups[(orientation, point.grid_level.level_id)].append(
            (
                s_value,
                v_h,
                {
                    "point_id": point.point_id,
                    "result_sha256": point.result_sha256,
                    "evaluator_input_sha256": input_sha256,
                },
            )
        )

    if seen != expected:
        raise ValueError("result points do not form the declared Cartesian sweep")

    expected_sweep_id = _canonical_sha256(
        {
            "schema_version": SWEEP_SCHEMA_VERSION,
            "spec": spec.to_dict(),
            "point_result_sha256": [
                points_by_key[key].result_sha256 for key in canonical_point_keys
            ],
        }
    )
    if result.sweep_id != expected_sweep_id:
        raise ValueError(
            "result sweep_id does not match the declared spec and ordered point checksums"
        )

    curves: list[dict[str, Any]] = []
    for orientation_index, orientation in enumerate(orientations):
        for level in levels:
            samples = sorted(
                groups[(orientation, level.level_id)], key=lambda sample: sample[0]
            )
            curves.append(
                {
                    "relative_isorotation": list(orientation),
                    "grid_level": level.level_id,
                    "label": (
                        f"{_orientation_label(orientation, orientation_index)}; "
                        f"grid={level.level_id}"
                    ),
                    "s_values": [sample[0] for sample in samples],
                    "v_h_values": [sample[1] for sample in samples],
                    "point_refs": [sample[2] for sample in samples],
                }
            )

    return {
        "schema_version": PLOT_DATA_SCHEMA_VERSION,
        "sweep_id": result.sweep_id,
        "axes": {
            "x": {
                "symbol": "s",
                "label": "Dimensionless separation, s = d/R",
                "unit": "dimensionless",
            },
            "y": {
                "symbol": "V_h",
                "label": "Dimensionless lattice excess, V_h = ΔE/E₀",
                "unit": "dimensionless_lattice",
            },
        },
        "curves": curves,
        "grid_level_note": (
            "Grid levels are discretization comparisons; convergence is not assumed."
        ),
        "scope_note": (
            "Synthetic static product-ansatz lattice excess only; this is not a "
            "force, relaxed solution, time evolution, or scientific validation."
        ),
        "evidence_class": "synthetic_static_model",
        "scientific_pass": False,
    }


def plot_two_hedgehog_interaction_sweep(
    result: TwoHedgehogSweepResult, destination: str | Path
) -> Path:
    """Write a headless PNG of dimensionless lattice excess versus ``s``.

    ``destination`` is an explicit caller-controlled path. Its parent
    directories are created as needed, and an existing destination file is
    overwritten directly (the write is not atomic).

    Matplotlib is optional and imported only when this renderer is called.
    Each declared orientation/grid-level pair is rendered as a separate curve.
    """
    plot_data = build_interaction_sweep_plot_data(result)
    try:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
    except ImportError as exc:
        raise InteractionSweepVisualizationUnavailable(
            "plot rendering requires the optional matplotlib dependency"
        ) from exc

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure = Figure(figsize=(8.5, 5.0), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    axis = figure.add_subplot(1, 1, 1)
    for curve in plot_data["curves"]:
        axis.plot(
            curve["s_values"],
            curve["v_h_values"],
            marker="o",
            label=curve["label"],
        )

    axis.set(
        xlabel=plot_data["axes"]["x"]["label"],
        ylabel=plot_data["axes"]["y"]["label"],
        title="Static two-hedgehog product-ansatz sweep",
    )
    axis.grid(True, alpha=0.25)
    axis.legend(fontsize="small")
    figure.suptitle(
        "Synthetic static diagnostic — grid levels are comparisons; convergence is not assumed",
        fontsize=10,
    )
    canvas.print_png(
        target,
        metadata={"Software": "NeuroTopology-Sim SU2 interaction sweep plot"},
    )
    return target
