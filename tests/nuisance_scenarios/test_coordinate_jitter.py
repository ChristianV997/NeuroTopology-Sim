"""Tests for electrode coordinate jitter, displacement metrics, and sphere projection."""
from __future__ import annotations

import numpy as np
import pytest

from sim.nuisance_scenarios.factory import generate_synthetic_spherical_coordinates
from sim.nuisance_scenarios.jitter import (
    JitteredCoordinateResult,
    apply_coordinate_jitter,
)


def test_zero_jitter_preserves_coordinates() -> None:
    """Verifies that jitter_std=0.0 returns exact copy and zero displacement."""
    coords = generate_synthetic_spherical_coordinates(n_points=10, radius=100.0)
    res = apply_coordinate_jitter(coords, jitter_std=0.0, units="mm", renormalize_to_sphere=False)

    assert isinstance(res, JitteredCoordinateResult)
    np.testing.assert_array_equal(res.jittered_coordinates, coords)
    assert res.mean_displacement == 0.0
    assert res.max_displacement == 0.0
    assert res.rms_displacement == 0.0
    assert res.units == "mm"
    assert not res.renormalized_to_sphere


def test_unconstrained_cartesian_jitter() -> None:
    """Verifies unconstrained 3D Cartesian jitter allows radial variation."""
    coords = generate_synthetic_spherical_coordinates(n_points=32, radius=100.0)
    res = apply_coordinate_jitter(
        coords,
        jitter_std=5.0,
        units="mm",
        renormalize_to_sphere=False,
        seed=42,
    )

    assert res.mean_displacement > 0.0
    assert res.max_displacement >= res.mean_displacement
    assert res.rms_displacement >= res.mean_displacement

    # Check that radii changed from 100.0
    orig_radii = np.linalg.norm(coords, axis=1)
    jit_radii = np.linalg.norm(res.jittered_coordinates, axis=1)
    np.testing.assert_allclose(orig_radii, 100.0, atol=1e-12)
    assert not np.allclose(jit_radii, 100.0, atol=1e-3)


def test_sphere_renormalization_preserves_radius() -> None:
    """Verifies that renormalize_to_sphere=True projects all coordinates back to exact original radius."""
    coords = generate_synthetic_spherical_coordinates(n_points=32, radius=100.0)
    res = apply_coordinate_jitter(
        coords,
        jitter_std=5.0,
        units="mm",
        renormalize_to_sphere=True,
        seed=42,
    )

    assert res.mean_displacement > 0.0
    assert res.renormalized_to_sphere is True

    # Every jittered coordinate must lie at exactly 100.0 mm from origin
    orig_radii = np.linalg.norm(coords, axis=1)
    jit_radii = np.linalg.norm(res.jittered_coordinates, axis=1)
    np.testing.assert_allclose(jit_radii, orig_radii, atol=1e-12)


def test_displacement_scales_with_jitter_std() -> None:
    """Verifies that mean displacement increases monotonically with jitter_std."""
    coords = generate_synthetic_spherical_coordinates(n_points=64, radius=100.0)
    jit_low = apply_coordinate_jitter(coords, jitter_std=1.0, seed=123)
    jit_med = apply_coordinate_jitter(coords, jitter_std=3.0, seed=123)
    jit_high = apply_coordinate_jitter(coords, jitter_std=6.0, seed=123)

    assert jit_low.mean_displacement < jit_med.mean_displacement < jit_high.mean_displacement


def test_supported_and_unsupported_units() -> None:
    """Verifies that supported units ('mm', 'cm', 'm') pass and unsupported units raise ValueError."""
    coords = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    for u in ("mm", "cm", "m", "MM", " Cm "):
        res = apply_coordinate_jitter(coords, jitter_std=0.5, units=u)
        assert res.units in ("mm", "cm", "m")

    with pytest.raises(ValueError, match="units must be one of"):
        apply_coordinate_jitter(coords, jitter_std=0.5, units="fathoms")


def test_2d_and_3d_coordinates_supported() -> None:
    """Verifies that both 2D and 3D coordinate inputs are supported."""
    coords_2d = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]])
    res_2d = apply_coordinate_jitter(coords_2d, jitter_std=0.2, seed=7)
    assert res_2d.jittered_coordinates.shape == (3, 2)

    coords_3d = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])
    res_3d = apply_coordinate_jitter(coords_3d, jitter_std=0.2, seed=7)
    assert res_3d.jittered_coordinates.shape == (2, 3)


def test_invalid_coordinates_raise_value_error() -> None:
    """Verifies that invalid shapes and non-finite values raise ValueError."""
    with pytest.raises(ValueError, match="shape"):
        apply_coordinate_jitter(np.ones((5, 4)), jitter_std=1.0)

    with pytest.raises(ValueError, match="non-finite"):
        bad_coords = np.array([[1.0, 2.0, np.nan]])
        apply_coordinate_jitter(bad_coords, jitter_std=1.0)

    with pytest.raises(ValueError, match="jitter_std"):
        apply_coordinate_jitter(np.ones((2, 3)), jitter_std=-1.0)
