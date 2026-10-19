from __future__ import annotations

import numpy as np
import pytest

from numpy.polynomial.legendre import legval

from tools.mne_csd_reference_audit.kkt import (
    OperatorInputError,
    apply_csd,
    csd_operator,
    csd_operator_regularised_after_inverse,
    csd_operator_without_sum_constraint,
    kkt_coefficients,
    legendre_matrices,
    regularise,
    centering_matrix,
    unit_vectors,
)
from tools.mne_csd_reference_audit.montages import MONTAGES

RADIUS = 0.095
LAMBDA2 = 1e-5
ALL = sorted(MONTAGES)
ASYMMETRIC = ["seeded_cap_7", "seeded_cap_12", "near_coincident_6", "ring_apex_9"]
SYMMETRIC = ["tetrahedron_4", "octahedron_6"]


def _positions(name: str) -> np.ndarray:
    return RADIUS * MONTAGES[name]()


def _scale(M: np.ndarray) -> float:
    return float(np.max(np.abs(M)))


def _mne_code_path(pos: np.ndarray, radius: float, lambda2: float) -> tuple[np.ndarray, np.ndarray]:
    """MNE 1.13.2 compute_current_source_density, transcribed from the verified sdist.

    Sources: mne/preprocessing/_csd.py (_prepare_G, _compute_csd) and
    mne/channels/interpolation.py (_calc_g, _calc_h). Written with numpy.polynomial.legendre.legval
    and not via the package, so it is an independent oracle for the code path, including the
    TC = Gi.sum(0) ordering that the package's projection form does not use.
    """
    u = pos / np.linalg.norm(pos, axis=1, keepdims=True)
    cos = np.clip(u @ u.T, -1, 1)
    g = [0.0] + [(2 * n + 1) / (n**4 * (n + 1) ** 4 * 4 * np.pi) for n in range(1, 51)]
    h = [0.0] + [(2 * n + 1) / (n**3 * (n + 1) ** 3 * 4 * np.pi) for n in range(1, 51)]
    G = legval(cos, g)
    H = legval(cos, h)
    G.flat[:: len(G) + 1] += lambda2
    Gi = np.linalg.inv(G)
    TC = Gi.sum(0)
    sgi = np.sum(TC)
    n = G.shape[0]
    Z = np.eye(n) - np.eye(n).mean(0)
    Cp2 = np.dot(Gi, Z)
    c02 = np.sum(Cp2, axis=0) / sgi
    C2 = Cp2 - np.dot(TC[:, np.newaxis], c02[np.newaxis, :])
    return (np.dot(C2.T, H).T / radius**2), G


@pytest.mark.parametrize("name", ALL)
def test_kkt_and_projection_forms_are_numerically_equivalent(name):
    pos = _positions(name)
    M_kkt = csd_operator(pos, radius=RADIUS, lambda2=LAMBDA2, method="kkt")
    M_proj = csd_operator(pos, radius=RADIUS, lambda2=LAMBDA2, method="projection")
    assert np.max(np.abs(M_kkt - M_proj)) / _scale(M_kkt) < 1e-10


@pytest.mark.parametrize("name", ALL)
def test_zero_sum_constraint_holds_on_the_coefficients(name):
    pos = _positions(name)
    unit = unit_vectors(pos)
    G, _ = legendre_matrices(unit)
    n = G.shape[0]
    C = kkt_coefficients(regularise(G, LAMBDA2), centering_matrix(n))
    assert np.max(np.abs(C.sum(axis=0))) < 1e-9 * max(1.0, np.max(np.abs(C)))


@pytest.mark.parametrize("name", ALL)
def test_constant_potential_maps_to_zero_current_density(name):
    M = csd_operator(_positions(name), radius=RADIUS, lambda2=LAMBDA2)
    residual = np.max(np.abs(apply_csd(M, np.ones(M.shape[0])))) / _scale(M)
    assert residual < 1e-10


@pytest.mark.parametrize("name", ALL)
def test_sphere_scaling_is_exactly_inverse_square_elementwise(name):
    unit = MONTAGES[name]()
    M_unit = csd_operator(unit, radius=1.0, lambda2=LAMBDA2)
    M_r = csd_operator(RADIUS * unit, radius=RADIUS, lambda2=LAMBDA2)
    assert np.max(np.abs(M_r * RADIUS**2 - M_unit)) / _scale(M_unit) < 1e-10


@pytest.mark.parametrize("name", ALL)
def test_channel_permutation_is_equivariant(name):
    pos = _positions(name)
    n = pos.shape[0]
    perm = np.random.default_rng(101).permutation(n)
    M = csd_operator(pos, radius=RADIUS, lambda2=LAMBDA2)
    M_perm = csd_operator(pos[perm], radius=RADIUS, lambda2=LAMBDA2)
    assert np.max(np.abs(M_perm - M[np.ix_(perm, perm)])) / _scale(M) < 1e-10


@pytest.mark.parametrize("name", ALL)
def test_output_is_finite_square_and_one_row_per_channel(name):
    pos = _positions(name)
    M = csd_operator(pos, radius=RADIUS, lambda2=LAMBDA2)
    assert M.shape == (pos.shape[0], pos.shape[0])
    assert np.all(np.isfinite(M))


def test_units_scale_with_length_inverse_square():
    unit = MONTAGES["seeded_cap_7"]()
    M_m = csd_operator(RADIUS * unit, radius=RADIUS, lambda2=LAMBDA2)
    M_mm = csd_operator(1000.0 * RADIUS * unit, radius=1000.0 * RADIUS, lambda2=LAMBDA2)
    np.testing.assert_allclose(M_mm * 1000.0**2, M_m, rtol=1e-10, atol=1e-12 * _scale(M_m))


@pytest.mark.parametrize("name", ASYMMETRIC)
def test_post_inverse_regularisation_is_discriminated(name):
    pos = _positions(name)
    M_ref = csd_operator(pos, radius=RADIUS, lambda2=LAMBDA2)
    M_var = csd_operator_regularised_after_inverse(pos, radius=RADIUS, lambda2=LAMBDA2)
    assert np.max(np.abs(M_var - M_ref)) / _scale(M_ref) > 1e-4


@pytest.mark.parametrize("name", ["seeded_cap_7", "seeded_cap_12", "ring_apex_9"])
def test_zero_sum_constraint_is_discriminated_on_asymmetric_montages(name):
    pos = _positions(name)
    M_ref = csd_operator(pos, radius=RADIUS, lambda2=LAMBDA2)
    M_var = csd_operator_without_sum_constraint(pos, radius=RADIUS, lambda2=LAMBDA2)
    assert np.max(np.abs(M_var - M_ref)) / _scale(M_ref) > 1e-2


@pytest.mark.parametrize("name", SYMMETRIC)
def test_zero_sum_constraint_is_redundant_on_symmetric_montages(name):
    # Documented limitation: on these layouts the constraint is implied by symmetry,
    # so they cannot test it. The asymmetric montages above do.
    pos = _positions(name)
    M_ref = csd_operator(pos, radius=RADIUS, lambda2=LAMBDA2)
    M_var = csd_operator_without_sum_constraint(pos, radius=RADIUS, lambda2=LAMBDA2)
    assert np.max(np.abs(M_var - M_ref)) / _scale(M_ref) < 1e-12


def test_duplicate_sensor_is_singular_without_regularisation_and_finite_with_it():
    unit = MONTAGES["seeded_cap_7"]()
    dup = np.vstack([unit, unit[:1]])
    with pytest.raises(np.linalg.LinAlgError):
        csd_operator(RADIUS * dup, radius=RADIUS, lambda2=0.0)
    assert np.all(np.isfinite(csd_operator(RADIUS * dup, radius=RADIUS, lambda2=LAMBDA2)))


@pytest.mark.parametrize("radius", [0.0, -0.095, float("nan"), float("inf")])
def test_invalid_radius_is_rejected(radius):
    with pytest.raises(OperatorInputError):
        csd_operator(_positions("tetrahedron_4"), radius=radius)


@pytest.mark.parametrize("lambda2", [-1e-9, 1.0, 2.0])
def test_lambda2_outside_mne_range_is_rejected(lambda2):
    with pytest.raises(OperatorInputError, match="lambda2"):
        csd_operator(_positions("tetrahedron_4"), radius=RADIUS, lambda2=lambda2)


@pytest.mark.parametrize("bad", [
    np.zeros((4, 2)),
    np.zeros((1, 3)),
    np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
    np.array([[np.nan, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
])
def test_malformed_positions_are_rejected(bad):
    with pytest.raises(OperatorInputError):
        csd_operator(bad, radius=RADIUS)


def test_unknown_method_is_rejected():
    with pytest.raises(OperatorInputError, match="method"):
        csd_operator(_positions("tetrahedron_4"), radius=RADIUS, method="lagrange")


def test_data_row_mismatch_is_rejected():
    M = csd_operator(_positions("tetrahedron_4"), radius=RADIUS)
    with pytest.raises(OperatorInputError, match="one row per channel"):
        apply_csd(M, np.zeros((3, 10)))


def test_regularise_adds_lambda2_exactly_to_the_diagonal():
    G = np.arange(16, dtype=float).reshape(4, 4)
    out = regularise(G, 1e-5)
    off_diagonal = ~np.eye(4, dtype=bool)
    np.testing.assert_array_equal((out - G)[off_diagonal], 0.0)
    np.testing.assert_allclose(np.diag(out - G), 1e-5, rtol=0, atol=1e-15)


@pytest.mark.parametrize("name", ["tetrahedron_4", "seeded_cap_12"])
def test_operator_wiring_matches_inline_formula_with_explicit_lambda(name):
    from tools.mne_csd_reference_audit.legendre import g_function, h_function

    unit = MONTAGES[name]()
    n = unit.shape[0]
    cos = np.clip(unit @ unit.T, -1.0, 1.0)
    G = g_function(cos, 4.0, 50)
    H = h_function(cos, 4.0, 50)
    Gi = np.linalg.inv(G + LAMBDA2 * np.eye(n))
    ones = np.ones(n)
    Z = np.eye(n) - np.ones((n, n)) / n
    C = Gi @ Z - np.outer(Gi @ ones, (ones @ Gi @ Z) / (ones @ Gi @ ones))
    expected = H.T @ C / RADIUS**2
    actual = csd_operator(RADIUS * unit, radius=RADIUS, lambda2=LAMBDA2)
    np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-12 * _scale(expected))


@pytest.mark.parametrize("name", ALL)
def test_kkt_and_projection_match_the_mne_code_path_within_conditioning(name):
    # The package's projection form uses TC = Gi @ 1; MNE 1.13.2 uses TC = Gi.sum(0). They agree in exact
    # arithmetic (Gi is symmetric) and differ only by float64 asymmetry of the inverse. Bound: 10 * cond * eps.
    # Measured error / (cond * eps) is at most 0.88 here (ring_apex_9), so the bound has about an order of
    # magnitude of headroom and is not tuned to pass.
    pos = _positions(name)
    M_mne, G_reg = _mne_code_path(pos, RADIUS, LAMBDA2)
    bound = 10 * np.linalg.cond(G_reg) * np.finfo(float).eps
    for method in ("kkt", "projection"):
        M = csd_operator(pos, radius=RADIUS, lambda2=LAMBDA2, method=method)
        assert np.linalg.norm(M - M_mne) / np.linalg.norm(M_mne) <= bound, (method, name)


@pytest.mark.parametrize("variant", [csd_operator_regularised_after_inverse, csd_operator_without_sum_constraint])
@pytest.mark.parametrize("radius", [0.0, -0.095, float("nan"), float("inf")])
def test_discriminator_variants_refuse_invalid_radius_as_the_reference_does(variant, radius):
    # Regression: both variants once skipped the radius guard, so radius = 0 returned inf/nan with a warning.
    with pytest.raises(OperatorInputError, match="radius"):
        variant(_positions("tetrahedron_4"), radius=radius)


@pytest.mark.parametrize("stiffness", [-1.0, -0.5])
def test_negative_stiffness_is_refused_as_mne_refuses_it(stiffness):
    # MNE 1.13.2 _csd.py:130-131: "stiffness must be non-negative". Regression: the reference returned a
    # finite matrix for negative stiffness, so a parity check on such input would report agreement.
    with pytest.raises(OperatorInputError, match="stiffness"):
        csd_operator(_positions("tetrahedron_4"), radius=RADIUS, stiffness=stiffness)


@pytest.mark.parametrize("offset", [0.0, 1e-9])
def test_sensor_at_the_raw_origin_is_refused_as_mne_refuses_it(offset):
    # MNE 1.13.2 _csd.py:158 applies np.isclose(loc, 0).all(1) to the raw locations, before the sphere centre
    # is subtracted. Regression: a sensor at 1e-9 passed the post-centring check and was accepted.
    pos = np.vstack([_positions("tetrahedron_4"), [offset, offset, offset]])
    with pytest.raises(OperatorInputError, match="zero"):
        csd_operator(pos, radius=RADIUS)
