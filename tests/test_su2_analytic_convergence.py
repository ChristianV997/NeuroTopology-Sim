"""Analytic continuum-limit checks for the SU(2) nearest-neighbor objective.

All inputs are generated in memory. These tests verify discretization contracts;
they do not certify a physical Skyrmion or relaxation dynamics.
"""

import math

import numpy as np
import pytest

from field_theory.su2 import SU2GridField, hedgehog
from field_theory.su2.nearest_neighbor import compute_nearest_neighbor_diagnostics


def _periodic_two_angle_map(size: int) -> tuple[SU2GridField, float]:
    step = 2.0 * math.pi / size
    coordinate = np.arange(size, dtype=np.float64) * step
    x, y, _ = np.meshgrid(coordinate, coordinate, coordinate, indexing="ij")
    a, b = x, y
    values = np.stack(
        (
            np.cos(a) * np.cos(b),
            np.sin(a) * np.cos(b),
            np.cos(a) * np.sin(b),
            np.sin(a) * np.sin(b),
        ),
        axis=-1,
    )
    return (
        SU2GridField(values, spacing=(step, step, step), boundary="periodic"),
        step,
    )


def test_periodic_two_angle_map_matches_lattice_normalization_and_continuum_limit() -> None:
    """Check sigma/quartic coefficients against exact lattice and continuum values."""
    sigma_errors = []
    quartic_errors = []
    continuum_volume = (2.0 * math.pi) ** 3
    sigma_continuum = 2.0 * math.pi**3
    quartic_continuum = 4.0 * math.pi**3

    for size in (8, 16, 32, 64):
        field, step = _periodic_two_angle_map(size)
        result = compute_nearest_neighbor_diagnostics(field)

        chord_norm_squared = 4.0 * math.sin(step / 2.0) ** 2 / step**2
        cross_chord_dot = (1.0 - math.cos(step)) ** 2 / step**2
        sigma_lattice = continuum_volume * chord_norm_squared / 4.0
        quartic_lattice = continuum_volume * (
            chord_norm_squared**2 - cross_chord_dot**2
        ) / 2.0

        assert result.energy_sigma == pytest.approx(sigma_lattice, rel=2e-12, abs=2e-12)
        assert result.energy_skyrme == pytest.approx(quartic_lattice, rel=2e-12, abs=2e-12)
        assert result.topological_charge == pytest.approx(0.0, abs=1e-12)
        sigma_errors.append(abs(result.energy_sigma / sigma_continuum - 1.0))
        quartic_errors.append(abs(result.energy_skyrme / quartic_continuum - 1.0))

    assert all(later < earlier for earlier, later in zip(sigma_errors, sigma_errors[1:]))
    assert all(later < earlier for earlier, later in zip(quartic_errors, quartic_errors[1:]))
    assert sigma_errors[-1] < 1.0e-3
    assert quartic_errors[-1] < 2.0e-3


def test_fixed_vacuum_rank_one_map_matches_energy_and_zero_charge() -> None:
    """Check boundary quadrature and the vanishing continuum quartic term."""
    amplitude = 0.7
    continuum_sigma = 3.0 * amplitude**2 * math.pi**2 / 64.0
    sigma_errors = []
    quartic_values = []

    for size in (5, 9, 17, 33):
        coordinate = np.linspace(0.0, 1.0, size)
        x, y, z = np.meshgrid(coordinate, coordinate, coordinate, indexing="ij")
        alpha = (
            amplitude
            * np.sin(math.pi * x)
            * np.sin(math.pi * y)
            * np.sin(math.pi * z)
        )
        values = np.stack(
            (np.cos(alpha), np.sin(alpha), np.zeros_like(alpha), np.zeros_like(alpha)),
            axis=-1,
        )
        step = 1.0 / (size - 1)
        field = SU2GridField(
            values,
            spacing=(step, step, step),
            boundary="fixed_vacuum",
        )
        result = compute_nearest_neighbor_diagnostics(field)

        assert result.topological_charge == pytest.approx(0.0, abs=1e-12)
        sigma_errors.append(abs(result.energy_sigma / continuum_sigma - 1.0))
        quartic_values.append(result.energy_skyrme)

    assert all(later < earlier for earlier, later in zip(sigma_errors, sigma_errors[1:]))
    assert sigma_errors[-1] < 1.1e-3
    assert quartic_values[-1] < quartic_values[0] * 0.03


def test_fixed_vacuum_hedgehog_charge_converges_with_declared_orientation() -> None:
    """Check non-rounded charge convergence and orientation reversal."""
    charge_errors = []
    for size in (9, 17, 25, 33, 49):
        step = 2.0 / (size - 1)
        field = hedgehog(
            (size, size, size), radius=0.8, spacing=(step, step, step)
        )
        result = compute_nearest_neighbor_diagnostics(field)
        assert result.topological_charge < 0.0
        charge_errors.append(abs(result.topological_charge + 1.0))

    assert all(later < earlier for earlier, later in zip(charge_errors, charge_errors[1:]))
    assert charge_errors[-1] < 0.05

    size = 33
    step = 2.0 / (size - 1)
    field = hedgehog((size, size, size), radius=0.8, spacing=(step, step, step))
    baseline = compute_nearest_neighbor_diagnostics(field)
    spatial_reflection = SU2GridField(
        field.components[::-1].copy(), spacing=field.spacing, boundary=field.boundary
    )
    reflected_result = compute_nearest_neighbor_diagnostics(spatial_reflection)
    target_reflection = SU2GridField(
        field.components * np.array((-1.0, 1.0, 1.0, 1.0)),
        spacing=field.spacing,
        boundary=field.boundary,
    )
    target_result = compute_nearest_neighbor_diagnostics(
        target_reflection, vacuum=(-1.0, 0.0, 0.0, 0.0)
    )

    assert reflected_result.topological_charge == pytest.approx(
        -baseline.topological_charge, abs=1e-12
    )
    assert target_result.topological_charge == pytest.approx(
        -baseline.topological_charge, abs=1e-12
    )
    assert reflected_result.energy_total == pytest.approx(baseline.energy_total, rel=1e-12)
    assert target_result.energy_total == pytest.approx(baseline.energy_total, rel=1e-12)

