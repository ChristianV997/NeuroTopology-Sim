"""Electrode coordinate jittering and displacement diagnostics in pure NumPy.

Two distinct displacement modes:
1. Unconstrained Additive 3D Jitter (renormalize_to_sphere=False):
   Adds independent 3D Gaussian displacement Delta R ~ N(0, sigma^2 * I) to each electrode.
   Electrodes displace freely in Cartesian space.
2. Sphere-Projected Jitter (renormalize_to_sphere=True):
   After additive jitter, radial projection preserves original electrode radius ||R_c||_2:
       R_hat_c = (R_c + Delta R_c) / ||R_c + Delta R_c||_2 * ||R_c||_2
   This constrains jittered electrodes to lie on the spherical scalp shell.
"""
from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from typing import Optional, Union

import numpy as np

from .config import SUPPORTED_COORDINATE_UNITS


@dataclass(frozen=True)
class JitteredCoordinateResult:
    """Container for jittered coordinates and realized displacement diagnostics."""

    jittered_coordinates: np.ndarray
    original_coordinates: np.ndarray
    mean_displacement: float
    max_displacement: float
    rms_displacement: float
    units: str
    renormalized_to_sphere: bool

    @property
    def jittered_coords(self) -> np.ndarray:
        """Alias for jittered_coordinates."""
        return self.jittered_coordinates


def apply_coordinate_jitter(
    coordinates: Optional[np.ndarray] = None,
    jitter_std: float = 0.0,
    units: str = "mm",
    renormalize_to_sphere: bool = False,
    seed: Optional[Union[int, np.random.Generator, np.random.SeedSequence]] = None,
    *,
    coords: Optional[np.ndarray] = None,
    rng: Optional[Union[int, np.random.Generator, np.random.SeedSequence]] = None,
) -> JitteredCoordinateResult:
    """Apply controlled coordinate jitter to sensor coordinates with explicit units and seed.

    Parameters:
        coordinates: Array of shape (n_channels, 3) or (n_channels, 2).
        jitter_std: Standard deviation of Gaussian perturbation in declared units.
        units: Explicit unit string ('mm', 'cm', or 'm').
        renormalize_to_sphere: If True, explicitly projects displaced coordinates back to the original radius.
                               If False (default), allows unconstrained 3D Cartesian displacement.
        seed: Master seed for reproducible jitter generation.
        coords: Optional keyword alias for coordinates.
        rng: Optional keyword alias for seed.

    Returns:
        JitteredCoordinateResult containing perturbed coordinates and realized displacement metrics.
    """
    if coords is not None and coordinates is not None:
        canonical_coords = np.asarray(coordinates, dtype=np.float64)
        alias_coords = np.asarray(coords, dtype=np.float64)
        if not np.array_equal(canonical_coords, alias_coords, equal_nan=True):
            raise ValueError("conflict: 'coordinates' and alias 'coords' disagree")
        raw_coords = canonical_coords
    else:
        raw_coords = coords if coords is not None else coordinates
    if raw_coords is None:
        raise ValueError("Coordinates array must be provided via 'coordinates' or 'coords'")

    arr = np.asarray(raw_coords, dtype=np.float64)

    if arr.ndim != 2 or arr.shape[1] not in (2, 3):
        raise ValueError(
            f"coordinates must have shape (n_channels, 2) or (n_channels, 3), got {arr.shape}"
        )
    if not np.all(np.isfinite(arr)):
        raise ValueError("coordinates contain non-finite values (NaN or Inf)")
    if isinstance(jitter_std, bool) or not isinstance(jitter_std, numbers.Real):
        raise ValueError(f"jitter_std must be a non-negative finite real number, got {jitter_std!r}")
    try:
        jitter_std = float(jitter_std)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(
            f"jitter_std must be representable as a finite float, got {jitter_std!r}"
        ) from exc
    if not math.isfinite(jitter_std) or jitter_std < 0.0:
        raise ValueError(f"jitter_std must be a non-negative finite float, got {jitter_std}")

    if not isinstance(units, str):
        raise ValueError(f"units must be a string, got {units!r}")
    unit_str = units.strip().lower()
    if unit_str not in SUPPORTED_COORDINATE_UNITS:
        raise ValueError(
            f"units must be one of {sorted(SUPPORTED_COORDINATE_UNITS)}, got '{units}'"
        )

    n_channels, n_dims = arr.shape

    if not isinstance(renormalize_to_sphere, bool):
        raise ValueError(
            "renormalize_to_sphere must be a bool, "
            f"got {renormalize_to_sphere!r}"
        )
    if seed is not None and rng is not None:
        raise ValueError("provide only one of seed or rng")
    effective_seed = rng if rng is not None else seed
    if effective_seed is not None:
        if isinstance(effective_seed, bool):
            raise ValueError("seed/rng must not be a bool")
        if not isinstance(effective_seed, (numbers.Integral, np.random.Generator, np.random.SeedSequence)):
            raise ValueError(f"seed/rng must be a non-negative integer, Generator, or SeedSequence, got {effective_seed!r}")
        if isinstance(effective_seed, numbers.Integral) and int(effective_seed) < 0:
            raise ValueError(f"seed/rng must be a non-negative integer, got {effective_seed}")

    if renormalize_to_sphere:
        for ch in range(n_channels):
            with np.errstate(over="ignore", invalid="ignore"):
                r_orig_check = float(np.linalg.norm(arr[ch]))
            if not math.isfinite(r_orig_check) or r_orig_check <= 1e-12:
                raise ValueError(
                    f"renormalize_to_sphere requires strictly positive finite electrode radius from origin; "
                    f"channel {ch} has radius {r_orig_check}"
                )

    if jitter_std == 0.0:
        return JitteredCoordinateResult(
            jittered_coordinates=arr.copy(),
            original_coordinates=arr.copy(),
            mean_displacement=0.0,
            max_displacement=0.0,
            rms_displacement=0.0,
            units=unit_str,
            renormalized_to_sphere=renormalize_to_sphere,
        )

    gen = np.random.default_rng(effective_seed)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        delta = gen.normal(loc=0.0, scale=jitter_std, size=(n_channels, n_dims))
        jittered = arr + delta
    if not np.all(np.isfinite(jittered)):
        raise ValueError("jitter_std produces non-finite jittered coordinates")

    if renormalize_to_sphere:
        # Radial projection to preserve the original distance from origin per electrode
        for ch in range(n_channels):
            with np.errstate(over="ignore", invalid="ignore"):
                r_orig = float(np.linalg.norm(arr[ch]))
                r_jit = float(np.linalg.norm(jittered[ch]))
            if not (math.isfinite(r_orig) and math.isfinite(r_jit)):
                raise ValueError("coordinate values or jitter_std produce non-finite sphere radii")
            if r_jit <= 1e-12:
                raise ValueError(f"jittered coordinate for channel {ch} collapsed to origin (radius {r_jit})")
            jittered[ch] = (jittered[ch] / r_jit) * r_orig

    # Compute Euclidean displacement per channel
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        displacements = np.linalg.norm(jittered - arr, axis=1)
    mean_disp = float(np.mean(displacements))
    max_disp = float(np.max(displacements))
    rms_disp = float(np.sqrt(np.mean(displacements ** 2)))
    if not all(math.isfinite(value) for value in (mean_disp, max_disp, rms_disp)):
        raise ValueError("jitter_std produces non-finite displacement diagnostics")

    return JitteredCoordinateResult(
        jittered_coordinates=jittered,
        original_coordinates=arr.copy(),
        mean_displacement=mean_disp,
        max_displacement=max_disp,
        rms_displacement=rms_disp,
        units=unit_str,
        renormalized_to_sphere=renormalize_to_sphere,
    )
