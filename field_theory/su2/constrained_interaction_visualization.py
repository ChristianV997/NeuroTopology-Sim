"""Optional plot-data and headless visualization for constrained sensitivity runs.

This module is separate from the static product-ansatz visualization. Missing
or rejected comparisons are represented as statuses, never as zero-valued
energy points.
"""

from __future__ import annotations

import hashlib
import json
import math
from numbers import Real
from pathlib import Path
from typing import Any

from .constrained_interaction_sweep import (
    ConstrainedInteractionSensitivityResult,
    serialize_constrained_interaction_sensitivity_result,
)


PLOT_DATA_SCHEMA_VERSION = "su2.constrained_interaction_sensitivity_plot_data.v1"


class ConstrainedSensitivityVisualizationUnavailable(ImportError):
    """Raised when optional Matplotlib support is unavailable."""


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def build_constrained_sensitivity_plot_data(
    result: ConstrainedInteractionSensitivityResult | dict[str, object],
) -> dict[str, Any]:
    """Build deterministic plotting data without importing Matplotlib."""
    if isinstance(result, ConstrainedInteractionSensitivityResult):
        record = result.to_dict()
    elif isinstance(result, dict):
        record = result
    else:
        raise ValueError(
            "result must be a ConstrainedInteractionSensitivityResult or dict"
        )
    serialize_constrained_interaction_sensitivity_result(record)
    spec = record.get("spec")
    cases = record.get("cases")
    if not isinstance(spec, dict) or not isinstance(cases, list):
        raise ValueError("sensitivity result is missing its spec or cases")
    levels = spec.get("grid_levels")
    anchors = spec.get("anchor_radii")
    if not isinstance(levels, list) or not isinstance(anchors, list):
        raise ValueError("sensitivity spec is missing grid or anchor axes")

    level_by_id: dict[str, dict[str, Any]] = {}
    for level in levels:
        if not isinstance(level, dict) or not isinstance(level.get("level_id"), str):
            raise ValueError("grid level metadata is malformed")
        level_id = level["level_id"]
        if level_id in level_by_id:
            raise ValueError("grid level ids must be unique")
        spacing = level.get("spacing")
        if not isinstance(spacing, list) or len(spacing) != 3:
            raise ValueError("grid spacing metadata is malformed")
        spacing_values = tuple(
            _finite_number(value, "grid spacing") for value in spacing
        )
        if any(value <= 0.0 for value in spacing_values):
            raise ValueError("grid spacing must be positive")
        effective_spacing = math.prod(spacing_values) ** (1.0 / 3.0)
        if not math.isfinite(effective_spacing) or effective_spacing <= 0.0:
            raise ValueError("effective grid spacing must be finite and positive")
        level_by_id[level_id] = {
            "level_id": level_id,
            "shape": level.get("shape"),
            "spacing": list(spacing_values),
            "effective_spacing": effective_spacing,
            "box_extent": level.get("box_extent"),
        }

    anchor_values = tuple(
        _finite_number(value, "anchor radius") for value in anchors
    )
    if not anchor_values or any(value <= 0.0 for value in anchor_values):
        raise ValueError("anchor radii must be positive")

    points = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("case metadata must be an object")
        case_input = case.get("case_input")
        if not isinstance(case_input, dict):
            raise ValueError("case is missing its input metadata")
        grid_meta = case_input.get("grid_level")
        if not isinstance(grid_meta, dict):
            raise ValueError("case is missing its grid-level metadata")
        level_id = grid_meta.get("level_id")
        if level_id not in level_by_id:
            raise ValueError("case references an undeclared grid level")
        level = level_by_id[level_id]
        anchor_radius = _finite_number(
            case_input.get("anchor_radius"), "case anchor radius"
        )
        if anchor_radius not in anchor_values:
            raise ValueError("case references an undeclared anchor radius")
        available = case.get("comparison_available") is True
        excess = case.get("final_pair_minus_isolated_energy")
        if available:
            excess = _finite_number(excess, "pair-minus-isolated excess")
        elif excess is not None:
            raise ValueError("withheld cases must not contain a numeric excess")
        points.append(
            {
                "case_id": case.get("case_id"),
                "grid_level_id": level_id,
                "shape": level["shape"],
                "spacing": level["spacing"],
                "effective_spacing": level["effective_spacing"],
                "box_extent": level["box_extent"],
                "anchor_radius": anchor_radius,
                "comparison_available": available,
                "excess": excess if available else None,
                "status": case.get("status"),
            }
        )
    points.sort(
        key=lambda point: (
            point["anchor_radius"],
            point["effective_spacing"],
            point["grid_level_id"],
        )
    )

    groups = []
    for anchor_radius in anchor_values:
        groups.append(
            {
                "anchor_radius": anchor_radius,
                "points": [
                    point for point in points
                    if point["anchor_radius"] == anchor_radius
                ],
            }
        )
    payload: dict[str, Any] = {
        "schema_version": PLOT_DATA_SCHEMA_VERSION,
        "sweep_id": record.get("sweep_id"),
        "source_result_sha256": record.get("result_sha256"),
        "x_axis": {
            "name": "effective_grid_spacing",
            "definition": "(h_x*h_y*h_z)^(1/3)",
            "units": "dimensionless model length",
        },
        "y_axis": {
            "name": "pair_minus_isolated_excess",
            "units": "dimensionless lattice energy",
        },
        "series": groups,
        "status_points": points,
        "anchor_sensitivity_by_grid": record.get("anchor_sensitivity_by_grid"),
        "claim_scope": (
            "conditional finite-grid, finite-box excess; sensitivity visualization only"
        ),
        "unavailable_points_are_not_zero": True,
        "not_a_binding_energy": True,
        "not_a_force": True,
        "not_a_continuum_extrapolation": True,
        "scientific_pass": False,
    }
    payload["plot_data_sha256"] = _sha256(payload)
    serialize_constrained_sensitivity_plot_data(payload)
    return payload


def serialize_constrained_sensitivity_plot_data(
    data: dict[str, Any],
) -> str:
    """Validate and serialize the plot-data contract deterministically."""
    if not isinstance(data, dict) or data.get("schema_version") != PLOT_DATA_SCHEMA_VERSION:
        raise ValueError("unsupported constrained-sensitivity plot-data schema")
    if data.get("scientific_pass") is not False:
        raise ValueError("plot data cannot assert a scientific pass")
    for claim_flag in (
        "unavailable_points_are_not_zero",
        "not_a_binding_energy",
        "not_a_force",
        "not_a_continuum_extrapolation",
    ):
        if data.get(claim_flag) is not True:
            raise ValueError(f"plot-data claim limit {claim_flag} is required")
    if not isinstance(data.get("sweep_id"), str) or not isinstance(
        data.get("source_result_sha256"), str
    ):
        raise ValueError("plot data is missing its source identifiers")
    if data.get("claim_scope") != (
        "conditional finite-grid, finite-box excess; sensitivity visualization only"
    ):
        raise ValueError("plot-data claim scope is inconsistent")
    points = data.get("status_points")
    series = data.get("series")
    if not isinstance(points, list) or not isinstance(series, list):
        raise ValueError("plot data must contain points and series")
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("plot points must be objects")
        _finite_number(point.get("effective_spacing"), "effective grid spacing")
        _finite_number(point.get("anchor_radius"), "anchor radius")
        available = point.get("comparison_available")
        if not isinstance(available, bool):
            raise ValueError("plot comparison availability must be boolean")
        status = point.get("status")
        if available and status != "COMPARISON_AVAILABLE":
            raise ValueError("available plot point has an inconsistent status")
        if not available and status not in {
            "COMPARISON_WITHHELD",
            "NUMERICAL_PREFLIGHT_FAILURE",
            "CASE_PREFLIGHT_REJECTED",
        }:
            raise ValueError("unavailable plot point has an unknown status")
        if available:
            _finite_number(point.get("excess"), "pair-minus-isolated excess")
        elif point.get("excess") is not None:
            raise ValueError("unavailable plot points must have null excess")
    for group in series:
        if not isinstance(group, dict) or not isinstance(group.get("points"), list):
            raise ValueError("plot series groups are malformed")
        for point in group["points"]:
            if point not in points:
                raise ValueError("plot series point is not in the validated point set")
    expected = data.get("plot_data_sha256")
    payload = {key: value for key, value in data.items() if key != "plot_data_sha256"}
    if not isinstance(expected, str) or expected != _sha256(payload):
        raise ValueError("plot-data checksum mismatch")
    return _canonical_json(data)


def render_constrained_sensitivity_png(
    result: ConstrainedInteractionSensitivityResult | dict[str, object],
    output_path: str | Path,
    *,
    dpi: int = 150,
) -> Path:
    """Render energy, anchor-spread, and case-status panels with Agg only."""
    path = Path(output_path)
    if path.suffix.lower() != ".png":
        raise ValueError("output_path must end in .png")
    dpi_value = int(dpi)
    if isinstance(dpi, bool) or dpi_value != dpi or dpi_value < 50 or dpi_value > 600:
        raise ValueError("dpi must be an integer between 50 and 600")
    plot_data = build_constrained_sensitivity_plot_data(result)
    try:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        from matplotlib.lines import Line2D
    except ImportError as exc:
        raise ConstrainedSensitivityVisualizationUnavailable(
            "Matplotlib is required to render sensitivity plots"
        ) from exc

    figure = Figure(figsize=(10.5, 8.0), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    energy_axis, spread_axis, status_axis = figure.subplots(
        3, 1, gridspec_kw={"height_ratios": (3.0, 1.5, 1.3)}
    )
    colors = ("#2457A7", "#C05A24", "#287A53", "#7A4F9A", "#A17B00")
    for index, group in enumerate(plot_data["series"]):
        color = colors[index % len(colors)]
        available_points = [
            point for point in group["points"] if point["comparison_available"]
        ]
        if available_points:
            energy_axis.plot(
                [point["effective_spacing"] for point in available_points],
                [point["excess"] for point in available_points],
                marker="o",
                linewidth=1.6,
                color=color,
                label=f"anchor radius={group['anchor_radius']:g}",
            )
    energy_axis.axhline(0.0, color="#777777", linewidth=0.8, linestyle="--")
    energy_axis.set_ylabel("Pair − isolated excess\n(dimensionless lattice energy)")
    energy_axis.set_title("Constrained pair-relaxation sensitivity (finite grid)")
    energy_axis.grid(True, alpha=0.25)
    if any(group["points"] for group in plot_data["series"]):
        energy_axis.legend(loc="best", frameon=False)

    summaries = plot_data.get("anchor_sensitivity_by_grid") or []
    spread_points = [
        item for item in summaries
        if item.get("anchor_spread") is not None
    ]
    if spread_points:
        spread_axis.plot(
            [
                math.prod(item["spacing"]) ** (1.0 / 3.0)
                for item in spread_points
            ],
            [item["anchor_spread"] for item in spread_points],
            marker="s",
            color="#555555",
            linewidth=1.4,
        )
    spread_axis.set_ylabel("Anchor-radius\nspread")
    spread_axis.grid(True, alpha=0.25)

    status_color = {
        "COMPARISON_AVAILABLE": "#287A53",
        "COMPARISON_WITHHELD": "#A17B00",
        "NUMERICAL_PREFLIGHT_FAILURE": "#B33434",
        "CASE_PREFLIGHT_REJECTED": "#7A4F9A",
    }
    anchor_order = list(plot_data["series"])
    anchor_to_y = {
        group["anchor_radius"]: index for index, group in enumerate(anchor_order)
    }
    for point in plot_data["status_points"]:
        status = point["status"]
        # Status points use the same effective-spacing coordinate as the curves.
        status_axis.scatter(
            [point["effective_spacing"]],
            [anchor_to_y[point["anchor_radius"]]],
            marker="o" if point["comparison_available"] else "x",
            s=48,
            color=status_color.get(status, "#666666"),
            linewidths=1.5,
        )
    status_axis.set_yticks(range(len(anchor_order)))
    status_axis.set_yticklabels(
        [f"a={group['anchor_radius']:g}" for group in anchor_order]
    )
    status_axis.set_ylabel("Anchor")
    status_axis.set_xlabel(
        "Effective mesh spacing (dimensionless model length) · "
        "× = unavailable/rejected (not zero)"
    )
    status_axis.grid(True, axis="x", alpha=0.25)
    status_handles = [
        Line2D(
            [],
            [],
            color="none",
            marker="o" if status == "COMPARISON_AVAILABLE" else "x",
            markerfacecolor=color,
            markeredgecolor=color,
            markersize=7,
            linestyle="None",
            label=status.replace("_", " ").title(),
        )
        for status, color in status_color.items()
    ]
    status_axis.legend(
        handles=status_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.32),
        ncol=2,
        frameon=False,
        fontsize=8,
    )
    figure.suptitle(
        f"Sweep {str(plot_data['sweep_id'])[:12]} · synthetic finite-grid analysis",
        fontsize=11,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.print_figure(path, format="png", dpi=dpi_value)
    figure.clear()
    return path
