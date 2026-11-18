"""Optional headless plots and plot data for Lorentzian SU(2) results.

Matplotlib is imported only by render functions. Plot labels explicitly mark
dimensionless diagnostics and approximate finite-grid charge; these figures
are not physical measurements or validation of the continuum model.
"""
from __future__ import annotations

import math
from numbers import Real
from pathlib import Path
from typing import Any

import numpy as np

from .lorentzian import LorentzianSkyrmeTrajectory
from .trajectory_sweep import LorentzianSweepPoint, LorentzianSweepResult


class LorentzianVisualizationUnavailable(ImportError):
    """Raised when optional matplotlib support is unavailable."""

def _metadata_real(
    value: object,
    name: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real numeric scalar")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if positive and number <= 0.0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and number < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return number


def _metadata_integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result




def _finite_history(values: object, name: str, length: int) -> tuple[float, ...]:
    try:
        raw = np.asarray(values, dtype=object)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite numeric history") from exc
    if raw.ndim != 1 or any(
        isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
        for value in raw
    ):
        raise ValueError(f"{name} must be a finite numeric history")
    try:
        converted = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite numeric history") from exc
    if len(converted) != length or not np.all(np.isfinite(converted)):
        raise ValueError(f"{name} must be a finite history matching time_history")
    return tuple(float(value) for value in converted)


def _trajectory_histories(
    trajectory: LorentzianSkyrmeTrajectory,
) -> dict[str, tuple[float, ...]]:
    if not isinstance(trajectory, LorentzianSkyrmeTrajectory):
        raise ValueError("trajectory must be a LorentzianSkyrmeTrajectory")
    times = _finite_history(trajectory.time_history, "time_history", len(trajectory.time_history))
    if len(times) < 2 or times[0] != 0.0 or any(
        right <= left for left, right in zip(times, times[1:])
    ):
        raise ValueError("time_history must start at zero and be strictly increasing")
    names = (
        "energy_sigma_history",
        "energy_skyrme_history",
        "kinetic_sigma_history",
        "kinetic_skyrme_history",
        "total_energy_history",
        "dissipated_energy_history",
        "energy_balance_residual_history",
        "approximate_charge_history",
        "time_kinetic_min_eigenvalue_history",
        "time_kinetic_max_condition_history",
    )
    result = {"time": times}
    for name in names:
        result[name.removesuffix("_history")] = _finite_history(
            getattr(trajectory, name), name, len(times)
        )
    return result


def build_lorentzian_trajectory_plot_data(
    trajectory: LorentzianSkyrmeTrajectory,
) -> dict[str, Any]:
    """Build deterministic, Matplotlib-free plot data for one trajectory."""
    data = _trajectory_histories(trajectory)
    dt = _metadata_real(trajectory.dt, "dt", positive=True)
    steps = _metadata_integer(trajectory.steps, "steps", minimum=1)
    damping = _metadata_real(trajectory.damping, "damping", nonnegative=True)
    cfl_indicator = _metadata_real(
        trajectory.linearized_cfl_indicator,
        "linearized_cfl_indicator",
        nonnegative=True,
    )
    data.update(
        {
            "schema_version": "su2.lorentzian_trajectory_plot_data.v1",
            "model": trajectory.model,
            "dt": dt,
            "steps": steps,
            "final_time": data["time"][-1],
            "damping": damping,
            "linearized_cfl_indicator": cfl_indicator,
            "hyperbolicity_status": trajectory.hyperbolicity_status,
            "claim_scope": "dimensionless_finite_grid_diagnostics_only",
            "charge_label": "approximate finite-grid topological charge",
            "energy_unit_status": "not_assessed",
        }
    )
    return data


def _matplotlib() -> tuple[Any, Any]:
    try:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
    except ImportError as exc:
        raise LorentzianVisualizationUnavailable(
            "plot rendering requires the optional matplotlib dependency"
        ) from exc
    return FigureCanvasAgg, Figure


def plot_lorentzian_trajectory(
    trajectory: LorentzianSkyrmeTrajectory, destination: str | Path
) -> Path:
    """Write a headless diagnostic dashboard for one saved trajectory."""
    data = build_lorentzian_trajectory_plot_data(trajectory)
    FigureCanvasAgg, Figure = _matplotlib()
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure = Figure(figsize=(11.0, 7.5), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    energy_axis = figure.add_subplot(2, 2, 1)
    work_axis = figure.add_subplot(2, 2, 2)
    charge_axis = figure.add_subplot(2, 2, 3)
    metric_axis = figure.add_subplot(2, 2, 4)
    time = data["time"]

    for key, label in (
        ("energy_sigma", "spatial sigma"),
        ("energy_skyrme", "spatial Skyrme"),
        ("kinetic_sigma", "sigma kinetic"),
        ("kinetic_skyrme", "Skyrme kinetic"),
        ("total_energy", "total"),
    ):
        energy_axis.plot(time, data[key], label=label)
    energy_axis.set(
        title="Finite-grid Hamiltonian terms",
        xlabel="dimensionless time",
        ylabel="model energy (unit not assigned)",
    )
    energy_axis.legend(fontsize="x-small")
    energy_axis.grid(True, alpha=0.25)

    work_axis.plot(time, data["dissipated_energy"], label="accumulated damping work")
    work_axis.plot(time, data["energy_balance_residual"], label="energy-balance residual")
    work_axis.set(
        title="Damping and numerical balance",
        xlabel="dimensionless time",
        ylabel="model energy (unit not assigned)",
    )
    work_axis.legend(fontsize="x-small")
    work_axis.grid(True, alpha=0.25)

    charge_axis.plot(time, data["approximate_charge"], marker="o", markersize=2)
    charge_axis.set(
        title="Approximate finite-grid charge",
        xlabel="dimensionless time",
        ylabel="approximate charge (not a conservation certificate)",
    )
    charge_axis.grid(True, alpha=0.25)

    metric_axis.plot(
        time,
        data["time_kinetic_min_eigenvalue"],
        color="tab:blue",
        label="minimum kinetic eigenvalue",
    )
    condition_axis = metric_axis.twinx()
    condition_axis.plot(
        time,
        data["time_kinetic_max_condition"],
        color="tab:orange",
        linestyle="--",
        label="maximum kinetic condition number",
    )
    metric_axis.set(
        title="Local kinetic-metric diagnostics",
        xlabel="dimensionless time",
        ylabel="minimum eigenvalue",
    )
    condition_axis.set_ylabel("maximum condition number")
    metric_axis.grid(True, alpha=0.25)
    lines = metric_axis.get_lines() + condition_axis.get_lines()
    metric_axis.legend(lines, [line.get_label() for line in lines], fontsize="x-small")
    figure.suptitle(
        "Lorentzian SU(2) finite-grid run — exploratory; nonlinear hyperbolicity not certified",
        fontsize=10,
    )
    canvas.print_png(
        target, metadata={"Software": "NeuroTopology-Sim Lorentzian trajectory plot"}
    )
    return target


def plot_lorentzian_field_slices(
    trajectory: LorentzianSkyrmeTrajectory,
    destination: str | Path,
    *,
    component: int = 0,
    slice_axis: int = 2,
    slice_index: int | None = None,
    max_frames: int = 8,
) -> Path:
    """Render a bounded time sequence of 2D slices of one quaternion component.

    Components are the dimensionless real fields (n0, n1, n2, n3). This
    visualization does not depict energy density, probability, or brain data.
    """
    if not isinstance(trajectory, LorentzianSkyrmeTrajectory):
        raise ValueError("trajectory must be a LorentzianSkyrmeTrajectory")
    if isinstance(component, bool) or not isinstance(component, (int, np.integer)):
        raise ValueError("component must be an integer from 0 through 3")
    if int(component) not in range(4):
        raise ValueError("component must be an integer from 0 through 3")
    if isinstance(slice_axis, bool) or not isinstance(slice_axis, (int, np.integer)):
        raise ValueError("slice_axis must be an integer from 0 through 2")
    if int(slice_axis) not in range(3):
        raise ValueError("slice_axis must be an integer from 0 through 2")
    if isinstance(max_frames, bool) or not isinstance(max_frames, (int, np.integer)):
        raise ValueError("max_frames must be an integer")
    if int(max_frames) < 1 or int(max_frames) > 16:
        raise ValueError("max_frames must be between 1 and 16")
    fields = trajectory.fields
    times = trajectory.time_history
    if len(fields) != len(times) or not fields:
        raise ValueError("trajectory fields must match its nonempty time_history")
    shape = fields[0].components.shape[:3]
    if any(field.components.shape[:3] != shape for field in fields):
        raise ValueError("all trajectory fields must use the same grid")
    axis = int(slice_axis)
    if slice_index is None:
        index = shape[axis] // 2
    elif (
        isinstance(slice_index, bool)
        or not isinstance(slice_index, (int, np.integer))
        or int(slice_index) < 0
        or int(slice_index) >= shape[axis]
    ):
        raise ValueError("slice_index must be within the selected grid axis")
    else:
        index = int(slice_index)

    count = min(int(max_frames), len(fields))
    selected = np.unique(np.rint(np.linspace(0, len(fields) - 1, count)).astype(int))
    images = []
    for frame in selected:
        values = np.asarray(fields[int(frame)].components, dtype=np.float64)
        if not np.all(np.isfinite(values)):
            raise ValueError("trajectory fields must be finite")
        images.append(np.take(values[..., int(component)], index, axis=axis))
    FigureCanvasAgg, Figure = _matplotlib()
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    columns = min(4, len(images))
    rows = math.ceil(len(images) / columns)
    figure = Figure(
        figsize=(3.2 * columns, 2.8 * rows),
        constrained_layout=True,
    )
    canvas = FigureCanvasAgg(figure)
    axes = figure.subplots(rows, columns, squeeze=False)
    image_handle = None
    for axis_index, axis_obj in enumerate(axes.flat):
        if axis_index >= len(images):
            axis_obj.set_visible(False)
            continue
        frame = int(selected[axis_index])
        image_handle = axis_obj.imshow(
            images[axis_index],
            origin="lower",
            vmin=-1.0,
            vmax=1.0,
            cmap="coolwarm",
            interpolation="nearest",
        )
        axis_obj.set_title(f"t={float(times[frame]):.4g}")
        axis_obj.set_xlabel("grid index")
        axis_obj.set_ylabel("grid index")
    if image_handle is not None:
        figure.colorbar(
            image_handle, ax=list(axes.flat), shrink=0.85, label="field component"
        )
    figure.suptitle(
        f"Dimensionless SU(2) component n{int(component)} slice; not a physical density",
        fontsize=10,
    )
    canvas.print_png(
        target, metadata={"Software": "NeuroTopology-Sim Lorentzian field slices"}
    )
    return target


def _point_key(point: LorentzianSweepPoint) -> tuple[float, float, float, float]:
    return (
        _metadata_real(point.f_pi, "f_pi", positive=True),
        _metadata_real(point.e, "e", positive=True),
        _metadata_real(point.damping, "damping", nonnegative=True),
        _metadata_real(point.dt, "dt", positive=True),
    )


def build_lorentzian_sweep_plot_data(
    result: LorentzianSweepResult, *, x_parameter: str
) -> dict[str, Any]:
    """Build sweep time-series plot data when only one parameter axis varies."""
    if not isinstance(result, LorentzianSweepResult):
        raise ValueError("result must be a LorentzianSweepResult")
    allowed = {"f_pi", "e", "damping", "dt"}
    if x_parameter not in allowed:
        raise ValueError("x_parameter must be one of f_pi, e, damping, or dt")
    spec = result.spec
    axes = {
        "f_pi": tuple(spec.f_pi_values),
        "e": tuple(spec.e_values),
        "damping": tuple(spec.damping_values),
        "dt": tuple(spec.dt_values),
    }
    if any(
        len(values) != 1 for name, values in axes.items() if name != x_parameter
    ):
        raise ValueError(
            "plot one varying parameter at a time; other axes must be singletons"
        )
    expected = {
        (float(f_pi), float(e), float(damping), float(dt))
        for f_pi, e, damping, dt in spec.point_parameters()
    }
    points_by_key: dict[
        tuple[float, float, float, float], LorentzianSweepPoint
    ] = {}
    for point in result.points:
        if not isinstance(point, LorentzianSweepPoint):
            raise ValueError("result points must be LorentzianSweepPoint values")
        key = _point_key(point)
        if key not in expected or key in points_by_key:
            raise ValueError("sweep points do not uniquely match the declared axes")
        points_by_key[key] = point
    if set(points_by_key) != expected:
        raise ValueError("sweep points do not cover the declared axes")

    axis_values = sorted(axes[x_parameter])
    curves = []
    for value in axis_values:
        key_values = {
            name: values[0] if name != x_parameter else value
            for name, values in axes.items()
        }
        key = (
            float(key_values["f_pi"]),
            float(key_values["e"]),
            float(key_values["damping"]),
            float(key_values["dt"]),
        )
        point = points_by_key[key]
        times = _finite_history(
            point.time_history, "time_history", len(point.time_history)
        )
        if len(times) < 2 or any(
            right <= left for left, right in zip(times, times[1:])
        ):
            raise ValueError("point time histories must be strictly increasing")
        total = _finite_history(
            point.total_energy_history, "total_energy_history", len(times)
        )
        charge = _finite_history(
            point.approximate_charge_history,
            "approximate_charge_history",
            len(times),
        )
        residual = _finite_history(
            point.energy_balance_residual_history,
            "energy_balance_residual_history",
            len(times),
        )
        curves.append(
            {
                "point_id": point.point_id,
                "x_value": value,
                "label": f"{x_parameter}={value:g}",
                "time": list(times),
                "total_energy": list(total),
                "approximate_charge": list(charge),
                "energy_balance_residual": list(residual),
            }
        )
    return {
        "schema_version": "su2.lorentzian_sweep_plot_data.v1",
        "x_parameter": x_parameter,
        "x_values": axis_values,
        "curves": curves,
        "claim_scope": "dimensionless_finite_grid_diagnostics_only",
        "charge_label": "approximate finite-grid topological charge",
        "energy_unit_status": "not_assessed",
    }


def plot_lorentzian_sweep(
    result: LorentzianSweepResult,
    destination: str | Path,
    *,
    x_parameter: str,
) -> Path:
    """Write headless energy and approximate-charge curves for one sweep axis."""
    data = build_lorentzian_sweep_plot_data(result, x_parameter=x_parameter)
    FigureCanvasAgg, Figure = _matplotlib()
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure = Figure(figsize=(10.0, 4.5), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    energy_axis = figure.add_subplot(1, 2, 1)
    charge_axis = figure.add_subplot(1, 2, 2)
    for curve in data["curves"]:
        energy_axis.plot(curve["time"], curve["total_energy"], label=curve["label"])
        charge_axis.plot(
            curve["time"],
            curve["approximate_charge"],
            label=curve["label"],
        )
    energy_axis.set(
        title="Total finite-grid model energy",
        xlabel="dimensionless time",
        ylabel="model energy (unit not assigned)",
    )
    charge_axis.set(
        title="Approximate finite-grid charge",
        xlabel="dimensionless time",
        ylabel="approximate charge (not a conservation certificate)",
    )
    for axis in (energy_axis, charge_axis):
        axis.grid(True, alpha=0.25)
        axis.legend(fontsize="x-small")
    figure.suptitle(
        f"Lorentzian SU(2) sweep over {x_parameter} — exploratory, not physical validation",
        fontsize=10,
    )
    canvas.print_png(
        target, metadata={"Software": "NeuroTopology-Sim Lorentzian sweep plot"}
    )
    return target
