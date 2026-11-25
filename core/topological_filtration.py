"""Topological filtration kernels, BLAS-3 PLV computation, and landscape generators.

Enforces:
- BLAS-3 GEMM/HERK accelerated PLV matrix calculation with zero 3D array allocations.
- Distance-pruned Vietoris-Rips persistence diagram computation via Ripser.
- Accelerated Betti-1 landscape generation via pre-filtering and top-k partial selection.
- Strict structural separation between graph topological cycles (H1) and spatial field defects (Q, Qabs).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass(frozen=True)
class GraphTopologyCycleSummary:
    """Permutation-invariant graph-derived topological cycle features (H1).

    These metrics are computed purely from network connectivity / adjacency graphs.
    They are NOT spatial phase winding charges and require no physical coordinates.
    """
    graph_beta1: int
    persistence_landscape_area: float
    filtration_threshold: float
    sweep_thresholds: List[float]
    sweep_beta1: List[int]
    noise_threshold: float = 1e-4
    method: str = "vietoris_rips_h1_pruned"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_beta1": int(self.graph_beta1),
            "persistence_landscape_area": float(self.persistence_landscape_area),
            "filtration_threshold": float(self.filtration_threshold),
            "sweep_thresholds": [float(x) for x in self.sweep_thresholds],
            "sweep_beta1": [int(x) for x in self.sweep_beta1],
            "noise_threshold": float(self.noise_threshold),
            "method": self.method,
            "topological_type": "graph_cycle_h1",
        }


@dataclass(frozen=True)
class SpatialFieldDefectSummary:
    """Coordinate-dependent spatial defect metrics (Q, Qabs).

    These metrics require explicit Cartesian/sensor grid coordinates and compute
    phase field winding numbers on physical plaquettes.
    """
    charge_q: int
    charge_q_abs: float
    sensor_count: int
    coordinate_frame: str
    grid_shape: Tuple[int, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "charge_q": int(self.charge_q),
            "charge_q_abs": float(self.charge_q_abs),
            "sensor_count": int(self.sensor_count),
            "coordinate_frame": self.coordinate_frame,
            "grid_shape": list(self.grid_shape),
            "topological_type": "spatial_phase_defect",
        }


def fast_plv_matrix(phases: np.ndarray) -> np.ndarray:
    """Compute channel-by-channel Phase Locking Value (PLV) using BLAS Level-3 GEMM.

    Given phase angles theta in [C, S] (channels x samples):
        Z = exp(i * theta) in C^(C x S)
        PLV = (1 / S) * |Z @ Z^H| in R^(C x C)

    Avoids O(C^2 * S) intermediate 3D broadcasting arrays, reducing memory
    allocation to O(C^2 + C*S).

    Args:
        phases: 2D array of phase angles in radians, shape (n_channels, n_samples).

    Returns:
        Square symmetric matrix of shape (n_channels, n_channels) with values in [0, 1].
    """
    arr = np.asarray(phases, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"phases must be 2D (channels, samples), got shape {arr.shape}")
    c, s = arr.shape
    if c == 0 or s == 0:
        return np.zeros((c, c), dtype=np.float64)

    # Complex unit phasor matrix Z = exp(i * phi) in C^(C x S)
    z = np.exp(1j * arr)

    # Level-3 BLAS matrix-matrix multiplication Z @ Z^H
    # Result is C x C Hermitian matrix
    cross = np.matmul(z, z.conj().T)

    plv = np.abs(cross) / float(s)

    # Enforce symmetric numerical properties and diagonal exact unity
    plv = (plv + plv.T) / 2.0
    np.clip(plv, 0.0, 1.0, out=plv)
    np.fill_diagonal(plv, 1.0)
    return plv


def pruned_persistence_diagram(
    connectivity: np.ndarray,
    max_dimension: int = 1,
    min_threshold: float = 0.1,
    distance_cutoff: Optional[float] = None,
) -> np.ndarray:
    """Compute graph Vietoris-Rips persistence diagram with distance threshold pruning.

    Converts similarity/connectivity A in [0, 1] to distance D = 1 - A.
    Uses Ripser with explicit `thresh` pruning to avoid unconstrained simplex explosions.

    Args:
        connectivity: Square symmetric matrix in [0, 1].
        max_dimension: Max homology dimension (default 1 for H1 cycles).
        min_threshold: Minimum connectivity threshold below which edges are pruned.
        distance_cutoff: Optional explicit distance upper bound.

    Returns:
        (N, 2) array of (birth, death) pairs for dimension 1.
    """
    try:
        from ripser import ripser
    except ImportError as exc:
        raise RuntimeError("ripser is required for pruned_persistence_diagram") from exc

    arr = np.asarray(connectivity, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
        raise ValueError("connectivity must be square 2D matrix")

    # Symmetrize and bound
    arr = (arr + arr.T) / 2.0
    np.clip(arr, 0.0, 1.0, out=arr)

    # Distance matrix D = 1 - A
    d = 1.0 - arr
    np.fill_diagonal(d, 0.0)

    # Threshold for Ripser filtration
    thresh = float(distance_cutoff if distance_cutoff is not None else (1.0 - min_threshold))
    thresh = max(0.0, min(1.0, thresh))

    res = ripser(d, distance_matrix=True, maxdim=max_dimension, thresh=thresh)
    dgms = res.get("dgms", [])

    if len(dgms) > 1 and dgms[1].size > 0:
        dgm1 = np.asarray(dgms[1], dtype=np.float64)
        valid = np.isfinite(dgm1[:, 0]) & (dgm1[:, 0] >= 0.0)
        return dgm1[valid]
    return np.empty((0, 2), dtype=np.float64)


def fast_betti_landscape(
    diagram: np.ndarray,
    grid: np.ndarray,
    k: int = 5,
    noise_threshold: float = 1e-4,
) -> np.ndarray:
    """Fast persistence landscape computation with noise pre-filtering and top-k selection.

    Computes the k-th persistence landscape curves:
        lambda_k(t) = k-th largest value of [ max(0, min(t - b_i, d_i - t)) ]_i

    Args:
        diagram: (N, 2) array of (birth, death) pairs.
        grid: 1D array of filtration evaluation points.
        k: Number of landscape layers to return.
        noise_threshold: Minimum lifespan (death - birth) to consider as signal.

    Returns:
        (k, len(grid)) array of landscape curves.
    """
    t_grid = np.asarray(grid, dtype=np.float64)
    if t_grid.ndim != 1:
        raise ValueError("grid must be 1D")
    n_grid = len(t_grid)
    out = np.zeros((k, n_grid), dtype=np.float64)

    if diagram is None or len(diagram) == 0:
        return out

    dgm = np.asarray(diagram, dtype=np.float64)
    if dgm.ndim != 2 or dgm.shape[1] != 2:
        raise ValueError("diagram must have shape (N, 2)")

    births = dgm[:, 0]
    deaths = np.where(np.isfinite(dgm[:, 1]), dgm[:, 1], 1.0)
    lifespans = deaths - births

    # Pre-filter topological noise pairs
    significant = lifespans > noise_threshold
    if not np.any(significant):
        return out

    b_sig = births[significant]
    d_sig = deaths[significant]
    n_features = len(b_sig)

    # Evaluate tent functions at each grid point
    # Lambda_i(t) = max(0, min(t - b_i, d_i - t))
    for j, t in enumerate(t_grid):
        left = t - b_sig
        right = d_sig - t
        tents = np.maximum(0.0, np.minimum(left, right))

        if n_features <= k:
            sorted_vals = np.sort(tents)[::-1]
            out[:n_features, j] = sorted_vals
        else:
            # O(N) partial selection of top-k values using partition
            partitioned = np.partition(tents, -k)[-k:]
            sorted_top_k = np.sort(partitioned)[::-1]
            out[:, j] = sorted_top_k

    return out
