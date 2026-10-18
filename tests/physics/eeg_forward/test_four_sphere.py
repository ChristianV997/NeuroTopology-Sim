"""Acceptance tests for the experimental four-shell EEG forward model.

Synthetic and offline. These tests check the numerical model against closed forms
and an independent layered solve. They support no biological or clinical claim.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from physics.eeg_forward import (
    FourSphereGeometry,
    FourSphereInputError,
    FourSphereQualityError,
    forward_potentials,
    transfer_ratios,
)
from physics.eeg_forward import four_sphere as fs

REPO_ROOT = Path(__file__).resolve().parents[3]
RADII = (0.079, 0.080, 0.085, 0.090)
R4 = RADII[3]
LAYERED = (0.33, 1.79, 0.0042, 0.33)
HOMOGENEOUS = (0.33, 0.33, 0.33, 0.33)


def _unit_vectors(rng: np.random.Generator, n: int) -> np.ndarray:
    x = rng.normal(size=(n, 3))
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def _scalp_points(rng: np.random.Generator, n: int) -> np.ndarray:
    return R4 * _unit_vectors(rng, n)


def _source_in_brain(rng: np.random.Generator, max_fraction: float = 0.95) -> np.ndarray:
    return _unit_vectors(rng, 1)[0] * RADII[0] * max_fraction * rng.uniform(0.05, 1.0)


def _closed_radial(t: np.ndarray | float, mu: np.ndarray) -> np.ndarray:
    """Sum_l (2l+1) t^(l-1) P_l(mu) = ((1 - t^2) D^(-3/2) - 1) / t, D = 1 - 2 t mu + t^2."""
    D = 1.0 - 2.0 * t * mu + t * t
    return ((1.0 - t * t) * D ** -1.5 - 1.0) / t


def _closed_tangential(t: float, mu: np.ndarray) -> np.ndarray:
    """Sum_l (2l+1)/l t^(l-1) P_l'(mu) in closed form (valid for t > 0, |mu| < 1)."""
    D = 1.0 - 2.0 * t * mu + t * t
    return 2.0 * D ** -1.5 + ((t - mu) / np.sqrt(D) + mu) / (t * (1.0 - mu * mu))


def _closed_form_potentials(source, moment, sensors, sigma: float = HOMOGENEOUS[0]) -> np.ndarray:
    depth = float(np.linalg.norm(source))
    axis = source / depth
    t = depth / R4
    q_r = float(moment @ axis)
    dirs = sensors / np.linalg.norm(sensors, axis=1, keepdims=True)
    mu = dirs @ axis
    q_te = dirs @ moment - q_r * mu
    return (q_r * _closed_radial(t, mu) + q_te * _closed_tangential(t, mu)) / (4.0 * np.pi * sigma * R4**2)


def _global_transfer(degree: int, radii, sigmas) -> float:
    """Independent layered solve for T_l: 7 unknowns, one linear system, no propagation.

    Brain potential is r^-(l+1) + a1 r^l with unit source coefficient, so T_l equals
    r4^(l+1) times the scalp potential.
    """
    r1, r2, r3, r4 = radii
    s1, s2, s3, s4 = sigmas
    l = degree

    def p(r):
        return r**l

    def q(r):
        return r ** (-(l + 1))

    def dp(r):
        return l * r ** (l - 1)

    def dq(r):
        return -(l + 1) * r ** (-(l + 2))

    A = np.zeros((7, 7))
    rhs = np.zeros(7)
    A[0] = [p(r1), -p(r1), -q(r1), 0, 0, 0, 0]
    rhs[0] = -q(r1)
    A[1] = [s1 * dp(r1), -s2 * dp(r1), -s2 * dq(r1), 0, 0, 0, 0]
    rhs[1] = -s1 * dq(r1)
    A[2] = [0, p(r2), q(r2), -p(r2), -q(r2), 0, 0]
    A[3] = [0, s2 * dp(r2), s2 * dq(r2), -s3 * dp(r2), -s3 * dq(r2), 0, 0]
    A[4] = [0, 0, 0, p(r3), q(r3), -p(r3), -q(r3)]
    A[5] = [0, 0, 0, s3 * dp(r3), s3 * dq(r3), -s4 * dp(r3), -s4 * dq(r3)]
    A[6] = [0, 0, 0, 0, 0, s4 * dp(r4), s4 * dq(r4)]
    x = np.linalg.solve(A, rhs)
    scalp = x[5] * p(r4) + x[6] * q(r4)
    return float(r4 ** (l + 1) * scalp)


def _potentials_with_weight(geometry, source, moment, sensors, weight, max_degree: int) -> np.ndarray:
    """Same expansion as forward_potentials, with an extra weight(l) on each degree.

    weight = 1 reproduces the production model. Used to show that a per-degree
    attenuation applied to both orientation terms is detected.
    """
    r4 = geometry.radii_m[3]
    sigma1 = geometry.conductivities_sm[0]
    depth = float(np.linalg.norm(source))
    axis = source / depth
    transfer = transfer_ratios(geometry, max_degree)
    dirs = sensors / np.linalg.norm(sensors, axis=1, keepdims=True)
    mu = dirs @ axis
    q_r = float(moment @ axis)
    q_te = dirs @ moment - q_r * mu
    P, dP = fs.legendre_and_derivative(max_degree, mu)
    total = np.zeros(len(sensors))
    for l in range(1, max_degree + 1):
        coeff = weight(l) * transfer[l - 1] * (depth / r4) ** (l - 1) / (4.0 * np.pi * sigma1 * r4**2)
        total += coeff * (l * q_r * P[l] + dP[l] * q_te)
    return total


def _scale(values: np.ndarray) -> float:
    return float(np.max(np.abs(values))) + 1e-300


# --- Package and import -----------------------------------------------------------

def test_package_import_is_clean_and_numpy_only():
    code = (
        "import sys\n"
        "import physics.eeg_forward as m\n"
        "assert 'scipy' not in sys.modules and 'sklearn' not in sys.modules\n"
        "assert 'mne' not in sys.modules\n"
        "print(sorted(m.__all__))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True,
        env={"PYTHONPATH": str(REPO_ROOT), "PATH": "/usr/bin:/bin"}, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "forward_potentials" in proc.stdout


# --- Homogeneous closed forms -----------------------------------------------------

def test_homogeneous_transfer_ratio_is_2l_plus_1_over_l():
    T = transfer_ratios(FourSphereGeometry(RADII, HOMOGENEOUS), 128)
    l = np.arange(1, 129)
    np.testing.assert_allclose(T, (2 * l + 1) / l, rtol=1e-13, atol=0)


def test_homogeneous_forward_matches_closed_radial_and_tangential_forms():
    rng = np.random.default_rng(11)
    geometry = FourSphereGeometry(RADII, HOMOGENEOUS)
    for _ in range(10):
        source = _source_in_brain(rng)
        moment = rng.normal(size=3) * 1e-8
        sensors = _scalp_points(rng, 25)
        got = forward_potentials(geometry, source, moment, sensors, max_degree=256).potentials_v
        ref = _closed_form_potentials(source, moment, sensors)
        assert np.max(np.abs(got - ref)) / _scale(ref) < 1e-11


def test_radial_only_dipole_matches_closed_form_radial_term():
    rng = np.random.default_rng(12)
    geometry = FourSphereGeometry(RADII, HOMOGENEOUS)
    source = _source_in_brain(rng, max_fraction=0.9)
    axis = source / np.linalg.norm(source)
    moment = 3e-8 * axis
    sensors = _scalp_points(rng, 30)
    got = forward_potentials(geometry, source, moment, sensors, max_degree=256).potentials_v
    dirs = sensors / np.linalg.norm(sensors, axis=1, keepdims=True)
    t = np.linalg.norm(source) / R4
    ref = 3e-8 * _closed_radial(t, dirs @ axis) / (4.0 * np.pi * HOMOGENEOUS[0] * R4**2)
    assert np.max(np.abs(got - ref)) / _scale(ref) < 1e-11


def test_tangential_only_dipole_matches_closed_form_tangential_term():
    rng = np.random.default_rng(13)
    geometry = FourSphereGeometry(RADII, HOMOGENEOUS)
    source = _source_in_brain(rng, max_fraction=0.9)
    axis = source / np.linalg.norm(source)
    perp = np.cross(axis, rng.normal(size=3))
    moment = 3e-8 * perp / np.linalg.norm(perp)
    sensors = _scalp_points(rng, 30)
    got = forward_potentials(geometry, source, moment, sensors, max_degree=256).potentials_v
    dirs = sensors / np.linalg.norm(sensors, axis=1, keepdims=True)
    t = np.linalg.norm(source) / R4
    ref = (dirs @ moment) * _closed_tangential(t, dirs @ axis) / (4.0 * np.pi * HOMOGENEOUS[0] * R4**2)
    assert np.max(np.abs(got - ref)) / _scale(ref) < 1e-11


def test_near_axis_and_exact_axis_sensors_are_finite_and_accurate():
    geometry = FourSphereGeometry(RADII, HOMOGENEOUS)
    source = np.array([0.0, 0.0, 0.05])
    moment = np.array([1e-8, 2e-8, 3e-8])
    limit = None
    for eps in (1e-3, 1e-6):
        sensors = np.array([
            [np.sin(eps) * R4, 0.0, np.cos(eps) * R4],
            [-np.sin(eps) * R4, 0.0, -np.cos(eps) * R4],
        ])
        got = forward_potentials(geometry, source, moment, sensors, max_degree=256).potentials_v
        ref = _closed_form_potentials(source, moment, sensors)
        assert np.all(np.isfinite(got))
        assert np.max(np.abs(got - ref)) / _scale(ref) < 1e-7
        limit = got
    exact = np.array([[0.0, 0.0, R4], [0.0, 0.0, -R4]])
    got_exact = forward_potentials(geometry, source, moment, exact, max_degree=256).potentials_v
    assert np.all(np.isfinite(got_exact))
    assert np.max(np.abs(got_exact - limit)) / _scale(limit) < 1e-6


def test_depth_zero_potential_is_degree_one_only():
    rng = np.random.default_rng(14)
    geometry = FourSphereGeometry(RADII, LAYERED)
    moment = rng.normal(size=3) * 1e-8
    sensors = _scalp_points(rng, 20)
    prefactor = 1.0 / (4.0 * np.pi * LAYERED[0] * R4**2)
    t1 = transfer_ratios(geometry, 1)[0]
    got = forward_potentials(geometry, [0.0, 0.0, 0.0], moment, sensors, max_degree=32).potentials_v
    dirs = sensors / np.linalg.norm(sensors, axis=1, keepdims=True)
    np.testing.assert_allclose(got, t1 * prefactor * (dirs @ moment), rtol=1e-12, atol=1e-30)


# --- Layered transfer ratios ------------------------------------------------------

@pytest.mark.parametrize("degree", [1, 2, 3, 4, 8, 16, 32, 64])
def test_layered_transfer_ratio_matches_independent_global_solve(degree):
    T = transfer_ratios(FourSphereGeometry(RADII, LAYERED), degree)[degree - 1]
    ref = _global_transfer(degree, RADII, LAYERED)
    assert abs(T - ref) / abs(ref) < 1e-11


@pytest.mark.parametrize("thickness", [1e-3, 1e-6, 1e-9])
def test_thin_shell_transfer_matches_independent_global_solve(thickness):
    radii = (RADII[0], RADII[0] * (1.0 + thickness), RADII[2], RADII[3])
    T = transfer_ratios(FourSphereGeometry(radii, LAYERED), 16)
    ref = np.array([_global_transfer(l, radii, LAYERED) for l in range(1, 17)])
    assert np.max(np.abs(T - ref) / np.abs(ref)) < 1e-11


# --- Residuals, tails, gates -----------------------------------------------------

def test_interface_and_scalp_residuals_stay_at_round_off_to_degree_256():
    rng = np.random.default_rng(15)
    geometry = FourSphereGeometry(RADII, LAYERED)
    result = forward_potentials(geometry, _source_in_brain(rng), [1e-8, 0.0, 0.0], _scalp_points(rng, 10),
                                max_degree=256)
    d = result.diagnostics
    assert d["interface_potential_residual"] < 1e-12
    assert d["interface_current_residual"] < 1e-12
    assert d["scalp_zero_current_residual"] < 1e-12
    assert d["tail_relative"] < 1e-10


def test_quality_gate_rejects_residuals_above_tolerance():
    rng = np.random.default_rng(16)
    geometry = FourSphereGeometry(RADII, LAYERED)
    with pytest.raises(FourSphereQualityError, match="residuals"):
        forward_potentials(geometry, _source_in_brain(rng), [1e-8, 0.0, 0.0], _scalp_points(rng, 3),
                           max_degree=32, residual_tol=1e-30)


def test_truncation_converges_for_declared_depth_range():
    # Declared range: source depth / r4 <= 0.8. Tail and L = 128 vs 256 agree.
    geometry = FourSphereGeometry(RADII, LAYERED)
    source = np.array([0.0, 0.0, 0.8 * R4])
    moment = np.array([1e-8, 0.0, 1e-8])
    sensors = np.array([[0.0, R4 * np.sin(a), R4 * np.cos(a)] for a in np.linspace(0.1, 3.0, 12)])
    p128 = forward_potentials(geometry, source, moment, sensors, max_degree=128).potentials_v
    res256 = forward_potentials(geometry, source, moment, sensors, max_degree=256)
    assert np.max(np.abs(p128 - res256.potentials_v)) / _scale(p128) < 1e-9
    assert res256.diagnostics["tail_relative"] < 1e-10


def test_truncation_non_convergence_is_reported_not_hidden():
    # Source close to the brain boundary converges slowly; a short series must fail the gate.
    geometry = FourSphereGeometry(RADII, LAYERED)
    source = np.array([0.0, 0.0, 0.87 * R4])
    sensors = np.array([[0.0, 0.0, R4]])
    # Radial moment along the source axis, so the series is non-trivial at the sensor.
    with pytest.raises(FourSphereQualityError, match="truncation tail"):
        forward_potentials(geometry, source, [0.0, 0.0, 1e-8], sensors, max_degree=16)


def test_overflow_for_extreme_radius_ratio_is_a_quality_error():
    geometry = FourSphereGeometry((0.01, 0.02, 0.05, 0.1), LAYERED)
    with pytest.raises(FourSphereQualityError, match="overflow"):
        transfer_ratios(geometry, 512)


# --- Regression: common 1/l attenuation must be detected --------------------------

def test_one_over_l_attenuation_applied_to_both_terms_is_detected():
    rng = np.random.default_rng(17)
    geometry = FourSphereGeometry(RADII, HOMOGENEOUS)
    source = _source_in_brain(rng, max_fraction=0.9)
    axis = source / np.linalg.norm(source)
    sensors = _scalp_points(rng, 20)

    radial = 3e-8 * axis
    production = forward_potentials(geometry, source, radial, sensors, max_degree=256).potentials_v
    variant = _potentials_with_weight(geometry, source, radial, sensors, lambda l: 1.0 / l, 256)
    ref = _closed_form_potentials(source, radial, sensors)
    assert np.max(np.abs(production - ref)) / _scale(ref) < 1e-11
    assert np.max(np.abs(variant - ref)) / _scale(ref) > 1e-2

    tangential = np.cross(axis, rng.normal(size=3))
    tangential = 3e-8 * tangential / np.linalg.norm(tangential)
    production_t = forward_potentials(geometry, source, tangential, sensors, max_degree=256).potentials_v
    variant_t = _potentials_with_weight(geometry, source, tangential, sensors, lambda l: 1.0 / l, 256)
    ref_t = _closed_form_potentials(source, tangential, sensors)
    assert np.max(np.abs(production_t - ref_t)) / _scale(ref_t) < 1e-11
    assert np.max(np.abs(variant_t - ref_t)) / _scale(ref_t) > 1e-2


# --- Symmetry, reference, reproducibility ----------------------------------------

def test_rotation_of_source_moment_and_sensors_leaves_potentials_unchanged():
    rng = np.random.default_rng(18)
    geometry = FourSphereGeometry(RADII, LAYERED)
    source = _source_in_brain(rng)
    moment = rng.normal(size=3) * 1e-8
    sensors = _scalp_points(rng, 15)
    rotation, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    base = forward_potentials(geometry, source, moment, sensors, max_degree=128).potentials_v
    rotated = forward_potentials(
        geometry, rotation @ source, rotation @ moment, sensors @ rotation.T, max_degree=128,
    ).potentials_v
    assert np.max(np.abs(rotated - base)) / _scale(base) < 1e-12


def test_potential_is_linear_in_dipole_moment():
    rng = np.random.default_rng(19)
    geometry = FourSphereGeometry(RADII, LAYERED)
    source = _source_in_brain(rng)
    sensors = _scalp_points(rng, 12)
    q1 = rng.normal(size=3) * 1e-8
    q2 = rng.normal(size=3) * 1e-8

    def pot(q):
        return forward_potentials(geometry, source, q, sensors, max_degree=128).potentials_v

    np.testing.assert_allclose(pot(q1 + 2.0 * q2), pot(q1) + 2.0 * pot(q2), rtol=1e-12, atol=1e-25)


def test_average_reference_gives_zero_mean_over_scalp():
    # Sensors on one meridian at Gauss-Legendre nodes in mu. Integrating V over
    # mu in [-1, 1] equals the sphere mean; the degree-0 term is zero, so it vanishes.
    geometry = FourSphereGeometry(RADII, LAYERED)
    nodes, weights = np.polynomial.legendre.leggauss(64)
    sensors = R4 * np.column_stack([np.sqrt(1.0 - nodes**2), np.zeros_like(nodes), nodes])
    source = np.array([0.0, 0.0, 0.05])
    moment = np.array([0.0, 0.0, 1e-8])
    values = forward_potentials(geometry, source, moment, sensors, max_degree=128).potentials_v
    assert abs(np.sum(weights * values)) / _scale(values) < 1e-9


def test_repeated_calls_are_bitwise_identical():
    rng = np.random.default_rng(20)
    geometry = FourSphereGeometry(RADII, LAYERED)
    source = _source_in_brain(rng)
    moment = rng.normal(size=3) * 1e-8
    sensors = _scalp_points(rng, 9)
    a = forward_potentials(geometry, source, moment, sensors)
    b = forward_potentials(geometry, source, moment, sensors)
    assert np.array_equal(a.potentials_v, b.potentials_v)
    assert np.array_equal(a.transfer_ratios, b.transfer_ratios)


@pytest.mark.parametrize("sigmas", [HOMOGENEOUS, LAYERED, (0.2, 0.5, 0.01, 0.4)])
@pytest.mark.parametrize("fraction", [0.0, 0.3, 0.9])
def test_outputs_are_finite_over_geometry_and_depth_grid(sigmas, fraction):
    rng = np.random.default_rng(21)
    geometry = FourSphereGeometry(RADII, sigmas)
    source = _unit_vectors(rng, 1)[0] * RADII[0] * fraction
    result = forward_potentials(geometry, source, [1e-8, -2e-8, 3e-8], _scalp_points(rng, 40),
                                max_degree=256)
    assert np.all(np.isfinite(result.potentials_v))
    assert np.all(np.isfinite(result.transfer_ratios))
    assert result.max_degree == 256


def test_scale_invariance_of_transfer_ratios():
    unit = FourSphereGeometry((0.079 / 0.09, 0.080 / 0.09, 0.085 / 0.09, 1.0), LAYERED)
    physical = FourSphereGeometry(RADII, LAYERED)
    np.testing.assert_allclose(transfer_ratios(unit, 32), transfer_ratios(physical, 32), rtol=1e-12)


# --- Input validation ------------------------------------------------------------

@pytest.mark.parametrize("radii", [
    (0.08, 0.079, 0.085, 0.09),
    (0.0, 0.08, 0.085, 0.09),
    (0.079, 0.080, 0.085, 1.5),
    (0.079, 0.080, 0.085, float("nan")),
    (0.079, 0.080, 0.085),
])
def test_invalid_radii_are_rejected(radii):
    with pytest.raises(FourSphereInputError):
        FourSphereGeometry(radii, LAYERED)


@pytest.mark.parametrize("sigmas", [
    (0.33, 1.79, 0.0042, 0.0),
    (0.33, 1.79, 0.0042, 50.0),
    (0.33, float("inf"), 0.0042, 0.33),
])
def test_invalid_conductivities_are_rejected(sigmas):
    with pytest.raises(FourSphereInputError):
        FourSphereGeometry(RADII, sigmas)


def _valid_call():
    geometry = FourSphereGeometry(RADII, LAYERED)
    sensors = np.array([[0.0, 0.0, R4]])
    return geometry, [0.0, 0.0, 0.03], [1e-8, 0.0, 0.0], sensors


@pytest.mark.parametrize("override, message", [
    ({"source_position_m": [0.0, 0.0, RADII[0]]}, "inside the brain"),
    ({"source_position_m": [0.0, 0.0]}, "finite 3-vector"),
    ({"source_position_m": [float("nan"), 0.0, 0.0]}, "finite 3-vector"),
    ({"dipole_moment_am": [1.0, 2.0]}, "finite 3-vector"),
    ({"sensor_positions_m": np.array([[0.0, 0.0, 0.5 * R4]])}, "scalp sphere"),
    ({"sensor_positions_m": np.zeros((0, 3))}, "N >= 1"),
    ({"sensor_positions_m": np.array([[0.0, 0.0]])}, "shape"),
    ({"max_degree": 0}, "max_degree"),
    ({"max_degree": 513}, "max_degree"),
    ({"max_degree": True}, "integer"),
    ({"max_degree": 2.0}, "integer"),
    ({"residual_tol": 0.0}, "residual_tol"),
    ({"residual_tol": float("nan")}, "residual_tol"),
    ({"tail_tol": -1.0}, "tail_tol"),
])
def test_invalid_forward_inputs_are_rejected(override, message):
    geometry, source, moment, sensors = _valid_call()
    kwargs = {"source_position_m": source, "dipole_moment_am": moment, "sensor_positions_m": sensors}
    kwargs.update(override)
    source_arg = kwargs.pop("source_position_m")
    moment_arg = kwargs.pop("dipole_moment_am")
    sensor_arg = kwargs.pop("sensor_positions_m")
    with pytest.raises(FourSphereInputError, match=message):
        forward_potentials(geometry, source_arg, moment_arg, sensor_arg, **kwargs)


# --- Convention, envelope, and preset checks ------------------------------------------

def test_free_space_series_matches_direct_dipole_field():
    # First-principles check of the radial and tangential terms, their signs, and their
    # source-depth power, with no shells. The degree sum must equal the direct field
    # q.(r - r_s) / (4 pi sigma |r - r_s|^3), so no shell model is involved.
    rng = np.random.default_rng(31)
    sigma = LAYERED[0]
    for _ in range(8):
        e_s = _unit_vectors(rng, 1)[0]
        source = rng.uniform(0.0, 0.85) * R4 * e_s
        moment = rng.normal(size=3) * 1e-8
        sensors = _scalp_points(rng, 12)
        diff = sensors - source
        direct = diff @ moment / (4.0 * np.pi * sigma * np.linalg.norm(diff, axis=1) ** 3)
        dirs = sensors / np.linalg.norm(sensors, axis=1, keepdims=True)
        mu = np.clip(dirs @ e_s, -1.0, 1.0)
        q_r = moment @ e_s
        q_te = dirs @ moment - q_r * mu
        P, dP = fs.legendre_and_derivative(200, mu)
        ratio = np.linalg.norm(source) / R4
        series = np.zeros(len(sensors))
        for l in range(1, 201):
            series += ratio ** (l - 1) * (l * q_r * P[l] + dP[l] * q_te) / (4.0 * np.pi * sigma * R4**2)
        assert np.max(np.abs(series - direct)) / _scale(direct) < 1e-12


def test_tangential_term_vanishes_at_both_poles():
    # At the poles e = +-e_s, so q_t . e = 0 and the tangential term is zero. The potential
    # there must not depend on the tangential part of the dipole.
    geometry = FourSphereGeometry(RADII, LAYERED)
    source = np.array([0.0, 0.0, 0.05])
    poles = np.array([[0.0, 0.0, R4], [0.0, 0.0, -R4]])
    with_tangential = forward_potentials(geometry, source, [1e-8, -2e-8, 3e-8], poles,
                                         max_degree=256).potentials_v
    radial_only = forward_potentials(geometry, source, [0.0, 0.0, 3e-8], poles,
                                     max_degree=256).potentials_v
    np.testing.assert_allclose(with_tangential, radial_only, rtol=1e-12, atol=0)


def test_legendre_sup_bounds_used_by_the_tail_envelope_hold():
    # Computational check on a grid, not a proof. The inequalities |P_l| <= 1 and
    # |P_l'| <= l(l+1)/2 on [-1, 1] are classical results.
    mu = np.linspace(-1.0, 1.0, 4001)
    P, dP = fs.legendre_and_derivative(256, mu)
    degrees = np.arange(1, 257)[:, None]
    assert np.max(np.abs(P[1:])) <= 1.0 + 1e-12
    assert np.max(np.abs(dP[1:]) / (degrees * (degrees + 1) / 2.0)) <= 1.0 + 1e-12


def test_tail_estimate_is_conservative_against_a_longer_series():
    # Tail estimate must be at least the actual truncation error. Checked against a degree-512
    # reference for this configuration only. It is not a proof for all geometries.
    rng = np.random.default_rng(37)
    geometry = FourSphereGeometry(RADII, LAYERED)
    source = np.array([0.0, 0.0, 0.6 * RADII[0]])
    moment = rng.normal(size=3) * 1e-8
    sensors = _scalp_points(rng, 15)
    reference = forward_potentials(geometry, source, moment, sensors, max_degree=512,
                                   tail_tol=1.0).potentials_v
    for degree in (32, 64):
        result = forward_potentials(geometry, source, moment, sensors, max_degree=degree, tail_tol=1.0)
        actual = np.max(np.abs(result.potentials_v - reference)) / _scale(reference)
        assert result.diagnostics["tail_relative"] >= actual


@pytest.mark.parametrize("k, sigma_skull", [(20, 0.33 / 20), (40, 0.33 / 40), (80, 0.33 / 80)])
def test_naess_table1_preset_geometry(k, sigma_skull):
    geometry = fs.naess2017_table1_geometry(k)
    assert geometry.radii_m == (0.079, 0.080, 0.085, 0.090)
    assert geometry.conductivities_sm == pytest.approx((0.33, 1.65, sigma_skull, 0.33))


@pytest.mark.parametrize("bad", [10, 60, 40.5, True, None])
def test_naess_preset_rejects_other_skull_ratios(bad):
    with pytest.raises(FourSphereInputError):
        fs.naess2017_table1_geometry(bad)


# --- Oracle cross-check -----------------------------------------------------------

@pytest.mark.skip(reason=(
    "Independent oracle (Hermes Agent A, PR #409) is not on main. The cross-check is run "
    "out of tree from a scratch copy and reported in the handoff; it is never imported here."
))
def test_independent_oracle_cross_check():
    pass
