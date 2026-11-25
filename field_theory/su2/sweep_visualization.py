"""Optional headless visualization for nearest-neighbor parameter sweeps."""

from __future__ import annotations

from pathlib import Path

from .parameter_sweep import NearestNeighborSweepResult


class SweepVisualizationUnavailable(RuntimeError):
    """Raised when optional matplotlib plotting support is not installed."""


def plot_nearest_neighbor_sweep(
    result: NearestNeighborSweepResult, destination: str | Path
) -> Path:
    """Write a headless PNG of energy and charge trajectories.

    Matplotlib is imported only when this function is called. The Agg canvas
    is attached directly to a Figure, so the function does not mutate a global
    pyplot backend or require a display server.
    """
    if not isinstance(result, NearestNeighborSweepResult):
        raise ValueError("result must be a NearestNeighborSweepResult")
    try:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
    except ImportError as exc:
        raise SweepVisualizationUnavailable(
            "plotting requires the optional matplotlib dependency"
        ) from exc

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure = Figure(figsize=(10.0, 4.5), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    energy_axis = figure.add_subplot(1, 2, 1)
    charge_axis = figure.add_subplot(1, 2, 2)

    for point in result.points:
        label = (
            f"{point.point_id}: λ={point.parameters.inverse_length_scale:g}, "
            f"E₀={point.parameters.energy_prefactor:g}, "
            f"step={point.parameters.initial_dimensionless_step:g}"
        )
        energy_axis.plot(
            range(len(point.energy_history)),
            point.energy_history,
            marker="o",
            label=label,
        )
        charge_axis.plot(
            range(len(point.topological_charge_history)),
            point.topological_charge_history,
            marker="o",
            label=point.point_id,
        )

    energy_axis.set(
        title="Nearest-neighbor energy trajectory",
        xlabel="accepted iteration",
        ylabel="model energy (unit not assigned)",
    )
    charge_axis.set(
        title="Approximate charge trajectory",
        xlabel="accepted iteration",
        ylabel="approximate charge",
    )
    for axis in (energy_axis, charge_axis):
        axis.grid(True, alpha=0.25)
        axis.legend(fontsize="x-small")
    figure.suptitle(
        "SU(2) relaxation sweep — optimizer iterations, not physical time or validation"
    )
    canvas.print_png(target, metadata={"Software": "NeuroTopology-Sim SU2 sweep plot"})
    return target
