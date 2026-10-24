from __future__ import annotations

import numpy as np
import pytest

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


# Regression (2026-10-21, #402 lane): commit 6f7175db removed the upper bound and accepted lambda2 = 1.0 and 2.0. The
# pinned MNE 1.13.2 refuses them: `if not 0 <= lambda2 < 1: raise ValueError` (mne/preprocessing/_csd.py L126-127).
# The reference must refuse the same domain, and NaN / inf fall outside it too.
@pytest.mark.parametrize("lambda2", [-1e-9, 1.0, 2.0, float("nan"), float("inf"), -float("inf")])
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
def test_kkt_and_projection_match_the_mne_code_path_within_conditioning(name, mne_code_path_oracle):
    # The package's projection form uses TC = Gi @ 1; MNE 1.13.2 uses TC = Gi.sum(0). They agree in exact
    # arithmetic (Gi is symmetric) and differ only by float64 asymmetry of the inverse. Bound: 10 * cond * eps.
    # Measured error / (cond * eps) is at most 0.88 here (ring_apex_9), so the bound has about an order of
    # magnitude of headroom and is not tuned to pass.
    pos = _positions(name)
    M_mne, G_reg = mne_code_path_oracle(pos, RADIUS, LAMBDA2)
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


def test_apply_csd_refuses_data_with_more_than_two_axes():
    # Regression (2026-10-23, post-merge audit of #402): data of shape (n, n, k) passed the row check, and
    # M @ data then broadcast over the first axis, so a result that is not the channel-wise product was
    # returned with no error.
    M = csd_operator(_positions("tetrahedron_4"), radius=RADIUS)
    with pytest.raises(OperatorInputError, match="axes"):
        apply_csd(M, np.ones((4, 4, 3)))


ONE_AXIS = np.ones(4)


@pytest.mark.parametrize(
    "operator",
    [ONE_AXIS, np.ones((4, 4, 4)), np.ones((4, 3)), [[1.0] * 4] * 4 + [[1.0] * 3], np.full((4, 4), np.nan)],
    ids=["one_axis", "three_axes", "not_square", "ragged_list", "non_finite"],
)
def test_apply_csd_refuses_an_operator_that_is_not_a_finite_square_matrix(operator):
    # Regression (2026-10-23, QA re-probe of the #402 follow-up): apply_csd checked data but not M. A 1-D M
    # returned a scalar dot product with no error; a 3-D M returned a (4, 4, k) array; a list raised
    # AttributeError and a non-square M raised ValueError instead of OperatorInputError.
    with pytest.raises(OperatorInputError, match="operator"):
        apply_csd(operator, np.ones(4) if operator is ONE_AXIS else np.ones((4, 5)))


def test_origin_must_be_three_finite_coordinates():
    # Regression (2026-10-23, post-merge audit of #402): an (n_channels, 3) origin was broadcast row by row as
    # a per-sensor centre, and a finite operator was returned with no error. MNE takes a single sphere centre.
    pos = _positions("tetrahedron_4")
    per_sensor = np.random.default_rng(0).normal(scale=0.01, size=pos.shape)
    with pytest.raises(OperatorInputError, match="origin"):
        csd_operator(pos, radius=RADIUS, origin=per_sensor)


@pytest.mark.parametrize("value", [True, False, np.True_, np.False_])
@pytest.mark.parametrize("name", ["stiffness", "lambda2"])
def test_bool_stiffness_and_lambda2_are_refused_as_mne_refuses_them(name, value):
    # Regression (2026-10-23, post-merge audit of #402): MNE 1.13.2 checks both with _validate_type(..., "numeric")
    # (_csd.py:125 and :129). "numeric" is (np.floating, float, int_like), and int_like uses _ensure_int, which
    # raises TypeError for bool (mne/utils/check.py L25-37, L585-596, L616). The reference returned a finite
    # operator, with False read as 0 and True as 1, so the same class of fix #402 made for n_legendre_terms.
    with pytest.raises(TypeError, match=name):
        csd_operator(_positions("tetrahedron_4"), radius=RADIUS, **{name: value})
