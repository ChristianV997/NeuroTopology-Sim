"""Headless PITNN visualizations for offline artifact inspection."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


class PITNNVisualizer:
    """Render invariant traces, field heatmaps, and S² projections."""

    def __init__(self, output_dir: str | Path = "artifacts/pitnn/plots"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_topological_trace(self, time_stamps: np.ndarray,
                               topology_trace: list[dict[str, Any]],
                               filename: str = "topological_trace.png") -> str:
        times = np.asarray(time_stamps, dtype=float)
        if times.ndim != 1 or len(times) != len(topology_trace) or len(times) == 0:
            raise ValueError("time_stamps and topology_trace must be non-empty and aligned")
        required = {"winding_number", "topological_charge", "beta1_loops"}
        if any(not required.issubset(snapshot) for snapshot in topology_trace):
            raise ValueError("topology snapshots are missing required invariant keys")
        w = [s["winding_number"] for s in topology_trace]
        q = [s["topological_charge"] for s in topology_trace]
        b1 = [s["beta1_loops"] for s in topology_trace]
        fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
        axes[0].plot(times, w, color="crimson", label="Winding Number (W)")
        axes[1].plot(times, q, color="navy", label="Topological Charge (Q)")
        axes[2].step(times, b1, color="darkgreen", where="mid", label=r"$\beta_1$ Loops")
        for axis in axes:
            axis.grid(True, linestyle="--", alpha=0.5); axis.legend(loc="upper right")
        axes[0].set_ylabel("W"); axes[1].set_ylabel("Q"); axes[2].set_ylabel(r"$\beta_1$"); axes[2].set_xlabel("Time (s)")
        fig.suptitle("PITNN Topological Invariants Evolution", fontweight="bold")
        fig.tight_layout()
        return self._save(fig, filename)

    def plot_spinor_field_heatmap(self, spins_history: np.ndarray,
                                  filename: str = "spinor_field_heatmap.png") -> str:
        spins = self._trajectory(spins_history)
        fig, axis = plt.subplots(figsize=(10, 4.5))
        image = axis.imshow(spins[:, :, 2].T, aspect="auto", origin="lower", cmap="coolwarm", vmin=-1, vmax=1)
        fig.colorbar(image, ax=axis, label=r"Spin $S_z$ Alignment")
        axis.set_xlabel("Time Step"); axis.set_ylabel("Lattice Site Index")
        axis.set_title(r"Spatiotemporal Evolution of $S_z(x,t)", fontweight="bold")
        fig.tight_layout()
        return self._save(fig, filename)

    def plot_s2_phase_space(self, spins: np.ndarray,
                            filename: str = "s2_phase_space.png") -> str:
        values = np.asarray(spins, dtype=float)
        if values.ndim != 2 or values.shape[1] != 3 or not np.all(np.isfinite(values)):
            raise ValueError("spins must have shape (N, 3) and be finite")
        fig = plt.figure(figsize=(7, 7)); axis = fig.add_subplot(111, projection="3d")
        u = np.linspace(0, 2 * np.pi, 30); v = np.linspace(0, np.pi, 20)
        axis.plot_wireframe(np.outer(np.cos(u), np.sin(v)), np.outer(np.sin(u), np.sin(v)),
                            np.outer(np.ones(u.size), np.cos(v)), color="gray", alpha=0.15, linewidth=0.5)
        axis.scatter(values[:, 0], values[:, 1], values[:, 2], c=values[:, 2], cmap="twilight", s=25, edgecolors="k")
        axis.set(xlim=(-1, 1), ylim=(-1, 1), zlim=(-1, 1), xlabel=r"$S_x$", ylabel=r"$S_y$", zlabel=r"$S_z$")
        axis.set_title(r"Spin Lattice Configuration on $S^2$", fontweight="bold")
        fig.tight_layout()
        return self._save(fig, filename)

    def plot_ep_scan(self, gaps: np.ndarray, pump_values: np.ndarray,
                     loss_values: np.ndarray, filename: str = "ep_scan.png") -> str:
        """Render a log-scaled EP spectral-gap map."""
        values, pumps, losses = np.asarray(gaps, float), np.asarray(pump_values, float), np.asarray(loss_values, float)
        if values.shape != (len(pumps), len(losses)) or np.any(values < 0):
            raise ValueError("EP gaps must match pump/loss grid and be non-negative")
        fig, axis = plt.subplots(figsize=(7, 5))
        image = axis.imshow(np.log10(values.T + 1e-300), origin="lower", aspect="auto",
                            extent=(pumps[0], pumps[-1], losses[0], losses[-1]), cmap="magma")
        fig.colorbar(image, ax=axis, label="log10 spectral gap")
        axis.set(xlabel="Pump rate (s^-1)", ylabel="Loss rate (s^-1)", title="Non-Hermitian EP scan")
        fig.tight_layout()
        return self._save(fig, filename)

    @staticmethod
    def _trajectory(spins_history: np.ndarray) -> np.ndarray:
        spins = np.asarray(spins_history, dtype=float)
        if spins.ndim != 3 or spins.shape[-1] != 3 or spins.shape[0] == 0 or not np.all(np.isfinite(spins)):
            raise ValueError("spins_history must have shape (time, spins, 3) and be finite")
        return spins

    def _save(self, figure: Any, filename: str) -> str:
        path = self.output_dir / filename
        figure.savefig(path, dpi=150)
        plt.close(figure)
        return str(path)
