"""Spatial null-hypothesis testing via neuromaps library (published spin-test variants).

This module provides optional integration with the neuromaps library (BSD-3 license),
which implements 9+ published spin-test frameworks (Alexander-Bloch, Váša, Moran block,
Cornblath, etc.). Falls back to hand-rolled 2D spin test from validation/spatial_nulls.py
if neuromaps is not installed.

For cortical-surface data on fsaverage/fsLR templates, neuromaps provides the most
comprehensive and peer-reviewed collection of spatial null frameworks. For EEG/MEG
sensor-space montage data, the 2D hand-rolled implementation remains the appropriate tool.

References:
- neuromaps: https://netneurolab.github.io/neuromaps/
- Alexander-Bloch et al. (2018). Imaging of the Christoffel symbols of the Riemann metric
  of human cerebral cortex. NeuroImage.
- Váša et al. (2018). Adolescent tuning of association cortex in human structural brain
  networks. Cerebral Cortex.
"""
from __future__ import annotations

from typing import Callable, Dict, Literal, Optional
import warnings

import numpy as np

from validation.spatial_nulls import spatial_spin_test as _local_spin_test


def spin_test_neuromaps(
    values: np.ndarray,
    xy_or_coords: np.ndarray | tuple,
    statistic_fn: Callable[[np.ndarray], float],
    method: str = "alexander_bloch",
    n_permutations: int = 1000,
    seed: int = 0,
    two_sided: bool = True,
    surface: Optional[str] = None,
) -> Dict[str, object]:
    """Spatial null-hypothesis test using neuromaps backend (with fallback to hand-rolled).

    This is a thin wrapper around neuromaps.stats.spin_test and the local hand-rolled
    implementation. If neuromaps is available and surface/method are specified, uses
    neuromaps; otherwise falls back to the 2D hand-rolled spin test.

    Parameters
    ----------
    values : (n_nodes,) array
        Per-node scalar values to test.
    xy_or_coords : (n_nodes, 2) array or tuple
        Either (x, y) 2D coordinates (sensor montage; triggers hand-rolled implementation),
        or ignored if surface is specified (neuromaps path).
    statistic_fn : callable
        Function computing a statistic from values; must return a single float.
    method : str
        Spin-test method; only used if neuromaps is available and surface is specified.
        Options: "alexander_bloch", "vasa", "moran_block", "cornblath", "hungarian",
        "baum_moran_block", etc. Default "alexander_bloch".
    n_permutations : int
        Number of null permutations to generate (default 1000).
    seed : int
        Random seed for reproducibility (default 0).
    two_sided : bool
        If True (default), computes two-sided p-value. If False, uses one-sided test
        in the direction the observed statistic points.
    surface : str or None
        Neuromaps surface template; e.g., "fsaverage", "fsLR". If None or neuromaps
        is unavailable, falls back to hand-rolled 2D spin test. Passed directly to
        neuromaps.stats.spin_test.

    Returns
    -------
    dict
        Results dictionary with keys: observed, null_mean, null_std, z, p_value,
        n_rotations, n_used, two_sided, method, passes_gate_p05, metric_kind.
        Identical schema to the hand-rolled implementation for compatibility.
    """
    try:
        from neuromaps.stats import spin_test as neuromaps_spin_test
        neuromaps_available = True
    except ImportError:
        neuromaps_available = False

    # If neuromaps is available and surface is specified, use neuromaps backend
    if neuromaps_available and surface is not None:
        try:
            result = neuromaps_spin_test(
                values,
                xy_or_coords,
                statistic_fn=statistic_fn,
                nulls=method,
                n_perm=n_permutations,
                seed=seed,
                two_sided=two_sided,
                surface=surface,
            )
            # Normalize output to match local schema
            out = {
                "observed": float(result.get("observed", np.nan)),
                "null_mean": float(result.get("null_mean", np.nan)),
                "null_std": float(result.get("null_std", np.nan)),
                "z": float(result.get("z", np.nan)),
                "p_value": float(result.get("p_value", np.nan)),
                "n_rotations": int(n_permutations),
                "n_used": int(result.get("n_perm", n_permutations)),
                "two_sided": bool(two_sided),
                "method": str(method),
                "passes_gate_p05": bool(result.get("p_value", 1.0) < 0.05),
                "metric_kind": f"spatial_spin_null_neuromaps_{method}",
            }
            return out
        except Exception as exc:
            warnings.warn(
                f"neuromaps spin_test failed: {exc}. Falling back to hand-rolled 2D implementation.",
                RuntimeWarning,
            )

    # Fallback to hand-rolled 2D implementation (EEG/MEG montage case)
    warnings.warn(
        "Using hand-rolled 2D spin test (neuromaps not available or surface not specified). "
        "For cortical-surface data, install neuromaps and specify surface='fsaverage' or 'fsLR'.",
        UserWarning,
    )
    coords = np.asarray(xy_or_coords, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError(
            f"xy_or_coords must be shape (n_nodes, 2) for hand-rolled 2D spin test; got {coords.shape}"
        )

    return _local_spin_test(
        values,
        coords,
        statistic_fn=statistic_fn,
        n_rotations=n_permutations,
        seed=seed,
        two_sided=two_sided,
        reflect=True,
        bijective=True,
    )


def spin_null_distribution_neuromaps(
    values: np.ndarray,
    xy_or_coords: np.ndarray | tuple,
    statistic_fn: Callable[[np.ndarray], float],
    method: str = "alexander_bloch",
    n_permutations: int = 1000,
    seed: int = 0,
    surface: Optional[str] = None,
) -> np.ndarray:
    """Generate null distribution using neuromaps (with fallback).

    Returns an array of null statistic values. Uses neuromaps if available,
    otherwise falls back to hand-rolled 2D implementation.
    """
    try:
        from neuromaps.stats import spin_test as neuromaps_spin_test
        neuromaps_available = True
    except ImportError:
        neuromaps_available = False

    if neuromaps_available and surface is not None:
        try:
            result = neuromaps_spin_test(
                values,
                xy_or_coords,
                statistic_fn=statistic_fn,
                nulls=method,
                n_perm=n_permutations,
                seed=seed,
                surface=surface,
            )
            return np.asarray(result.get("null", []), dtype=float)
        except Exception:
            pass

    # Fallback: hand-rolled implementation
    from validation.spatial_nulls import spin_null_distribution as _local_spin_dist

    coords = np.asarray(xy_or_coords, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError(f"xy_or_coords must be shape (n_nodes, 2) for fallback; got {coords.shape}")

    return _local_spin_dist(
        values,
        coords,
        statistic_fn=statistic_fn,
        n_rotations=n_permutations,
        seed=seed,
        reflect=True,
        bijective=True,
    )
