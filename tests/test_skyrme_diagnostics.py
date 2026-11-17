"""Synthetic contract tests for the standalone SU(2)/Skyrme diagnostics."""

import numpy as np
import pytest

from field_theory.skyrme_diagnostics import compute_skyrme_diagnostics
from field_theory.su2 import fixed_axis, hedgehog, vacuum


def _hedgehog(samples: int, radius: float = 0.8) -> np.ndarray:
    coordinates = np.linspace(-1.0, 1.0, samples)
    x, y, z = np.meshgrid(coordinates, coordinates, coordinates, indexing="ij")
    r = np.sqrt(x * x + y * y + z * z)
    s = np.clip(r / radius, 0.0, 1.0)
    # Monotone profile with F(0)=pi, F(R)=0, F'(R)=0 and
    # F(r)=pi-O(r) at the origin, so sin(F) x_hat is regular there.
    profile = np.pi * (1.0 - 1.5 * s + 0.5 * s**3)
    profile = np.where(r < radius, profile, 0.0)
    sin_profile = np.sin(profile)
    radial = np.zeros((samples, samples, samples, 3), dtype=np.float64)
    nonzero = r > 0.0
    radial[..., 0][nonzero] = sin_profile[nonzero] * x[nonzero] / r[nonzero]
    radial[..., 1][nonzero] = sin_profile[nonzero] * y[nonzero] / r[nonzero]
    radial[..., 2][nonzero] = sin_profile[nonzero] * z[nonzero] / r[nonzero]
    return np.concatenate((np.cos(profile)[..., None], radial), axis=-1)


def _rotation4() -> np.ndarray:
    def plane_rotation(i: int, j: int, angle: float) -> np.ndarray:
        matrix = np.eye(4)
        c, s = np.cos(angle), np.sin(angle)
        matrix[i, i] = c
        matrix[j, j] = c
        matrix[i, j] = -s
        matrix[j, i] = s
        return matrix

    return plane_rotation(0, 1, 0.37) @ plane_rotation(1, 3, -0.61) @ plane_rotation(0, 2, 0.23)


def test_constant_vacuum_has_zero_energy_and_degree() -> None:
    field = np.zeros((9, 9, 9, 4), dtype=np.float64)
    field[..., 0] = 1.0
    result = compute_skyrme_diagnostics(field, 0.25, boundary="fixed_vacuum")

    assert result.energy_sigma == 0.0
    assert result.energy_skyrme == 0.0
    assert result.energy_total == 0.0
    assert result.topological_charge == 0.0


def test_fixed_axis_map_has_zero_degree_and_no_quartic_energy() -> None:
    size = 16
    phase = 2.0 * np.pi * np.arange(size) / size
    field = np.zeros((size, size, size, 4), dtype=np.float64)
    field[..., 0] = np.cos(phase)[:, None, None]
    field[..., 1] = np.sin(phase)[:, None, None]

    result = compute_skyrme_diagnostics(field, 2.0 * np.pi / size, boundary="periodic")

    assert result.energy_sigma > 0.0
    assert result.energy_skyrme == 0.0
    assert abs(result.topological_charge) < 1.0e-12


def test_hedgehog_degree_converges_with_grid_refinement() -> None:
    charges = []
    for samples in (17, 25, 33):
        field = _hedgehog(samples)
        spacing = 2.0 / (samples - 1)
        result = compute_skyrme_diagnostics(field, spacing, boundary="fixed_vacuum")
        charges.append(result.topological_charge)
        assert result.energy_sigma > 0.0
        assert result.energy_skyrme > 0.0
        assert result.energy_total == pytest.approx(result.energy_sigma + result.energy_skyrme)

    # Under the declared orientation, this profile has degree -1.
    errors = [abs(charge + 1.0) for charge in charges]
    assert errors[-1] < errors[0]
    assert errors[-1] < 0.15


def test_spatial_orientation_reversal_flips_degree_sign() -> None:
    field = _hedgehog(25)
    spacing = 2.0 / 24
    original = compute_skyrme_diagnostics(field, spacing, boundary="fixed_vacuum")
    reflected = compute_skyrme_diagnostics(
        field[::-1, :, :, :].copy(), spacing, boundary="fixed_vacuum"
    )

    assert original.topological_charge < 0.0
    assert reflected.topological_charge > 0.0
    assert reflected.topological_charge == pytest.approx(-original.topological_charge, abs=1.0e-12)


def test_proper_global_target_rotation_preserves_energies_and_degree() -> None:
    field = _hedgehog(25)
    spacing = 2.0 / 24
    vacuum = np.array((1.0, 0.0, 0.0, 0.0))
    baseline = compute_skyrme_diagnostics(field, spacing, boundary="fixed_vacuum", vacuum=vacuum)

    rotation = _rotation4()
    assert np.linalg.det(rotation) == pytest.approx(1.0, abs=1.0e-14)
    rotated_field = np.einsum("ab,ijkb->ijka", rotation, field)
    rotated_vacuum = rotation @ vacuum
    rotated = compute_skyrme_diagnostics(
        rotated_field,
        spacing,
        boundary="fixed_vacuum",
        vacuum=rotated_vacuum,
    )

    assert rotated.energy_sigma == pytest.approx(baseline.energy_sigma, rel=1.0e-12, abs=1.0e-12)
    assert rotated.energy_skyrme == pytest.approx(baseline.energy_skyrme, rel=1.0e-12, abs=1.0e-12)
    assert rotated.topological_charge == pytest.approx(baseline.topological_charge, abs=1.0e-12)


def test_declared_energy_coefficients_have_expected_scaling() -> None:
    field = _hedgehog(17)
    spacing = 2.0 / 16
    baseline = compute_skyrme_diagnostics(field, spacing, boundary="fixed_vacuum")
    doubled_f = compute_skyrme_diagnostics(field, spacing, boundary="fixed_vacuum", f_pi=2.0)
    doubled_e = compute_skyrme_diagnostics(field, spacing, boundary="fixed_vacuum", e=2.0)

    assert doubled_f.energy_sigma == pytest.approx(4.0 * baseline.energy_sigma)
    assert doubled_f.energy_skyrme == pytest.approx(baseline.energy_skyrme)
    assert doubled_e.energy_sigma == pytest.approx(baseline.energy_sigma)
    assert doubled_e.energy_skyrme == pytest.approx(baseline.energy_skyrme / 4.0)


def test_quartic_energy_matches_independent_pauli_matrix_trace() -> None:
    rng = np.random.default_rng(77)
    raw = rng.normal(size=(5, 5, 5, 4))
    field = raw / np.linalg.norm(raw, axis=-1, keepdims=True)
    h, e = 0.7, 1.3
    sigma = np.asarray([
        [[0, 1], [1, 0]], [[0, -1j], [1j, 0]], [[1, 0], [0, -1]]
    ], dtype=complex)
    identity = np.eye(2, dtype=complex)

    def matrix(n):
        return n[..., 0, None, None] * identity + 1j * np.einsum("...a,aij->...ij", n[..., 1:], sigma)

    U = matrix(field)
    Udag = U.conj().swapaxes(-1, -2)
    derivatives = [(np.roll(field, -1, axis=i) - np.roll(field, 1, axis=i)) / (2 * h) for i in range(3)]
    currents = []
    for dn in derivatives:
        dU = dn[..., 0, None, None] * identity + 1j * np.einsum("...a,aij->...ij", dn[..., 1:], sigma)
        currents.append(Udag @ dU)
    trace_energy = 0.0
    for i in range(3):
        for j in range(i + 1, 3):
            comm = currents[i] @ currents[j] - currents[j] @ currents[i]
            trace_energy += np.sum(-np.trace(comm @ comm, axis1=-2, axis2=-1).real) * h**3 / (16 * e**2)
    result = compute_skyrme_diagnostics(field, h, boundary="periodic", e=e)
    assert result.energy_skyrme == pytest.approx(trace_energy, rel=1e-12, abs=1e-12)


def test_non_unit_field_and_implicit_boundary_are_rejected() -> None:
    bad_field = np.zeros((5, 5, 5, 4), dtype=np.float64)
    bad_field[..., 0] = 2.0
    with pytest.raises(ValueError, match="unit three-sphere"):
        compute_skyrme_diagnostics(bad_field, 1.0, boundary="periodic")

    vacuum_field = np.zeros((5, 5, 5, 4), dtype=np.float64)
    vacuum_field[..., 0] = 1.0
    with pytest.raises(ValueError, match="boundary must"):
        compute_skyrme_diagnostics(
            vacuum_field, 1.0, boundary="reflecting"  # type: ignore[arg-type]
        )


def test_fixed_vacuum_rejects_non_vacuum_outer_face() -> None:
    field = np.zeros((7, 7, 7, 4), dtype=np.float64)
    field[..., 0] = 1.0
    field[0, 3, 3] = (0.0, 1.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="outer face"):
        compute_skyrme_diagnostics(field, 1.0, boundary="fixed_vacuum")


def test_foundation_field_and_diagnostics_interoperate() -> None:
    vacuum_field = vacuum((7, 7, 7), spacing=(0.25,) * 3)
    vacuum_result = compute_skyrme_diagnostics(
        vacuum_field.components, vacuum_field.spacing, boundary=vacuum_field.boundary
    )
    assert vacuum_result.energy_total == 0.0
    phase_field = fixed_axis(np.zeros((7, 7, 7)), spacing=(0.25,) * 3)
    phase_result = compute_skyrme_diagnostics(
        phase_field.components, phase_field.spacing, boundary=phase_field.boundary
    )
    assert phase_result.topological_charge == 0.0
    errors = []
    for size in (17, 25, 33):
        field = hedgehog((size,) * 3, radius=0.8, spacing=(2 / (size - 1),) * 3)
        result = compute_skyrme_diagnostics(field.components, field.spacing, boundary=field.boundary)
        errors.append(abs(result.topological_charge + 1.0))
        assert result.energy_sigma > 0 and result.energy_skyrme > 0
    assert errors[2] < errors[1] < errors[0]
    assert errors[2] < 0.15


