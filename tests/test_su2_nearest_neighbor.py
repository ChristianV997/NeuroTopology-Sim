"""Synthetic checks for the checkerboard-safe forward-link objective."""

import numpy as np
import pytest

from field_theory.skyrme_diagnostics import compute_skyrme_diagnostics
from field_theory.su2 import SU2GridField, hedgehog
from field_theory.su2.nearest_neighbor import (
    _energy_components,
    _forward_differences,
    compute_nearest_neighbor_diagnostics,
    nearest_neighbor_energy_gradient_finite_difference,
    nearest_neighbor_energy_gradient,
    probe_nearest_neighbor_curvature,
    relax_skyrme_field_nearest_neighbor,
)


def _small_hedgehog() -> SU2GridField:
    return hedgehog((5, 5, 5), radius=0.8, spacing=(0.5, 0.5, 0.5))


def _smooth_hedgehog(samples: int, radius: float) -> SU2GridField:
    coordinates = np.linspace(-1.0, 1.0, samples)
    x, y, z = np.meshgrid(coordinates, coordinates, coordinates, indexing="ij")
    r = np.sqrt(x * x + y * y + z * z)
    s = np.clip(r / radius, 0.0, 1.0)
    profile = np.pi * (1.0 - 1.5 * s + 0.5 * s**3)
    profile = np.where(r < radius, profile, 0.0)
    radial = np.zeros((samples, samples, samples, 3), dtype=np.float64)
    nonzero = r > 0.0
    sine = np.sin(profile)
    radial[..., 0][nonzero] = sine[nonzero] * x[nonzero] / r[nonzero]
    radial[..., 1][nonzero] = sine[nonzero] * y[nonzero] / r[nonzero]
    radial[..., 2][nonzero] = sine[nonzero] * z[nonzero] / r[nonzero]
    values = np.concatenate((np.cos(profile)[..., None], radial), axis=-1)
    spacing = 2.0 / (samples - 1)
    return SU2GridField(values, spacing=(spacing,) * 3, boundary="fixed_vacuum")


def _simpson(values: np.ndarray, step: float) -> float:
    if (values.size - 1) % 2:
        raise ValueError("composite Simpson quadrature needs an even interval count")
    return float(
        step
        / 3.0
        * (
            values[0]
            + values[-1]
            + 4.0 * np.sum(values[1:-1:2])
            + 2.0 * np.sum(values[2:-1:2])
        )
    )


def _radial_hedgehog_reference(radius: float, f_pi: float = 1.0, e: float = 1.0):
    # Independent one-dimensional continuum formulas for n=(cos(F),sin(F) r_hat).
    intervals = 32768
    r = np.linspace(0.0, radius, intervals + 1)
    step = radius / intervals
    s = r / radius
    profile = np.pi * (1.0 - 1.5 * s + 0.5 * s**3)
    derivative = (1.5 * np.pi / radius) * (s**2 - 1.0)
    sine = np.sin(profile)
    sigma_integrand = r**2 * derivative**2 + 2.0 * sine**2
    sine_four_over_r2 = np.zeros_like(r)
    np.divide(sine**4, r**2, out=sine_four_over_r2, where=r > 0.0)
    # For sum_{i<j}|d_i n wedge d_j n|^2 the hedgehog density is
    # 2 F'^2 sin^2(F)/r^2 + sin^4(F)/r^4. Integrating over 4 pi r^2
    # gives the radial integrand below; the factor of two is easy to lose.
    skyrme_integrand = 2.0 * derivative**2 * sine**2 + sine_four_over_r2
    degree_integrand = sine**2 * derivative
    energy_sigma = 0.5 * np.pi * f_pi**2 * _simpson(sigma_integrand, step)
    energy_skyrme = 2.0 * np.pi / e**2 * _simpson(skyrme_integrand, step)
    charge = 2.0 / np.pi * _simpson(degree_integrand, step)
    return energy_sigma, energy_skyrme, charge


def _geodesic_perturb(field: np.ndarray, tangent: np.ndarray, amount: float) -> np.ndarray:
    lengths = np.linalg.norm(tangent, axis=-1)
    angles = amount * lengths
    factor = np.full_like(lengths, amount)
    np.divide(np.sin(angles), lengths, out=factor, where=lengths > 0.0)
    return field * np.cos(angles)[..., None] + tangent * factor[..., None]


def test_forward_links_assign_nonzero_energy_to_periodic_checkerboard():
    values = np.zeros((8, 4, 4, 4), dtype=np.float64)
    values[..., 0] = ((-1.0) ** np.arange(8))[:, None, None]
    field = SU2GridField(values, spacing=(1.0, 1.0, 1.0), boundary="periodic")

    legacy = compute_skyrme_diagnostics(field.components, field.spacing, boundary="periodic")
    nearest = compute_nearest_neighbor_diagnostics(field)

    # The old centered stencil is retained as a legacy diagnostic; the new
    # forward-link energy sees every alternating nearest-neighbor jump.
    assert legacy.energy_total == 0.0
    assert nearest.energy_sigma > 0.0
    assert nearest.energy_total == nearest.energy_sigma + nearest.energy_skyrme
    assert np.linalg.norm(nearest_neighbor_energy_gradient(field)) < 1.0e-12


def test_checkerboard_first_order_stationary_point_reports_negative_curvature():
    values = np.zeros((8, 4, 4, 4), dtype=np.float64)
    values[..., 0] = ((-1.0) ** np.arange(8))[:, None, None]
    field = SU2GridField(values, spacing=(1.0, 1.0, 1.0), boundary="periodic")

    diagnostic = probe_nearest_neighbor_curvature(field)
    result = relax_skyrme_field_nearest_neighbor(field, max_iterations=1)

    assert 0 < diagnostic.probe_count <= 16
    assert diagnostic.assessment == "negative_curvature_detected"
    assert diagnostic.most_negative_directional_curvature < -1.0e-3
    assert result.termination == "gradient_tolerance"
    assert result.stationarity_status == "first_order_stationary"
    assert result.curvature_diagnostics == diagnostic
    assert result.minimum_certified is False


def test_no_detected_negative_probe_does_not_certify_a_minimum():
    values = np.zeros((4, 4, 4, 4), dtype=np.float64)
    values[..., 0] = 1.0
    field = SU2GridField(values, spacing=(1.0, 1.0, 1.0), boundary="periodic")

    result = relax_skyrme_field_nearest_neighbor(field, max_iterations=1)

    assert result.stationarity_status == "first_order_stationary"
    assert result.curvature_diagnostics.assessment == "no_negative_curvature_in_probe_set"
    assert result.minimum_certified is False


def test_reported_gradient_matches_directional_difference_of_its_objective():
    field = _small_hedgehog()
    gradient = nearest_neighbor_energy_gradient(field, finite_difference_step=1.0e-5)
    raw_direction = np.arange(1, field.components.size + 1, dtype=np.float64).reshape(
        field.components.shape
    )
    direction = raw_direction - field.components * np.sum(
        field.components * raw_direction, axis=-1, keepdims=True
    )
    direction[[0, -1], :, :, :] = 0.0
    direction[:, [0, -1], :, :] = 0.0
    direction[:, :, [0, -1], :] = 0.0

    epsilon = 2.0e-5
    plus = SU2GridField(
        _geodesic_perturb(field.components, direction, epsilon),
        spacing=field.spacing,
        boundary=field.boundary,
    )
    minus = SU2GridField(
        _geodesic_perturb(field.components, direction, -epsilon),
        spacing=field.spacing,
        boundary=field.boundary,
    )
    e_plus = compute_nearest_neighbor_diagnostics(plus).energy_total
    e_minus = compute_nearest_neighbor_diagnostics(minus).energy_total
    directional_fd = (e_plus - e_minus) / (2.0 * epsilon)
    gradient_dot_direction = float(np.sum(gradient * direction))

    assert gradient_dot_direction == pytest.approx(directional_fd, rel=2.0e-3, abs=2.0e-5)


@pytest.mark.parametrize("boundary", ["periodic", "fixed_vacuum"])
def test_analytic_gradient_matches_finite_difference_reference_and_directional_derivative(
    boundary: str,
):
    rng = np.random.default_rng(20261117)
    raw = rng.normal(size=(4, 4, 4, 4))
    values = raw / np.linalg.norm(raw, axis=-1, keepdims=True)
    if boundary == "fixed_vacuum":
        values[0, ...] = (1.0, 0.0, 0.0, 0.0)
        values[-1, ...] = (1.0, 0.0, 0.0, 0.0)
        values[:, 0, ...] = (1.0, 0.0, 0.0, 0.0)
        values[:, -1, ...] = (1.0, 0.0, 0.0, 0.0)
        values[:, :, 0, ...] = (1.0, 0.0, 0.0, 0.0)
        values[:, :, -1, ...] = (1.0, 0.0, 0.0, 0.0)
    field = SU2GridField(values, spacing=(0.7, 0.9, 1.1), boundary=boundary)

    analytic = nearest_neighbor_energy_gradient(field, finite_difference_step=1.0e-5)
    reference = nearest_neighbor_energy_gradient_finite_difference(
        field, finite_difference_step=1.0e-5
    )
    np.testing.assert_allclose(analytic, reference, rtol=2.0e-4, atol=2.0e-5)

    direction = rng.normal(size=field.components.shape)
    direction -= field.components * np.sum(
        field.components * direction, axis=-1, keepdims=True
    )
    if boundary == "fixed_vacuum":
        direction[[0, -1], :, :, :] = 0.0
        direction[:, [0, -1], :, :] = 0.0
        direction[:, :, [0, -1], :] = 0.0
    epsilon = 2.0e-5
    plus = SU2GridField(
        _geodesic_perturb(field.components, direction, epsilon),
        spacing=field.spacing,
        boundary=field.boundary,
    )
    minus = SU2GridField(
        _geodesic_perturb(field.components, direction, -epsilon),
        spacing=field.spacing,
        boundary=field.boundary,
    )
    directional_fd = (
        compute_nearest_neighbor_diagnostics(plus).energy_total
        - compute_nearest_neighbor_diagnostics(minus).energy_total
    ) / (2.0 * epsilon)
    assert float(np.sum(analytic * direction)) == pytest.approx(
        directional_fd, rel=3.0e-4, abs=3.0e-5
    )


def test_nearest_neighbor_relaxation_descends_and_preserves_unit_fixed_boundary():
    field = _small_hedgehog()
    initial_components = field.components.copy()
    initial_diagnostics = compute_nearest_neighbor_diagnostics(field)

    result = relax_skyrme_field_nearest_neighbor(
        field,
        max_iterations=2,
        initial_step=1.0e-4,
        finite_difference_step=1.0e-5,
        gradient_tolerance=1.0e-10,
    )

    assert result.iterations >= 1
    assert result.energy_history[0] == initial_diagnostics.energy_total
    assert np.all(np.diff(result.energy_history) < 0.0)
    assert result.topological_charge_history[0] == initial_diagnostics.topological_charge
    assert np.all(np.isfinite(result.topological_charge_history))
    np.testing.assert_array_equal(field.components, initial_components)
    np.testing.assert_allclose(
        np.sum(result.field.components**2, axis=-1), 1.0, rtol=0.0, atol=1.0e-14
    )
    for axis in range(3):
        for index in (0, -1):
            np.testing.assert_array_equal(
                np.take(result.field.components, index, axis=axis),
                np.take(field.components, index, axis=axis),
            )


def test_periodic_relaxation_uses_nonzero_forward_energy_for_checkerboard():
    values = np.zeros((8, 4, 4, 4), dtype=np.float64)
    values[..., 0] = ((-1.0) ** np.arange(8))[:, None, None]
    field = SU2GridField(values, spacing=(1.0, 1.0, 1.0), boundary="periodic")

    result = relax_skyrme_field_nearest_neighbor(field, max_iterations=1)

    assert result.energy_history[0] > 0.0
    assert result.energy_history[-1] <= result.energy_history[0]
    assert result.termination == "gradient_tolerance"
    np.testing.assert_allclose(np.sum(result.field.components**2, axis=-1), 1.0, atol=1.0e-14)


def test_smooth_hedgehog_energy_and_charge_converge_to_independent_radial_quadrature():
    radius = 0.83
    reference_sigma, reference_skyrme, reference_charge = _radial_hedgehog_reference(radius)
    assert reference_charge == pytest.approx(-1.0, abs=1.0e-10)
    errors = []
    for samples in (17, 25, 33, 41):
        result = compute_nearest_neighbor_diagnostics(_smooth_hedgehog(samples, radius))
        errors.append(
            (
                abs(result.energy_sigma - reference_sigma),
                abs(result.energy_skyrme - reference_skyrme),
                abs(result.topological_charge - reference_charge),
            )
        )

    # Every refinement step must improve all three independent comparisons,
    # rather than passing on a single favorable endpoint.
    assert np.all(np.diff(np.asarray(errors), axis=0) < 0.0)
    assert errors[-1][0] < 0.1 * reference_sigma
    assert errors[-1][1] < 0.1 * reference_skyrme
    assert errors[-1][2] < 0.1



def test_anisotropic_hedgehog_charge_converges_and_reverses_under_spatial_reflection():
    """Check charge refinement with unequal spacings and reversed domain orientation."""
    radius = 0.83
    refinement_levels = (
        ((17, 9, 5), (0.125, 0.25, 0.5)),
        ((33, 17, 9), (0.0625, 0.125, 0.25)),
        ((65, 33, 17), (0.03125, 0.0625, 0.125)),
        ((129, 65, 33), (0.015625, 0.03125, 0.0625)),
    )
    # For F(0)=pi and F(r>=R)=0, the continuum degree is
    # (2/pi) * integral_0^R F'(r) sin(F(r))**2 dr = -1.
    # Reflecting x reverses domain orientation and therefore gives +1.
    charge_errors = []
    for shape, spacing in refinement_levels:
        field = hedgehog(shape, radius=radius, spacing=spacing)
        np.testing.assert_allclose(
            (np.asarray(shape) - 1) * np.asarray(spacing),
            (2.0, 2.0, 2.0),
            rtol=0.0,
            atol=1.0e-15,
        )
        reflected = SU2GridField(
            np.flip(field.components, axis=0).copy(),
            spacing=field.spacing,
            boundary=field.boundary,
        )

        charge = compute_nearest_neighbor_diagnostics(field).topological_charge
        reflected_charge = compute_nearest_neighbor_diagnostics(
            reflected
        ).topological_charge
        assert charge < 0.0
        assert reflected_charge > 0.0
        charge_errors.append((abs(charge + 1.0), abs(reflected_charge - 1.0)))

    errors = np.asarray(charge_errors)
    assert np.all(np.diff(errors, axis=0) < 0.0)
    assert errors[-1, 0] < 0.04
    assert errors[-1, 1] < 0.04

def test_fixed_vacuum_energy_includes_nonzero_normal_boundary_derivatives():
    samples = 9
    coordinates = np.linspace(-1.0, 1.0, samples)
    x, y, z = np.meshgrid(coordinates, coordinates, coordinates, indexing="ij")
    theta = 0.25 * (1.0 - x**2) * (1.0 - y**2) * (1.0 - z**2)
    values = np.zeros((samples, samples, samples, 4), dtype=np.float64)
    values[..., 0] = np.cos(theta)
    values[..., 1] = np.sin(theta)
    field = SU2GridField(values, spacing=(0.25,) * 3, boundary="fixed_vacuum")

    # Dirichlet values are vacuum on the face, but the interior-to-face normal
    # link has a nonzero chord; it must contribute to the nearest-link energy.
    normal_link = field.components[-1, 3, 3] - field.components[-2, 3, 3]
    result = compute_nearest_neighbor_diagnostics(field)

    assert np.linalg.norm(normal_link) > 0.0
    assert result.energy_sigma > 0.0
    assert np.all(np.isfinite((result.energy_sigma, result.energy_skyrme, result.topological_charge)))


def test_resolved_hedgehog_charge_drift_is_small_over_one_relaxation_step():
    field = _smooth_hedgehog(41, 0.83)
    result = relax_skyrme_field_nearest_neighbor(
        field,
        max_iterations=1,
        initial_step=1.0e-5,
        gradient_tolerance=1.0e-12,
    )
    initial_charge, final_charge = result.topological_charge_history

    assert abs(initial_charge + 1.0) < 0.05
    assert result.iterations == 1
    assert result.energy_history[-1] < result.energy_history[0]
    assert abs(final_charge - initial_charge) < 1.0e-6
    for axis in range(3):
        for index in (0, -1):
            np.testing.assert_array_equal(
                np.take(result.field.components, index, axis=axis),
                np.take(field.components, index, axis=axis),
            )


def test_fixed_site_mask_pins_interior_values_and_zeros_masked_gradient():
    field = _small_hedgehog()
    mask = np.zeros(field.components.shape[:3], dtype=bool)
    mask[2, 2, 2] = True

    analytic = nearest_neighbor_energy_gradient(field, fixed_mask=mask)
    reference = nearest_neighbor_energy_gradient_finite_difference(field, fixed_mask=mask)
    result = relax_skyrme_field_nearest_neighbor(
        field,
        fixed_mask=mask,
        max_iterations=2,
        initial_step=1.0e-4,
        gradient_tolerance=1.0e-12,
    )

    np.testing.assert_array_equal(analytic[mask], np.zeros_like(analytic[mask]))
    np.testing.assert_array_equal(reference[mask], np.zeros_like(reference[mask]))
    np.testing.assert_array_equal(
        result.field.components[mask], field.components[mask]
    )
    assert result.minimum_certified is False


@pytest.mark.parametrize(
    "mask",
    [
        np.zeros((2, 2, 2), dtype=bool),
        np.zeros((5, 5, 5), dtype=np.uint8),
    ],
)
def test_fixed_site_mask_rejects_wrong_shape_or_non_boolean_values(mask):
    field = _small_hedgehog()
    with pytest.raises(ValueError, match="fixed_mask"):
        relax_skyrme_field_nearest_neighbor(field, fixed_mask=mask)

def test_fixed_mask_active_gradient_matches_reference_and_is_tangent():
    field = _small_hedgehog()
    fixed_mask = np.zeros(field.components.shape[:3], dtype=bool)
    fixed_mask[2, 2, 2] = True
    fixed_mask[1, 2, 2] = True
    fixed_mask[2, 1, 2] = True
    f_pi = 1.3
    e = 0.7

    analytic = nearest_neighbor_energy_gradient(
        field, f_pi=f_pi, e=e, fixed_mask=fixed_mask
    )
    reference = nearest_neighbor_energy_gradient_finite_difference(
        field, f_pi=f_pi, e=e, fixed_mask=fixed_mask
    )
    active = np.ones(fixed_mask.shape, dtype=bool)
    active[[0, -1], :, :] = False
    active[:, [0, -1], :] = False
    active[:, :, [0, -1]] = False
    active &= ~fixed_mask

    np.testing.assert_allclose(
        analytic[active], reference[active], rtol=2.0e-4, atol=2.0e-5
    )
    np.testing.assert_array_equal(
        analytic[fixed_mask], np.zeros_like(analytic[fixed_mask])
    )
    tangent_residual = np.sum(field.components * analytic, axis=-1)
    assert np.max(np.abs(tangent_residual[active])) < 1.0e-10
    assert np.any(np.linalg.norm(analytic[active], axis=-1) > 1.0e-10)


def test_extreme_exact_parallel_links_keep_quartic_energy_and_gradient_finite():
    vectors = np.array(
        [
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (-1.0, 0.0, 0.0, 0.0),
            (0.0, -1.0, 0.0, 0.0),
        ],
        dtype=np.float64,
    )
    x, y = np.indices((4, 4))
    components = np.repeat(vectors[(x + y) % 4][:, :, None, :], 2, axis=2)
    spacing = (1.0e-200, 1.0e-200, 1.0e200)
    field = SU2GridField(components, spacing=spacing, boundary="periodic")
    f_pi = np.sqrt(8.0e-200)
    differences = _forward_differences(components, spacing, "periodic")

    energy_sigma, energy_skyrme = _energy_components(
        components, differences, spacing, "periodic", f_pi, 1.0
    )
    gradient_e1 = nearest_neighbor_energy_gradient(field, f_pi=f_pi, e=1.0)
    gradient_e2 = nearest_neighbor_energy_gradient(field, f_pi=f_pi, e=2.0)

    assert energy_sigma == pytest.approx(128.0, rel=1.0e-12)
    assert energy_skyrme == 0.0
    assert np.all(np.isfinite(gradient_e1))
    assert np.all(np.isfinite(gradient_e2))
    np.testing.assert_array_equal(gradient_e1, gradient_e2)

def test_continuum_l2_residual_is_mesh_consistent_and_uses_anisotropic_cell_volume(monkeypatch):
    from field_theory.su2 import nearest_neighbor as module

    def evaluate(shape, spacing):
        values = np.zeros((*shape, 4), dtype=np.float64)
        values[..., 0] = 1.0
        field = SU2GridField(values, spacing=spacing, boundary="periodic")
        cell_volume = float(np.prod(spacing))

        def manufactured_gradient(current, **kwargs):
            gradient = np.zeros_like(current.components)
            gradient[..., 1] = cell_volume
            return gradient

        monkeypatch.setattr(module, "nearest_neighbor_energy_gradient", manufactured_gradient)
        return module.relax_skyrme_field_nearest_neighbor(
            field,
            max_iterations=1,
            max_backtracks=0,
            initial_step=1.0e-8,
            gradient_tolerance=0.5,
            stationarity_metric="continuum_l2",
        )

    coarse = evaluate((4, 4, 4), (0.25, 0.25, 0.25))
    fine = evaluate((8, 8, 8), (0.125, 0.125, 0.125))
    assert coarse.cell_volume == pytest.approx(0.25**3)
    assert fine.cell_volume == pytest.approx(0.125**3)
    assert coarse.continuum_l2_residual == pytest.approx(1.0)
    assert fine.continuum_l2_residual == pytest.approx(1.0)
    assert coarse.raw_gradient_norm == pytest.approx(0.125)
    assert fine.raw_gradient_norm == pytest.approx(0.125 / np.sqrt(8.0))
    assert coarse.active_site_count == 4**3
    assert fine.active_site_count == 8**3
    assert coarse.active_l2_measure == pytest.approx(1.0)
    assert fine.active_l2_measure == pytest.approx(1.0)
    assert coarse.active_l2_rms_residual == pytest.approx(1.0)
    assert fine.active_l2_rms_residual == pytest.approx(1.0)

    anisotropic = evaluate((4, 5, 6), (0.25, 0.5, 0.125))
    expected_volume = 0.25 * 0.5 * 0.125
    assert anisotropic.cell_volume == pytest.approx(expected_volume)
    assert anisotropic.continuum_l2_residual == pytest.approx(
        np.sqrt(4 * 5 * 6 * expected_volume)
    )
    assert anisotropic.active_site_count == 4 * 5 * 6
    assert anisotropic.active_l2_measure == pytest.approx(4 * 5 * 6 * expected_volume)
    assert anisotropic.active_l2_rms_residual == pytest.approx(1.0)


def test_continuum_l2_descent_rescales_steps_and_preserves_pinned_sites():
    field = _small_hedgehog()
    fixed = np.zeros(field.components.shape[:3], dtype=bool)
    fixed[2, 2, 2] = True
    kwargs = {
        "fixed_mask": fixed,
        "max_iterations": 1,
        "initial_step": 1.0e-6,
        "gradient_tolerance": 1.0e-16,
        "stationarity_metric": "euclidean",
    }
    euclidean = relax_skyrme_field_nearest_neighbor(
        field, descent_metric="euclidean", **kwargs
    )
    continuum = relax_skyrme_field_nearest_neighbor(
        field, descent_metric="continuum_l2", **kwargs
    )
    assert euclidean.energy_history[-1] < euclidean.energy_history[0]
    assert continuum.energy_history[-1] < continuum.energy_history[0]
    assert continuum.descent_metric == "continuum_l2"
    assert continuum.stationarity_metric == "euclidean"
    assert euclidean.active_site_count == continuum.active_site_count == 26
    assert continuum.continuum_l2_residual == pytest.approx(
        continuum.raw_gradient_norm / np.sqrt(continuum.cell_volume)
    )
    assert continuum.active_l2_measure == pytest.approx(
        continuum.active_site_count * continuum.cell_volume
    )
    assert continuum.active_l2_rms_residual == pytest.approx(
        continuum.continuum_l2_residual / np.sqrt(continuum.active_l2_measure)
    )
    np.testing.assert_array_equal(euclidean.field.components[fixed], field.components[fixed])
    np.testing.assert_array_equal(continuum.field.components[fixed], field.components[fixed])
    assert not np.array_equal(euclidean.field.components, continuum.field.components)


def test_default_optimizer_trajectory_matches_explicit_legacy_metrics():
    field = _small_hedgehog()
    kwargs = {
        "max_iterations": 2,
        "initial_step": 1.0e-4,
        "gradient_tolerance": 1.0e-10,
        "max_backtracks": 4,
    }
    default = relax_skyrme_field_nearest_neighbor(field, **kwargs)
    explicit = relax_skyrme_field_nearest_neighbor(
        field,
        stationarity_metric="euclidean",
        descent_metric="euclidean",
        **kwargs,
    )
    np.testing.assert_array_equal(default.field.components, explicit.field.components)
    assert default.energy_history == explicit.energy_history
    assert default.termination == explicit.termination
    assert default.raw_gradient_norm == explicit.raw_gradient_norm


def test_relaxation_rejects_empty_active_set_and_invalid_metric():
    field = _small_hedgehog()
    with pytest.raises(ValueError, match="no active sites"):
        relax_skyrme_field_nearest_neighbor(
            field, fixed_mask=np.ones(field.components.shape[:3], dtype=bool)
        )
    with pytest.raises(ValueError, match="stationarity_metric"):
        relax_skyrme_field_nearest_neighbor(field, stationarity_metric="bad")
    with pytest.raises(ValueError, match="descent_metric"):
        relax_skyrme_field_nearest_neighbor(field, descent_metric="bad")


def test_zero_gradient_reports_zero_mesh_residual_without_vacuous_mask():
    values = np.zeros((4, 4, 4, 4), dtype=np.float64)
    values[..., 0] = 1.0
    field = SU2GridField(values, spacing=(0.5, 0.25, 0.125), boundary="periodic")
    result = relax_skyrme_field_nearest_neighbor(
        field,
        stationarity_metric="continuum_l2",
        gradient_tolerance=1.0e-12,
    )
    assert result.termination == "gradient_tolerance"
    assert result.stationarity_status == "first_order_stationary"
    assert result.raw_gradient_norm == 0.0
    assert result.continuum_l2_residual == 0.0
    assert result.active_site_count == 4**3
    assert result.active_l2_measure == pytest.approx(1.0)
    assert result.active_l2_rms_residual == 0.0

