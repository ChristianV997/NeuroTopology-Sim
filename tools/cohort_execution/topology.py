"""Descriptive persistent homology and spatial topological phase computation.

Strictly separates graph persistent homology (H0, H1, persistence landscapes)
from geometric spatial phase charge (Q_spatial).
"""
from __future__ import annotations

import math
from typing import Any, Sequence
import numpy as np
from scipy.signal import hilbert

from topo_monitor.graph_persistence import analyze_adjacency, betti_curve
from topo_monitor.spatial_phase import sensor_spatial_charge
from .models import WindowMetrics


def compute_window_topology(
    chunk: np.ndarray,
    *,
    montage_coordinates: np.ndarray | None = None,
    filtration_thresholds: Sequence[float] | None = None,
    plv_threshold: float = 0.5,
    landscape_layers: int = 3,
) -> WindowMetrics:
    """Computes descriptive persistent homology (H0, H1) and spatial phase charge.

    Args:
        chunk: 2D array of shape `(channels, samples)`.
        montage_coordinates: Optional 3D sensor coordinates of shape `(channels, 3)`.
        filtration_thresholds: Optional thresholds in [0, 1] for filtration sweep.
        plv_threshold: Single threshold parameter for PLV persistence slice.
        landscape_layers: Number of persistence landscape layers to integrate.

    Returns:
        WindowMetrics with finite Betti-0, Betti-1, persistence landscape area,
        interval counts, and spatial phase charge (only if montage coordinates exist).
    """
    channels, samples = chunk.shape
    if channels < 2 or samples < 8 or not np.all(np.isfinite(chunk)):
        return WindowMetrics(
            channels=channels,
            samples=samples,
            is_finite=False,
            h0_intervals_count=0,
            h1_intervals_count=0,
            beta0_max=channels,
            beta0_mean=float(channels),
            beta1_max=0,
            filtration_beta1_max=0,
            mean_beta1=0.0,
            integrated_beta1_landscape_area=0.0,
            spatial_phase_charge=None,
            spatial_charge_available=False,
        )

    # 1. Analytic phase via Hilbert transform
    analytic = hilbert(chunk, axis=1)
    phase = np.angle(analytic)

    # 2. Phase Locking Value (PLV) adjacency matrix
    diff = phase[:, None, :] - phase[None, :, :]
    plv = np.abs(np.mean(np.exp(1j * diff), axis=2))
    np.fill_diagonal(plv, 0.0)
    plv = np.clip(plv, 0.0, 1.0)
    plv = (plv + plv.T) / 2.0

    # 3. Persistent Homology via ripser
    try:
        from ripser import ripser
    except ImportError as exc:
        raise RuntimeError("ripser is required for persistent homology") from exc

    d = 1.0 - plv
    np.fill_diagonal(d, 0.0)

    try:
        dgm_data = ripser(d, distance_matrix=True, maxdim=1)
        dgms = dgm_data["dgms"]
        dgm0 = np.asarray(dgms[0], dtype=float) if len(dgms) > 0 else np.empty((0, 2))
        dgm1 = np.asarray(dgms[1], dtype=float) if len(dgms) > 1 else np.empty((0, 2))
    except Exception as exc:
        raise RuntimeError(f"Error during ripser persistent homology computation: {exc}") from exc

    # H0 intervals and Betti-0 counts
    h0_count = len(dgm0)
    sweep_t = np.linspace(0.1, 0.9, 9) if filtration_thresholds is None else np.asarray(filtration_thresholds, float)
    cutoff_d = 1.0 - sweep_t  # Distance cutoffs corresponding to PLV thresholds

    # In H0, birth is always 0.0; count surviving intervals where death > distance_cutoff
    if dgm0.size > 0:
        death0 = np.where(np.isfinite(dgm0[:, 1]), dgm0[:, 1], np.inf)
        b0_curve = np.asarray([np.count_nonzero(death0 > c) for c in cutoff_d], int)
        beta0_max = int(np.max(b0_curve)) if b0_curve.size else channels
        beta0_mean = float(np.mean(b0_curve)) if b0_curve.size else float(channels)
    else:
        beta0_max = channels
        beta0_mean = float(channels)

    # H1 persistent homology via analyze_adjacency
    try:
        result = analyze_adjacency(
            plv,
            threshold=plv_threshold,
            n_layers=landscape_layers,
        )
        sweep_b1 = result.sweep_beta1 if result.sweep_beta1 is not None else np.empty(0)
        filtration_beta1_max = int(np.max(sweep_b1)) if sweep_b1.size else 0
        beta1_max = int(np.max(result.beta_curve)) if result.beta_curve.size else 0
        mean_beta1 = float(np.mean(sweep_b1)) if sweep_b1.size else 0.0
        area = float(result.integrated_landscape_area) if math.isfinite(result.integrated_landscape_area) else 0.0
    except Exception as exc:
        raise RuntimeError(f"Error during H1 graph persistence analysis: {exc}") from exc

    h1_count = len(dgm1)

    # 4. Geometric spatial phase charge
    # STRICT GUARD: spatial phase charge only when valid montage coordinates exist;
    # explicit null when spatial coordinates are missing!
    spatial_phase_charge: float | None = None
    spatial_charge_available: bool = False

    if montage_coordinates is not None:
        try:
            coords = np.asarray(montage_coordinates, float)
            # Must match number of channels and be 3D
            if coords.ndim == 2 and coords.shape == (channels, 3):
                q = sensor_spatial_charge(phase[:, -1], coords)
                if math.isfinite(q):
                    spatial_phase_charge = float(q)
                    spatial_charge_available = True
        except Exception:
            spatial_phase_charge = None
            spatial_charge_available = False

    return WindowMetrics(
        channels=channels,
        samples=samples,
        is_finite=True,
        h0_intervals_count=h0_count,
        h1_intervals_count=h1_count,
        beta0_max=beta0_max,
        beta0_mean=beta0_mean,
        beta1_max=beta1_max,
        filtration_beta1_max=filtration_beta1_max,
        mean_beta1=mean_beta1,
        integrated_beta1_landscape_area=area,
        spatial_phase_charge=spatial_phase_charge,
        spatial_charge_available=spatial_charge_available,
    )
