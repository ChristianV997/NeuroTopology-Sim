"""Descriptive persistent homology and spatial topological phase computation.

Graph persistent homology (beta_1, landscape area) and geometric spatial charge
(Q_spatial) are intentionally separated and computed via distinct mathematical pathways.
"""
from __future__ import annotations

import math
from typing import Any
import numpy as np
from scipy.signal import hilbert

from topo_monitor.graph_persistence import analyze_adjacency
from topo_monitor.spatial_phase import sensor_spatial_charge, spatial_winding_charge
from .models import WindowMetrics


def compute_window_topology(
    chunk: np.ndarray,
    *,
    montage_coordinates: np.ndarray | None = None,
    plv_threshold: float = 0.5,
    landscape_layers: int = 3,
) -> WindowMetrics:
    """Computes descriptive persistent-homology and spatial charge metrics for a window.

    Args:
        chunk: 2D array of shape `(channels, samples)`.
        montage_coordinates: Optional 3D sensor coordinates of shape `(channels, 3)`.
        plv_threshold: Threshold parameter for PLV persistence sweep.
        landscape_layers: Number of persistence landscape layers to integrate.

    Returns:
        WindowMetrics containing finite graph Betti-1, persistence landscape area,
        and geometric spatial charge (if coordinates available).
    """
    channels, samples = chunk.shape
    if channels < 2 or samples < 8:
        return WindowMetrics(
            channels=channels,
            samples=samples,
            is_finite=False,
            beta1_max=0,
            filtration_beta1_max=0,
            mean_beta1=0.0,
            integrated_landscape_area=0.0,
            spatial_charge=None,
            spatial_charge_available=False,
        )

    # Check finite status of input recording window
    if not np.all(np.isfinite(chunk)):
        return WindowMetrics(
            channels=channels,
            samples=samples,
            is_finite=False,
            beta1_max=0,
            filtration_beta1_max=0,
            mean_beta1=0.0,
            integrated_landscape_area=0.0,
            spatial_charge=None,
            spatial_charge_available=False,
        )

    # 1. Analytic phase via Hilbert transform
    analytic = hilbert(chunk, axis=1)
    phase = np.angle(analytic)

    # 2. Phase Locking Value (PLV) adjacency matrix
    # PLV_ij = |1/T sum_t exp(i(theta_i(t) - theta_j(t)))|
    diff = phase[:, None, :] - phase[None, :, :]
    plv = np.abs(np.mean(np.exp(1j * diff), axis=2))
    np.fill_diagonal(plv, 0.0)
    plv = np.clip(plv, 0.0, 1.0)

    # 3. Graph persistent homology (H1 cycles over PLV distance filtration)
    try:
        result = analyze_adjacency(
            plv,
            threshold=plv_threshold,
            n_layers=landscape_layers,
        )
        sweep_b = result.sweep_beta1 if result.sweep_beta1 is not None else np.empty(0)
        filtration_beta1_max = int(np.max(sweep_b)) if sweep_b.size else 0
        beta1_max = int(np.max(result.beta_curve)) if result.beta_curve.size else 0
        mean_beta1 = float(np.mean(sweep_b)) if sweep_b.size else 0.0
        area = float(result.integrated_landscape_area) if math.isfinite(result.integrated_landscape_area) else 0.0
    except Exception as exc:
        raise RuntimeError(f"Error during graph persistence computation: {exc}") from exc

    # 4. Geometric spatial topological charge (strictly separated from graph beta_1)
    spatial_charge: float | None = None
    spatial_charge_available: bool = False

    if montage_coordinates is not None:
        try:
            q = sensor_spatial_charge(phase[:, -1], montage_coordinates)
            if math.isfinite(q):
                spatial_charge = float(q)
                spatial_charge_available = True
        except Exception:
            spatial_charge = None
            spatial_charge_available = False
    else:
        side = int(round(math.isqrt(channels)))
        if side * side == channels and side >= 2:
            try:
                grid_phase = phase[:, -1].reshape(side, side)
                coords = np.stack(np.mgrid[:side, :side], axis=-1).astype(float)
                q = spatial_winding_charge(grid_phase, coords)
                if math.isfinite(q):
                    spatial_charge = float(q)
                    spatial_charge_available = True
            except Exception:
                spatial_charge = None
                spatial_charge_available = False

    return WindowMetrics(
        channels=channels,
        samples=samples,
        is_finite=True,
        beta1_max=beta1_max,
        filtration_beta1_max=filtration_beta1_max,
        mean_beta1=mean_beta1,
        integrated_landscape_area=area,
        spatial_charge=spatial_charge,
        spatial_charge_available=spatial_charge_available,
    )
