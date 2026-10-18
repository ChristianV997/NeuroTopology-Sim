"""Adversarial public-contract tests for the four-shell EEG forward model (HOLD / SYNTHETIC_ONLY).

These tests import ``physics.eeg_forward`` directly and fail loudly if it is missing. They check
identities, symmetries, closed forms derived from the homogeneous boundary problem, input rejection,
and the truncation controls. They are software-contract checks on a synthetic, concentric head.
They do not establish agreement with recordings, individual anatomy, or any biological quantity.
No participant data, dataset, or network resource is used.

Independent references, derived here rather than read back from the model:

* Homogeneous transfer ratio. With every conductivity equal, the free-space degree-l term
  r**-(l+1) is supplemented in d < r < r4 by a regular term r**l. Zero radial current at r4 fixes the
  coefficient, and the surface value is (2l+1)/l times the free-space term.
* Homogeneous pole values. Summing the radial series (2l+1) P_l(+-1) t**(l-1) gives closed forms in
  t = d / r4.
* Tangential pole symmetry. The model is concentric. Reflection through the plane normal to a
  tangential moment keeps the source axis and the pole sensors fixed and reverses the moment, so the
  potential at a pole must vanish.
"""
from __future__ import annotations

import numpy as np
import pytest

from physics.eeg_forward import (
    FourSphereGeometry,
    FourSphereInputError,
    FourSphereQualityError,
    forward_potentials,
    transfer_ratios,
)

_REL = 1e-12
R_LAYERED = (0.079, 0.080, 0.085, 0.090)
R4 = R_LAYERED[3]
SIGMA1 = 0.33
LAYERED = FourSphereGeometry(R_LAYERED, (0.33, 1.79, 0.0042, 0.33))
HOMOGENEOUS = FourSphereGeometry(R_LAYERED, (SIGMA1, SIGMA1, SIGMA1, SIGMA1))
GEOMETRIES = pytest.mark.parametrize("geometry", [LAYERED, HOMOGENEOUS], ids=["layered", "homogeneous"])

AXIAL_SOURCE = np.array([0.0, 0.0, 0.04])          # d / r4 = 0.44
OBLIQUE_SOURCE = np.array([0.02, -0.03, 0.035])    # d / r4 = 0.56
MOMENT = np.array([1e-9, -2e-9, 0.5e-9])


def _pot(geometry, source, moment, sensors, max_degree=128):
    return forward_potentials(geometry, source, moment, sensors, max_degree=max_degree).potentials_v


def _scale(values) -> float:
    return float(np.max(np.abs(values)))


def _assert_close(actual, expected, *, scale, rel=_REL):
    """Absolute tolerance relative to a reference scale, so near-zero entries are not over-constrained."""
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=rel * scale)


def _sensors(seed: int, n: int = 8) -> np.ndarray:
    pts = np.random.default_rng(seed).normal(size=(n, 3))
    return R4 * pts / np.linalg.norm(pts, axis=1, keepdims=True)


def _unit(vector) -> np.ndarray:
    vector = np.asarray(vector, dtype=float)
    return vector / np.linalg.norm(vector)


def _perpendicular(axis) -> np.ndarray:
    return _unit(np.cross(axis, [0.3, -0.5, 0.8]))


def _polar_sensors(axis, angles) -> np.ndarray:
    """Sensors on the scalp at polar angles from the source axis, in the plane of a fixed perpendicular."""
    u = _perpendicular(axis)
    return np.array([R4 * (np.cos(t) * axis + np.sin(t) * u) for t in angles])


def _rotation(seed: int) -> np.ndarray:
    q, r = np.linalg.qr(np.random.default_rng(seed).normal(size=(3, 3)))
    q = q * np.sign(np.diag(r))
    return q * np.sign(np.linalg.det(q))


# ── superposition and linearity ──────────────────────────────────────────────

@GEOMETRIES
def test_radial_tangential_and_mixed_moments_superpose(geometry):
    axis = _unit(OBLIQUE_SOURCE)
    radial = (MOMENT @ axis) * axis
    tangential = MOMENT - radial
    sensors = _sensors(5)
    whole = _pot(geometry, OBLIQUE_SOURCE, MOMENT, sensors)
    radial_part = _pot(geometry, OBLIQUE_SOURCE, radial, sensors)
    tangential_part = _pot(geometry, OBLIQUE_SOURCE, tangential, sensors)
    assert _scale(radial_part) > 0.0 and _scale(tangential_part) > 0.0  # the split is not vacuous
    _assert_close(radial_part + tangential_part, whole, scale=_scale(whole))


@GEOMETRIES
def test_potential_is_linear_in_the_moment(geometry):
    m1, m2 = MOMENT, np.array([-0.4e-9, 1.1e-9, 0.9e-9])
    sensors = _sensors(6)
    a, b = 2.5, -0.75
    lhs = _pot(geometry, OBLIQUE_SOURCE, a * m1 + b * m2, sensors)
    rhs = a * _pot(geometry, OBLIQUE_SOURCE, m1, sensors) + b * _pot(geometry, OBLIQUE_SOURCE, m2, sensors)
    _assert_close(lhs, rhs, scale=_scale(lhs))


# ── tangential pole symmetry and sign convention ─────────────────────────────

@GEOMETRIES
@pytest.mark.parametrize("source", [AXIAL_SOURCE, OBLIQUE_SOURCE], ids=["axial", "oblique"])
def test_tangential_dipole_has_no_pole_value(geometry, source):
    # Poles are evaluated with general sensors so the tail scale is defined. A poles-only query with an exactly
    # zero signal is refused by the tail estimate, which is checked separately below.
    axis = _unit(source)
    tangential = _perpendicular(axis) * 1e-9
    poles = np.vstack([R4 * axis, -R4 * axis])
    batch = _pot(geometry, source, tangential, np.vstack([poles, _sensors(7)]))
    assert np.all(np.abs(batch[:2]) <= _REL * _scale(batch[2:]))


@GEOMETRIES
@pytest.mark.parametrize("source", [AXIAL_SOURCE, OBLIQUE_SOURCE], ids=["axial", "oblique"])
def test_poles_only_tangential_query_never_returns_a_spurious_value(geometry, source):
    # Contract: either the call refuses (zero signal, undefined tail estimate) or every pole value is at round-off.
    axis = _unit(source)
    tangential = _perpendicular(axis) * 1e-9
    poles = np.vstack([R4 * axis, -R4 * axis])
    scale = _scale(_pot(geometry, source, tangential, _sensors(7)))
    try:
        values = _pot(geometry, source, tangential, poles)
    except FourSphereQualityError:
        return
    assert np.all(np.abs(values) <= _REL * scale)


@GEOMETRIES
def test_radial_dipole_is_positive_toward_its_pole_and_negative_away(geometry):
    poles = np.array([[0.0, 0.0, R4], [0.0, 0.0, -R4]])
    moment = np.array([0.0, 0.0, 1e-9])
    for z in (0.04, -0.04):  # source above and below the centre; the moment points to +z in both cases
        toward, away = _pot(geometry, np.array([0.0, 0.0, z]), moment, poles)
        assert toward > 0.0 > away


@GEOMETRIES
def test_tangential_dipole_is_positive_on_the_side_it_points_toward(geometry):
    sensors = np.array([[R4, 0.0, 0.0], [-R4, 0.0, 0.0]])
    toward, away = _pot(geometry, AXIAL_SOURCE, np.array([1e-9, 0.0, 0.0]), sensors)
    assert toward > 0.0 > away


# ── closed forms and transfer ratios (homogeneous limit) ─────────────────────

def test_homogeneous_transfer_ratios_are_two_l_plus_one_over_l():
    degrees = np.arange(1, 65)
    np.testing.assert_allclose(transfer_ratios(HOMOGENEOUS, 64), (2 * degrees + 1) / degrees, rtol=_REL, atol=0)


def test_layered_transfer_ratios_differ_from_the_homogeneous_limit():
    assert not np.allclose(transfer_ratios(LAYERED, 4), transfer_ratios(HOMOGENEOUS, 4), rtol=1e-3, atol=0)


@pytest.mark.parametrize("depth", [0.02, 0.04, 0.06])
def test_homogeneous_radial_pole_values_match_the_closed_form(depth):
    t = depth / R4
    poles = np.array([[0.0, 0.0, R4], [0.0, 0.0, -R4]])
    got = _pot(HOMOGENEOUS, np.array([0.0, 0.0, depth]), np.array([0.0, 0.0, 1e-9]), poles)
    prefactor = 1e-9 / (4.0 * np.pi * SIGMA1 * R4**2)
    expected = prefactor * np.array([((1 + t) / (1 - t) ** 2 - 1) / t, ((1 - t) / (1 + t) ** 2 - 1) / t])
    _assert_close(got, expected, scale=_scale(expected))


# ── rotational equivariance and frame convention ─────────────────────────────

@GEOMETRIES
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_rotating_source_moment_and_sensors_together_leaves_potentials_unchanged(geometry, seed):
    rot = _rotation(seed)
    sensors = _sensors(11)
    base = _pot(geometry, OBLIQUE_SOURCE, MOMENT, sensors)
    rotated = _pot(geometry, rot @ OBLIQUE_SOURCE, rot @ MOMENT, sensors @ rot.T)
    _assert_close(rotated, base, scale=_scale(base))


@GEOMETRIES
def test_rotating_sensors_alone_changes_the_potentials(geometry):
    rot = _rotation(4)
    sensors = _sensors(11)
    base = _pot(geometry, OBLIQUE_SOURCE, MOMENT, sensors)
    moved = _pot(geometry, OBLIQUE_SOURCE, MOMENT, sensors @ rot.T)
    assert _scale(moved - base) > 1e-3 * _scale(base)  # negative control: the equivariance test is not vacuous


# ── scalar, shape, and batch behaviour ───────────────────────────────────────

def test_one_sensor_row_returns_one_potential():
    out = forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, _sensors(3)[:1], max_degree=128)
    assert out.potentials_v.shape == (1,)


def test_sensors_evaluated_as_a_batch_match_one_at_a_time():
    sensors = _sensors(8)
    batch = _pot(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors)
    single = np.concatenate([_pot(LAYERED, OBLIQUE_SOURCE, MOMENT, s[None]) for s in sensors])
    _assert_close(batch, single, scale=_scale(batch))


def test_sensor_order_permutes_the_output():
    sensors = _sensors(9)
    order = np.array([3, 0, 7, 1, 5, 2, 6, 4])
    _assert_close(_pot(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors[order]),
                  _pot(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors)[order],
                  scale=_scale(_pot(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors)))


def test_tuple_and_list_inputs_match_array_inputs():
    sensors = _sensors(10)
    as_arrays = _pot(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors)
    as_lists = _pot(LAYERED, tuple(OBLIQUE_SOURCE), list(MOMENT), sensors.tolist())
    np.testing.assert_array_equal(as_lists, as_arrays)


def test_a_flat_three_vector_sensor_is_rejected_not_read_as_three_sensors():
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, _sensors(12)[0])


@pytest.mark.parametrize("bad_source, bad_moment", [
    (np.stack([OBLIQUE_SOURCE, OBLIQUE_SOURCE]), MOMENT),
    (OBLIQUE_SOURCE, np.stack([MOMENT, MOMENT])),
])
def test_batched_sources_and_moments_are_rejected_rather_than_broadcast(bad_source, bad_moment):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, bad_source, bad_moment, _sensors(13))


# ── finiteness and continuity at the poles and the centre ────────────────────

@GEOMETRIES
def test_potentials_are_finite_on_the_axis_and_near_both_poles(geometry):
    axis = _unit(OBLIQUE_SOURCE)
    sensors = _polar_sensors(axis, [0.0, 1e-9, 1e-6, np.pi - 1e-6, np.pi])
    for moment in (axis * 1e-9, _perpendicular(axis) * 1e-9, MOMENT):
        assert np.all(np.isfinite(_pot(geometry, OBLIQUE_SOURCE, moment, sensors)))


@GEOMETRIES
@pytest.mark.parametrize("moment", [MOMENT, np.array([1e-9, 0.0, 0.0])], ids=["mixed", "tangential"])
def test_potentials_converge_to_the_pole_value_as_the_sensor_approaches_the_axis(geometry, moment):
    axis = _unit(OBLIQUE_SOURCE)
    scale = _scale(_pot(geometry, OBLIQUE_SOURCE, moment, _sensors(9)))
    pole = _pot(geometry, OBLIQUE_SOURCE, moment, _polar_sensors(axis, [0.0]))
    for theta in (1e-6, 1e-3):
        near = _pot(geometry, OBLIQUE_SOURCE, moment, _polar_sensors(axis, [theta]))
        assert np.all(np.abs(near - pole) <= 100.0 * theta * scale)
        far_pole = _pot(geometry, OBLIQUE_SOURCE, moment, _polar_sensors(axis, [np.pi]))
        near_back = _pot(geometry, OBLIQUE_SOURCE, moment, _polar_sensors(axis, [np.pi - theta]))
        assert np.all(np.abs(near_back - far_pole) <= 100.0 * theta * scale)


@GEOMETRIES
def test_potentials_are_continuous_as_the_source_approaches_the_centre_from_any_direction(geometry):
    sensors = _sensors(13)
    at_centre = _pot(geometry, np.zeros(3), MOMENT, sensors, max_degree=64)
    for direction in (np.array([0.3, 0.2, 0.9]), np.array([1.0, 0.0, 0.0])):
        near = _pot(geometry, 1e-8 * _unit(direction), MOMENT, sensors, max_degree=64)
        _assert_close(near, at_centre, scale=_scale(at_centre), rel=1e-5)


# ── truncation controls ──────────────────────────────────────────────────────

@pytest.mark.parametrize("max_degree", [1, 2, 4, 8])
def test_a_few_legendre_terms_are_not_accepted_as_convergence(max_degree):
    with pytest.raises(FourSphereQualityError, match="truncation tail"):
        _pot(LAYERED, AXIAL_SOURCE, MOMENT, _sensors(2), max_degree=max_degree)


def test_converged_sum_is_insensitive_to_further_terms():
    sensors = _sensors(2)
    short = _pot(LAYERED, AXIAL_SOURCE, MOMENT, sensors, max_degree=64)
    long = _pot(LAYERED, AXIAL_SOURCE, MOMENT, sensors, max_degree=128)
    _assert_close(short, long, scale=_scale(long), rel=1e-9)


def test_deep_source_non_convergence_is_reported_not_hidden():
    deep = np.array([0.0, 0.0, 0.87 * R4])  # d / r4 = 0.87, below r1 = 0.079 m
    moment = np.array([0.0, 0.0, 1e-9])
    with pytest.raises(FourSphereQualityError, match="truncation tail"):
        _pot(LAYERED, deep, moment, _sensors(2), max_degree=16)
    assert np.all(np.isfinite(_pot(LAYERED, deep, moment, _sensors(2), max_degree=256)))


def test_tail_tolerance_is_a_strict_control():
    sensors = _sensors(2)
    tail = forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors, max_degree=128).diagnostics["tail_relative"]
    assert tail > 0.0
    with pytest.raises(FourSphereQualityError, match="truncation tail"):
        forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors, max_degree=128, tail_tol=tail / 2.0)
    forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors, max_degree=128, tail_tol=tail * 2.0)


def test_residual_gate_compares_the_reported_residuals_against_its_tolerance():
    # The three gated residuals sit at round-off and are not separable by tolerance alone, so the gate is
    # tested through its reported worst value: just below it the results are withheld, just above they pass.
    sensors = _sensors(2)
    diag = forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors, max_degree=128).diagnostics
    worst = max(diag[key] for key in ("interface_potential_residual", "interface_current_residual",
                                      "scalp_zero_current_residual"))
    assert worst > 0.0
    with pytest.raises(FourSphereQualityError, match="boundary residuals"):
        forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors, max_degree=128, residual_tol=worst / 2.0)
    forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors, max_degree=128, residual_tol=worst * 2.0)


def test_interface_potential_residual_is_gated_on_its_own():
    # At this extreme conductivity contrast the interface-potential residual exceeds the other two by orders
    # of magnitude. A tolerance between them isolates that gate, so disabling it cannot go unnoticed.
    geometry = FourSphereGeometry((0.06931, 0.07318, 0.0736, 0.0809), (0.0004, 5.2088, 0.0365, 0.0199))
    sensors = np.array([[0.0, 0.0, 0.0809]])
    source, moment = np.array([0.0, 0.0, 0.01]), np.array([0.0, 0.0, 1e-9])
    diag = forward_potentials(geometry, source, moment, sensors, max_degree=32,
                              residual_tol=1.0, tail_tol=1.0).diagnostics
    potential = diag["interface_potential_residual"]
    others = max(diag["interface_current_residual"], diag["scalp_zero_current_residual"])
    assert others < potential / 100.0  # the separation holds for this geometry
    tol = np.sqrt(potential * others)
    with pytest.raises(FourSphereQualityError, match="boundary residuals"):
        forward_potentials(geometry, source, moment, sensors, max_degree=32, residual_tol=tol, tail_tol=1.0)


def test_tail_estimate_follows_the_documented_geometric_extrapolation():
    # Independent oracle built from public inputs. Each degree's envelope bounds its term: |P_l| <= 1,
    # |P_l'| <= l(l+1)/2, and |q_t . e| <= |q_t|. The reported tail extrapolates the last envelope from its last
    # ratio r as env_L r / (1 - r), relative to the largest sensor potential. The result is an estimate, not a bound.
    sensors = _sensors(21)
    degrees = 12
    depth = float(np.linalg.norm(OBLIQUE_SOURCE))
    axis = _unit(OBLIQUE_SOURCE)
    q_r = float(MOMENT @ axis)
    q_t_norm = float(np.linalg.norm(MOMENT - q_r * axis))
    prefactor = 1.0 / (4.0 * np.pi * LAYERED.conductivities_sm[0] * R4**2)
    degree = np.arange(1, degrees + 1)
    coeff = transfer_ratios(LAYERED, degrees) * prefactor * (depth / R4) ** (degree - 1)
    envelope = np.abs(coeff) * (degree * abs(q_r) + degree * (degree + 1) / 2.0 * q_t_norm)
    r = envelope[-1] / envelope[-2]
    tail_abs = envelope[-1] * r / (1.0 - r)
    result = forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors, max_degree=degrees, tail_tol=1.0)
    expected = tail_abs / _scale(result.potentials_v)
    assert result.diagnostics["tail_relative"] == pytest.approx(expected, rel=1e-9)


def test_result_fields_agree_with_the_transfer_ratio_api():
    result = forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, _sensors(2), max_degree=128)
    assert result.max_degree == 128
    assert result.potentials_v.shape == (8,)
    np.testing.assert_array_equal(result.transfer_ratios, transfer_ratios(LAYERED, 128))


# ── malformed inputs fail closed ─────────────────────────────────────────────

def test_error_types_are_value_errors():
    assert issubclass(FourSphereInputError, ValueError)
    assert issubclass(FourSphereQualityError, ValueError)


@pytest.mark.parametrize("radii, sigmas", [
    ((0.080, 0.079, 0.085, 0.090), (0.33,) * 4),                    # not strictly increasing
    ((0.079, 0.079, 0.085, 0.090), (0.33,) * 4),                    # equal radii
    ((0.0, 0.080, 0.085, 0.090), (0.33,) * 4),                      # zero radius
    ((0.079, 0.080, 0.085, float("nan")), (0.33,) * 4),             # non-finite radius
    ((0.079, 0.080, 0.085, 1.5), (0.33,) * 4),                      # scalp above 1 m: unit error
    ((0.079, 0.080, 0.085), (0.33,) * 4),                           # three radii
    ((0.079, 0.080, 0.085, 0.090), (0.33, 0.33, 0.33)),             # three conductivities
    ((0.079, 0.080, 0.085, 0.090), (0.0, 0.33, 0.33, 0.33)),        # zero conductivity
    ((0.079, 0.080, 0.085, 0.090), (1e-5, 0.33, 0.33, 0.33)),       # below the bound
    ((0.079, 0.080, 0.085, 0.090), (0.33, 0.33, 0.33, 11.0)),       # above the bound
    ((0.079, 0.080, 0.085, 0.090), (0.33, float("inf"), 0.33, 0.33)),
])
def test_invalid_geometry_is_rejected(radii, sigmas):
    with pytest.raises(FourSphereInputError):
        FourSphereGeometry(radii, sigmas)


@pytest.mark.parametrize("source", [
    [R_LAYERED[0], 0.0, 0.0],        # on the brain boundary
    [0.2, 0.0, 0.0],                 # outside the head
    [float("nan"), 0.0, 0.0],
    [0.01, 0.0],                     # wrong length
])
def test_out_of_domain_source_is_rejected(source):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, source, MOMENT, _sensors(2))


@pytest.mark.parametrize("moment", [[float("inf"), 0.0, 0.0], [1.0, 2.0]])
def test_non_finite_or_misshapen_moment_is_rejected(moment):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, OBLIQUE_SOURCE, moment, _sensors(2))


@pytest.mark.parametrize("sensors", [
    _sensors(2) * (1.0 + 1e-6),          # 1e-6 relative off the scalp: outside the 1e-9 tolerance
    np.zeros((0, 3)),                    # no sensors
    _sensors(2)[:, :2],                  # shape (N, 2)
    np.vstack([_sensors(2)[:1], [[np.nan, 0.0, 0.0]]]),
])
def test_malformed_sensors_are_rejected(sensors):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, sensors)


@pytest.mark.parametrize("max_degree", [True, 4.0, "64", 0, 513])
def test_invalid_max_degree_is_rejected(max_degree):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, _sensors(2), max_degree=max_degree)


@pytest.mark.parametrize("kwargs", [
    {"residual_tol": 0.0},
    {"residual_tol": -1e-9},
    {"residual_tol": float("nan")},
    {"tail_tol": 0.0},
    {"tail_tol": float("inf")},
])
def test_invalid_tolerances_are_rejected(kwargs):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, OBLIQUE_SOURCE, MOMENT, _sensors(2), **kwargs)
