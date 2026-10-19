"""Public-contract tests for physics.eeg_forward (PR #418 candidate). HOLD / SYNTHETIC_ONLY.

Every test imports the candidate directly. Nothing is mocked, skipped, or copied from the implementation.
Expected values are either analytic (dimensional scaling, the centre identity, homogeneous closed forms) or
black-box properties (monotone pass/fail sets, invariances). The tests make no empirical or biological claim.

Plan, one group per section below:
  1. Direct import resolves to the candidate file; exported names and error hierarchy are exact.
  2. Input forms: sequences, arrays, integer-valued and numpy-integer inputs are accepted; bad degrees rejected.
  3. Output shapes, dtypes, types, determinism, finite values, and input immutability.
  4. Domain: non-finite, wrong-shape, and out-of-domain sources, moments, sensors, geometry, and tolerances.
  5. Degenerate cases: zero dipole, source at the centre (degree-1 identity).
  6. Orientation: radial, tangential, and mixed superposition; pole symmetry; sign convention; rotation.
  7. Units and scaling: length (inverse square), conductivity (inverse), moment (linear).
  8. Truncation and tolerance: monotone pass/fail sets in max_degree, tail_tol, residual_tol; deep-source refusal.
  9. Vectorisation: batch equals one-at-a-time, except the pole-refusal characterization in section 8, which
     records an open owner question; order permutation; duplicates.

Known uncovered, recorded rather than hidden, with mutation evidence at candidate e316933:
- the scalp zero-current residual gate: round-off, never binding in any geometry tried, so no input exposes it;
- the interface potential terms: no sampled geometry let them set the potential diagnostic without the brain-side
  check dominating the current diagnostic;
- the overflow transfer guard: in the thin-brain case the residual clause refuses with the same message, so removing
  the transfer clause alone is masked;
- the shell-condition NaN guard: no tested input produces a NaN shell condition;
- the non-finite potential guard: no tested input reaches it.
The interface flux terms are covered by test_interface_flux_terms_are_gated_through_the_current_diagnostic.
Documented risk, not a test failure: the tail estimate underestimates the true tail below about L = 63 on the PR's own
sample, so a loose tail_tol at small max_degree can accept a result with error above that tolerance.

Not duplicated here. PR #409's oracle covers the seven-equation boundary-value solve, the coefficient-by-coefficient
sweep, and the P10 tail fixture. Module-level helpers outside the package exports (naess2017_table1_geometry) are
excluded: their conductivity provenance is unresolved in the PR docs.
"""
from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import numpy as np
import pytest

import physics.eeg_forward as package
from physics.eeg_forward import (
    DEFAULT_MAX_DEGREE,
    DEFAULT_RESIDUAL_TOL,
    DEFAULT_TAIL_TOL,
    FourSphereError,
    FourSphereGeometry,
    FourSphereInputError,
    FourSphereQualityError,
    FourSphereResult,
    forward_potentials,
    transfer_ratios,
)
from physics.eeg_forward import four_sphere as candidate_module

REPO_ROOT = Path(__file__).resolve().parents[2]
R_LAYERED = (0.079, 0.080, 0.085, 0.090)
R1, R4 = R_LAYERED[0], R_LAYERED[3]
SIG_LAYERED = (0.33, 1.79, 0.0042, 0.33)
SIG_HOMOGENEOUS = (0.33, 0.33, 0.33, 0.33)
SIG_ASYMMETRIC = (0.33, 1.79, 0.0042, 0.6)  # scalp differs from brain, so a prefactor on the wrong shell is visible
LAYERED = FourSphereGeometry(R_LAYERED, SIG_LAYERED)
HOMOGENEOUS = FourSphereGeometry(R_LAYERED, SIG_HOMOGENEOUS)
ASYMMETRIC = FourSphereGeometry(R_LAYERED, SIG_ASYMMETRIC)
GEOMETRIES = pytest.mark.parametrize("geometry", [LAYERED, HOMOGENEOUS], ids=["layered", "homogeneous"])
SOURCE_AXIAL = (0.0, 0.0, 0.04)            # d / r4 = 0.44
SOURCE_OBLIQUE = (0.02, -0.03, 0.035)      # d / r4 = 0.56
MOMENT = (1e-9, -2e-9, 0.5e-9)
RADIAL_Z = (0.0, 0.0, 1e-9)
_REL = 1e-12


# ── helpers ──────────────────────────────────────────────────────────────────

def _sensors(seed: int, n: int = 8) -> np.ndarray:
    pts = np.random.default_rng(seed).normal(size=(n, 3))
    return R4 * pts / np.linalg.norm(pts, axis=1, keepdims=True)


def _values(geometry, source, moment, sensors, max_degree=128, **kwargs) -> np.ndarray:
    return forward_potentials(geometry, source, moment, sensors, max_degree=max_degree, **kwargs).potentials_v


def _scale(values) -> float:
    return float(np.max(np.abs(values)))


def _assert_close(actual, expected, *, scale, rel=_REL):
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=rel * scale)


def _unit(vector) -> np.ndarray:
    vector = np.asarray(vector, dtype=float)
    return vector / np.linalg.norm(vector)


def _perpendicular(axis) -> np.ndarray:
    return _unit(np.cross(axis, [0.3, -0.5, 0.8]))


def _rotation(seed: int) -> np.ndarray:
    q, r = np.linalg.qr(np.random.default_rng(seed).normal(size=(3, 3)))
    q = q * np.sign(np.diag(r))
    return q * np.sign(np.linalg.det(q))


def _to_tuples(value):
    return tuple(_to_tuples(item) for item in value) if isinstance(value, list) else value


def _as_form(values, form: str):
    array = np.asarray(values, dtype=float)
    if form == "ndarray":
        return array
    if form == "list":
        return array.tolist()
    return _to_tuples(array.tolist())


def _passes(callable_) -> bool:
    try:
        callable_()
    except FourSphereQualityError:
        return False
    return True


# ── 1. direct import and public surface ──────────────────────────────────────

def test_direct_import_resolves_to_the_candidate_source_file():
    assert Path(candidate_module.__file__).resolve() == REPO_ROOT / "physics" / "eeg_forward" / "four_sphere.py"


def test_package_exports_exactly_the_documented_public_names():
    assert set(package.__all__) == {
        "DEFAULT_MAX_DEGREE", "DEFAULT_RESIDUAL_TOL", "DEFAULT_TAIL_TOL",
        "FourSphereError", "FourSphereGeometry", "FourSphereInputError", "FourSphereQualityError",
        "FourSphereResult", "forward_potentials", "transfer_ratios",
    }
    for name in ("forward_potentials", "transfer_ratios"):
        assert callable(getattr(package, name))
    for name in ("FourSphereError", "FourSphereGeometry", "FourSphereInputError",
                 "FourSphereQualityError", "FourSphereResult"):
        assert isinstance(getattr(package, name), type)
    assert isinstance(package.DEFAULT_MAX_DEGREE, int)


def test_error_classes_form_a_value_error_hierarchy():
    assert issubclass(FourSphereError, ValueError)
    assert issubclass(FourSphereInputError, FourSphereError)
    assert issubclass(FourSphereQualityError, FourSphereError)


def test_documented_defaults_are_used_when_options_are_omitted():
    assert (DEFAULT_MAX_DEGREE, DEFAULT_RESIDUAL_TOL, DEFAULT_TAIL_TOL) == (256, 1e-9, 1e-10)
    sensors = _sensors(1)
    implicit = forward_potentials(LAYERED, SOURCE_AXIAL, MOMENT, sensors)
    explicit = forward_potentials(LAYERED, SOURCE_AXIAL, MOMENT, sensors, max_degree=DEFAULT_MAX_DEGREE,
                                  residual_tol=DEFAULT_RESIDUAL_TOL, tail_tol=DEFAULT_TAIL_TOL)
    assert implicit.max_degree == DEFAULT_MAX_DEGREE
    np.testing.assert_array_equal(implicit.potentials_v, explicit.potentials_v)


def test_public_signature_defaults_match_the_documented_values():
    parameters = inspect.signature(forward_potentials).parameters
    assert parameters["max_degree"].default == DEFAULT_MAX_DEGREE
    assert parameters["residual_tol"].default == DEFAULT_RESIDUAL_TOL
    assert parameters["tail_tol"].default == DEFAULT_TAIL_TOL


def test_geometry_is_an_immutable_value_object():
    with pytest.raises(dataclasses.FrozenInstanceError):
        LAYERED.radii_m = (0.1, 0.2, 0.3, 0.4)


# ── 2. accepted input forms ──────────────────────────────────────────────────

@pytest.mark.parametrize("form", ["list", "tuple", "ndarray"])
def test_geometry_accepts_sequence_and_array_forms(form):
    geometry = FourSphereGeometry(_as_form(R_LAYERED, form), _as_form(SIG_LAYERED, form))
    assert geometry.radii_m == R_LAYERED
    assert geometry.conductivities_sm == SIG_LAYERED
    assert all(type(value) is float for value in geometry.radii_m + geometry.conductivities_sm)


@pytest.mark.parametrize("form", ["list", "tuple", "ndarray"])
def test_source_moment_and_sensor_forms_give_identical_potentials(form):
    sensors = _sensors(2)
    reference = _values(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors)
    got = _values(LAYERED, _as_form(SOURCE_OBLIQUE, form), _as_form(MOMENT, form), _as_form(sensors, form))
    np.testing.assert_array_equal(got, reference)


def test_integer_valued_source_and_moment_match_the_centre_identity():
    sensors = _sensors(3)
    t1 = transfer_ratios(LAYERED, 1)[0]
    expected = t1 * (sensors[:, 2] / R4) / (4.0 * np.pi * SIG_LAYERED[0] * R4**2)
    _assert_close(_values(LAYERED, (0, 0, 0), (0, 0, 1), sensors, max_degree=64), expected, scale=_scale(expected))


@pytest.mark.parametrize("degree", [64, np.int64(64), np.int32(64)])
def test_integer_like_max_degree_is_accepted(degree):
    result = forward_potentials(LAYERED, SOURCE_AXIAL, MOMENT, _sensors(4), max_degree=degree)
    assert result.max_degree == 64
    assert result.transfer_ratios.shape == (64,)


@pytest.mark.parametrize("degree", [True, False, 4.0, "64", None, 0, -1, 513])
def test_invalid_max_degree_values_are_rejected(degree):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, SOURCE_AXIAL, MOMENT, _sensors(5), max_degree=degree)


# ── 3. outputs: shape, types, finiteness, determinism, immutability ──────────

def test_output_shapes_dtypes_and_types_are_stable():
    result = forward_potentials(LAYERED, SOURCE_OBLIQUE, MOMENT, _sensors(6, n=5), max_degree=96)
    assert isinstance(result, FourSphereResult)
    assert result.potentials_v.shape == (5,) and result.potentials_v.dtype == np.float64
    assert result.transfer_ratios.shape == (96,) and result.transfer_ratios.dtype == np.float64
    assert type(result.max_degree) is int and result.max_degree == 96
    assert isinstance(result.diagnostics, dict)
    assert all(isinstance(value, float) for value in result.diagnostics.values())


def test_transfer_ratio_prefix_is_independent_of_the_requested_length():
    np.testing.assert_array_equal(transfer_ratios(LAYERED, 8), transfer_ratios(LAYERED, 16)[:8])


@GEOMETRIES
@pytest.mark.parametrize("source", [(0.0, 0.0, 0.0), (0.0, 0.0, 0.03), SOURCE_OBLIQUE], ids=["centre", "axial", "oblique"])
def test_outputs_are_finite_over_sources_and_moment_types(geometry, source):
    sensors = _sensors(7, n=16)
    axis = _unit(source) if any(source) else np.array([0.0, 0.0, 1.0])
    radial = tuple(float(v) for v in 1e-9 * axis)
    tangential = tuple(float(v) for v in 1e-9 * _perpendicular(axis))
    for moment in (radial, tangential, MOMENT):
        assert np.all(np.isfinite(_values(geometry, source, moment, sensors, max_degree=96)))


def test_repeated_calls_are_bitwise_identical():
    first = _values(LAYERED, SOURCE_OBLIQUE, MOMENT, _sensors(8))
    second = _values(LAYERED, SOURCE_OBLIQUE, MOMENT, _sensors(8))
    np.testing.assert_array_equal(first, second)


def test_inputs_are_not_mutated_by_the_call():
    sensors = _sensors(9)
    before = sensors.copy()
    moment = np.array(MOMENT, dtype=float)
    source = np.array(SOURCE_OBLIQUE, dtype=float)
    source_before = source.copy()
    forward_potentials(LAYERED, source, moment, sensors, max_degree=96)
    np.testing.assert_array_equal(sensors, before)
    np.testing.assert_array_equal(moment, np.array(MOMENT))
    np.testing.assert_array_equal(source, source_before)


# ── 4. domain rejection ──────────────────────────────────────────────────────

@pytest.mark.parametrize("source", [
    [float("nan"), 0.0, 0.0],
    [0.0, float("inf"), 0.0],
    [0.01, 0.0],
    [[0.01, 0.0, 0.0], [0.0, 0.0, 0.0]],
], ids=["nan", "inf", "wrong-length", "batched"])
def test_malformed_source_is_rejected(source):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, source, MOMENT, _sensors(10))


@pytest.mark.parametrize("moment", [[float("inf"), 0.0, 0.0], [float("nan"), 0.0, 0.0], [1.0, 2.0],
                                    [[1e-9, 0.0, 0.0], [0.0, 0.0, 0.0]]],
                         ids=["inf", "nan", "wrong-length", "batched"])
def test_malformed_moment_is_rejected(moment):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, SOURCE_OBLIQUE, moment, _sensors(11))


@pytest.mark.parametrize("depth_factor", [1.0, 1.0 + 1e-12, 1.5])
def test_source_on_or_beyond_the_brain_boundary_is_rejected(depth_factor):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, (0.0, 0.0, R1 * depth_factor), RADIAL_Z, _sensors(12))


def test_source_strictly_inside_the_brain_is_accepted():
    values = _values(LAYERED, (0.0, 0.0, 0.5 * R1), RADIAL_Z, _sensors(13), max_degree=128)
    assert np.all(np.isfinite(values))


@pytest.mark.parametrize("scale", [1.0 + 1e-6, 1.0 - 1e-6, 0.5, 2.0])
def test_sensors_off_the_scalp_are_rejected(scale):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, SOURCE_OBLIQUE, MOMENT, _sensors(14) * scale)


@pytest.mark.parametrize("scale, accepted", [(1.0 + 5e-10, True), (1.0 + 2e-9, False)],
                         ids=["inside-1e-9", "outside-1e-9"])
def test_surface_tolerance_brackets_the_documented_relative_limit(scale, accepted):
    # Docs: sensors lie on r = r4 within relative tolerance 1e-9. The bracket sits at half and twice that limit.
    sensors = _sensors(15) * scale
    if accepted:
        assert np.all(np.isfinite(_values(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors, max_degree=96)))
    else:
        with pytest.raises(FourSphereInputError):
            forward_potentials(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors)


@pytest.mark.parametrize("sensors", [
    np.zeros((0, 3)),
    np.zeros((4, 2)),
    np.array([0.0, 0.0, R4]),
    np.vstack([_sensors(16)[:1], [[float("nan"), 0.0, 0.0]]]),
    np.zeros((2, 3)),
], ids=["empty", "shape-n2", "flat", "nan", "origin"])
def test_malformed_sensors_are_rejected(sensors):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors)


@pytest.mark.parametrize("radii, sigmas", [
    ((0.080, 0.079, 0.085, 0.090), (0.33,) * 4),
    ((0.079, 0.079, 0.085, 0.090), (0.33,) * 4),
    ((0.0, 0.080, 0.085, 0.090), (0.33,) * 4),
    ((-0.079, 0.080, 0.085, 0.090), (0.33,) * 4),
    ((0.079, 0.080, 0.085, float("nan")), (0.33,) * 4),
    ((0.079, 0.080, 0.085, 1.5), (0.33,) * 4),
    ((0.079, 0.080, 0.085), (0.33,) * 4),
    ((0.079, 0.080, 0.085, 0.090), (0.33, 0.33, 0.33)),
    ((0.079, 0.080, 0.085, 0.090), (9.9999e-5, 0.33, 0.33, 0.33)),
    ((0.079, 0.080, 0.085, 0.090), (0.33, 0.33, 0.33, 10.0001)),
    ((0.079, 0.080, 0.085, 0.090), (0.33, float("inf"), 0.33, 0.33)),
])
def test_invalid_geometry_is_rejected(radii, sigmas):
    with pytest.raises(FourSphereInputError):
        FourSphereGeometry(radii, sigmas)


def test_conductivity_bounds_are_inclusive():
    FourSphereGeometry(R_LAYERED, (1e-4,) * 4)
    FourSphereGeometry(R_LAYERED, (10.0,) * 4)


def test_radius_floor_is_one_tenth_of_a_millimetre():
    # Docs: each radius is at least 1e-4 m, below which radius powers underflow.
    FourSphereGeometry((1e-4, 2e-4, 3e-4, 4e-4), (0.33,) * 4)
    with pytest.raises(FourSphereInputError):
        FourSphereGeometry((9e-5, 2e-4, 3e-4, 4e-4), (0.33,) * 4)


def test_invalid_input_types_raise_the_library_error_not_a_type_error():
    # Docs: invalid geometry, source, sensor, degree, or tolerance raises FourSphereInputError (a ValueError).
    sensors = _sensors(38)
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors, residual_tol=True)
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors, tail_tol="1e-10")
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors, residual_tol=1j)
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors.astype(complex))
    with pytest.raises(FourSphereInputError):
        FourSphereGeometry(("0.079", "0.080", "0.085", "0.090"), (0.33,) * 4)


def test_overflow_for_a_thin_brain_is_refused_as_a_quality_error_not_returned():
    # Docs (quality gates): overflow for extreme radius ratios is reported as a quality error. With a 1 mm brain
    # inside a 90 mm head, the degree-79 transfer ratio overflows, so the call must refuse.
    thin = FourSphereGeometry((0.001, 0.002, 0.003, 0.090), (0.33,) * 4)
    with pytest.raises(FourSphereQualityError, match="non-finite transfer ratio"):
        forward_potentials(thin, (0.0, 0.0, 0.0005), (0.0, 0.0, 1e-9), _sensors(37, n=3), max_degree=128)


@pytest.mark.parametrize("kwargs", [
    {"residual_tol": 0.0}, {"residual_tol": -1e-9}, {"residual_tol": float("nan")}, {"residual_tol": float("inf")},
    {"tail_tol": 0.0}, {"tail_tol": -1e-10}, {"tail_tol": float("nan")}, {"tail_tol": float("inf")},
])
def test_invalid_tolerances_are_rejected(kwargs):
    with pytest.raises(FourSphereInputError):
        forward_potentials(LAYERED, SOURCE_OBLIQUE, MOMENT, _sensors(17), **kwargs)


# ── 5. degenerate cases ──────────────────────────────────────────────────────

@pytest.mark.parametrize("source", [SOURCE_AXIAL, (0.0, 0.0, 0.0)], ids=["axial", "centre"])
def test_zero_dipole_gives_exact_zero_potentials_including_at_the_poles(source):
    poles = np.array([[0.0, 0.0, R4], [0.0, 0.0, -R4]])
    sensors = np.vstack([_sensors(18, n=4), poles])
    values = _values(LAYERED, source, (0.0, 0.0, 0.0), sensors)
    np.testing.assert_array_equal(values, np.zeros(len(sensors)))


@pytest.mark.parametrize("geometry", [ASYMMETRIC, HOMOGENEOUS], ids=["asymmetric", "homogeneous"])
def test_source_at_the_centre_reduces_to_the_degree_one_term(geometry):
    sensors = _sensors(19)
    moment = np.array(MOMENT)
    t1 = transfer_ratios(geometry, 1)[0]
    expected = t1 * (sensors @ moment) / R4 / (4.0 * np.pi * geometry.conductivities_sm[0] * R4**2)
    _assert_close(_values(geometry, (0.0, 0.0, 0.0), MOMENT, sensors, max_degree=64), expected,
                  scale=_scale(expected))


# ── 6. orientation, pole symmetry, sign, rotation ────────────────────────────

@GEOMETRIES
def test_moment_split_is_linear_and_both_parts_are_nonzero(geometry):
    # Linearity only. The radial/tangential split itself is pinned by the centre identity, the pole closed
    # forms, and the generating-function test below.
    axis = _unit(SOURCE_OBLIQUE)
    moment = np.array(MOMENT)
    radial = (moment @ axis) * axis
    tangential = moment - radial
    sensors = _sensors(20)
    whole = _values(geometry, SOURCE_OBLIQUE, moment, sensors)
    radial_part = _values(geometry, SOURCE_OBLIQUE, radial, sensors)
    tangential_part = _values(geometry, SOURCE_OBLIQUE, tangential, sensors)
    assert _scale(radial_part) > 0.0 and _scale(tangential_part) > 0.0
    _assert_close(radial_part + tangential_part, whole, scale=_scale(whole))


@GEOMETRIES
@pytest.mark.parametrize("source", [SOURCE_AXIAL, SOURCE_OBLIQUE], ids=["axial", "oblique"])
def test_tangential_dipole_has_no_pole_value(geometry, source):
    axis = _unit(source)
    tangential = _perpendicular(axis) * 1e-9
    poles = np.vstack([R4 * axis, -R4 * axis])
    batch = _values(geometry, source, tangential, np.vstack([poles, _sensors(21)]))
    assert np.all(np.abs(batch[:2]) <= _REL * _scale(batch[2:]))


def test_poles_only_tangential_query_returns_exact_zeros_when_the_envelope_underflows():
    # Docs (pole behaviour): if the envelope at degree L underflows to zero, the call returns exact zeros. At a depth
    # ratio of 0.02 the degree-256 envelope is below the float range, so the call is accepted, not refused.
    tangential = _perpendicular(np.array([0.0, 0.0, 1.0])) * 1e-9
    poles = np.array([[0.0, 0.0, R4], [0.0, 0.0, -R4]])
    values = _values(LAYERED, (0.0, 0.0, 0.02 * R4), tangential, poles, max_degree=256)
    np.testing.assert_array_equal(values, np.zeros(2))


@GEOMETRIES
def test_poles_only_tangential_query_is_refused_as_documented(geometry):
    # PR #418 docs: a zero signal has an undefined tail estimate, so the call is refused, not valued.
    axis = np.array([0.0, 0.0, 1.0])
    tangential = _perpendicular(axis) * 1e-9
    poles = np.array([[0.0, 0.0, R4], [0.0, 0.0, -R4]])
    with pytest.raises(FourSphereQualityError, match="truncation tail"):
        _values(geometry, (0.0, 0.0, 0.04), tangential, poles)


def test_pole_refusal_depends_on_the_batch_it_is_evaluated_in():
    # Recorded as observed behaviour for the owner to decide, not as a settled contract. The tail scale is taken
    # over the whole call. Alone, the pole is refused. With a general sensor in the same call, the pole value is zero.
    tangential = _perpendicular(np.array([0.0, 0.0, 1.0])) * 1e-9
    pole = np.array([[0.0, 0.0, R4]])
    with pytest.raises(FourSphereQualityError, match="truncation tail"):
        _values(LAYERED, (0.0, 0.0, 0.04), tangential, pole)
    batch = _values(LAYERED, (0.0, 0.0, 0.04), tangential, np.vstack([pole, _sensors(36, n=2)]))
    assert abs(batch[0]) <= _REL * _scale(batch[1:])


@GEOMETRIES
def test_radial_dipole_is_positive_toward_its_pole_for_sources_on_either_side(geometry):
    poles = np.array([[0.0, 0.0, R4], [0.0, 0.0, -R4]])
    for z in (0.04, -0.04):
        toward, away = _values(geometry, (0.0, 0.0, z), RADIAL_Z, poles)
        assert toward > 0.0 > away


@GEOMETRIES
def test_tangential_dipole_is_positive_on_the_side_it_points_toward(geometry):
    sensors = np.array([[R4, 0.0, 0.0], [-R4, 0.0, 0.0]])
    toward, away = _values(geometry, SOURCE_AXIAL, (1e-9, 0.0, 0.0), sensors)
    assert toward > 0.0 > away


def test_homogeneous_transfer_ratios_are_two_l_plus_one_over_l():
    degrees = np.arange(1, 65)
    np.testing.assert_allclose(transfer_ratios(HOMOGENEOUS, 64), (2 * degrees + 1) / degrees, rtol=1e-12, atol=0)


@pytest.mark.parametrize("depth", [0.03, 0.05])
def test_homogeneous_potential_matches_the_documented_generating_function_forms(depth):
    # Docs (homogeneous limit), with t = d/r4, mu = e_s.e, D = 1 - 2 t mu + t^2:
    #   A = sum_l (2l+1) t^(l-1) P_l(mu)    = ((1 - t^2) D^(-3/2) - 1) / t
    #   B = sum_l (2l+1)/l t^(l-1) P_l'(mu) = 2 D^(-3/2) + ((t - mu)/sqrt(D) + mu) / (t (1 - mu^2))
    #   V = (q_r A + (q.e - q_r mu) B) / (4 pi sigma r4^2)
    # Generic sensors keep mu away from the poles, where the closed form's 1/(1 - mu^2) loses accuracy.
    t = depth / R4
    axis = np.array([0.0, 0.0, 1.0])
    moment = np.array(MOMENT)
    e = _sensors(35, n=6) / R4
    mu = e @ axis
    q_r = float(moment @ axis)
    d_factor = 1.0 - 2.0 * t * mu + t * t
    a_term = ((1.0 - t * t) * d_factor ** -1.5 - 1.0) / t
    b_term = 2.0 * d_factor ** -1.5 + ((t - mu) / np.sqrt(d_factor) + mu) / (t * (1.0 - mu * mu))
    expected = (q_r * a_term + (e @ moment - q_r * mu) * b_term) / (4.0 * np.pi * SIG_HOMOGENEOUS[0] * R4**2)
    got = _values(HOMOGENEOUS, (0.0, 0.0, depth), MOMENT, _sensors(35, n=6), max_degree=128)
    _assert_close(got, expected, scale=_scale(expected), rel=1e-9)


@pytest.mark.parametrize("depth", [0.02, 0.04, 0.06])
def test_homogeneous_radial_pole_values_match_the_closed_form(depth):
    # Analytic: sum_l (2l+1) P_l(+-1) t^(l-1) = ((1 +- t)/(1 -+ t)^2 - 1)/t with t = d/r4.
    t = depth / R4
    poles = np.array([[0.0, 0.0, R4], [0.0, 0.0, -R4]])
    got = _values(HOMOGENEOUS, (0.0, 0.0, depth), RADIAL_Z, poles)
    prefactor = 1e-9 / (4.0 * np.pi * SIG_HOMOGENEOUS[0] * R4**2)
    expected = prefactor * np.array([((1 + t) / (1 - t) ** 2 - 1) / t, ((1 - t) / (1 + t) ** 2 - 1) / t])
    _assert_close(got, expected, scale=_scale(expected))


@GEOMETRIES
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_rotating_source_moment_and_sensors_together_is_invariant(geometry, seed):
    rot = _rotation(seed)
    sensors = _sensors(22)
    base = _values(geometry, SOURCE_OBLIQUE, MOMENT, sensors)
    rotated = _values(geometry, rot @ np.array(SOURCE_OBLIQUE), rot @ np.array(MOMENT), sensors @ rot.T)
    _assert_close(rotated, base, scale=_scale(base))


@GEOMETRIES
def test_rotating_sensors_alone_changes_the_output(geometry):
    sensors = _sensors(22)
    base = _values(geometry, SOURCE_OBLIQUE, MOMENT, sensors)
    moved = _values(geometry, SOURCE_OBLIQUE, MOMENT, sensors @ _rotation(4).T)
    assert _scale(moved - base) > 1e-3 * _scale(base)


# ── 7. units and scaling ─────────────────────────────────────────────────────

@pytest.mark.parametrize("lam", [0.5, 2.0, 4.0])
def test_length_scaling_gives_inverse_square_potentials(lam):
    scaled_geometry = FourSphereGeometry(tuple(lam * r for r in R_LAYERED), SIG_LAYERED)
    sensors = _sensors(23)
    base = _values(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors)
    scaled = _values(scaled_geometry, tuple(lam * np.array(SOURCE_OBLIQUE)), MOMENT, lam * sensors)
    _assert_close(scaled, base / lam**2, scale=_scale(base))


@pytest.mark.parametrize("factor", [0.5, 2.5])
def test_uniform_conductivity_scaling_gives_inverse_potentials(factor):
    scaled_geometry = FourSphereGeometry(R_LAYERED, tuple(factor * s for s in SIG_ASYMMETRIC))
    sensors = _sensors(24)
    base = _values(ASYMMETRIC, SOURCE_OBLIQUE, MOMENT, sensors)
    scaled = _values(scaled_geometry, SOURCE_OBLIQUE, MOMENT, sensors)
    _assert_close(scaled * factor, base, scale=_scale(base))


@pytest.mark.parametrize("factor", [-1.0, 3.0, 1e-3])
def test_moment_scaling_is_linear(factor):
    sensors = _sensors(25)
    base = _values(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors)
    scaled = _values(LAYERED, SOURCE_OBLIQUE, tuple(factor * np.array(MOMENT)), sensors)
    _assert_close(scaled, factor * base, scale=_scale(base))


# ── 8. truncation and tolerance controls (black-box) ─────────────────────────

@pytest.mark.parametrize("degree", [1, 2, 4, 8])
def test_a_few_legendre_terms_are_refused_at_a_moderate_depth(degree):
    with pytest.raises(FourSphereQualityError, match="truncation tail"):
        _values(LAYERED, SOURCE_AXIAL, MOMENT, _sensors(26), max_degree=degree)


def test_max_degree_pass_set_is_upward_closed_and_mixed():
    pattern = [_passes(lambda degree=d: _values(LAYERED, SOURCE_AXIAL, MOMENT, _sensors(27), max_degree=degree))
               for d in (1, 2, 4, 8, 16, 32, 64, 128, 256)]
    assert pattern == sorted(pattern)
    assert True in pattern and False in pattern


def test_tail_tolerance_pass_set_is_upward_closed_and_mixed():
    grid = (1e-300, 1e-100, 1e-30, 1e-12, 1e-10, 1e-6, 1e-2, 1.0, 1e3)
    pattern = [_passes(lambda t=t: _values(LAYERED, SOURCE_AXIAL, MOMENT, _sensors(28), max_degree=128, tail_tol=t))
               for t in grid]
    assert pattern == sorted(pattern)
    assert True in pattern and False in pattern


def test_residual_tolerance_pass_set_is_upward_closed_and_mixed():
    grid = (1e-30, 1e-20, 1e-16, 1e-15, 1e-14, 1e-9)
    pattern = [_passes(lambda t=t: _values(LAYERED, SOURCE_AXIAL, MOMENT, _sensors(29), max_degree=128,
                                           residual_tol=t)) for t in grid]
    assert pattern == sorted(pattern)
    assert True in pattern and False in pattern


def test_interface_potential_residual_is_gated_on_its_own():
    # The diagnostic keys are the candidate's own names. The PR docs describe the residuals in prose but do not
    # write these keys, so a rename breaks this test loudly. At this extreme conductivity contrast the
    # interface-potential residual dominates the other two.
    geometry = FourSphereGeometry((0.06931, 0.07318, 0.0736, 0.0809), (0.0004, 5.2088, 0.0365, 0.0199))
    sensors = np.array([[0.0, 0.0, 0.0809]])
    source, moment = (0.0, 0.0, 0.01), (0.0, 0.0, 1e-9)
    diag = forward_potentials(geometry, source, moment, sensors, max_degree=32,
                              residual_tol=1.0, tail_tol=1.0).diagnostics
    potential = diag["interface_potential_residual"]
    others = max(diag["interface_current_residual"], diag["scalp_zero_current_residual"])
    assert others < potential / 100.0
    with pytest.raises(FourSphereQualityError, match="residuals"):
        forward_potentials(geometry, source, moment, sensors, max_degree=32,
                           residual_tol=float(np.sqrt(potential * others)), tail_tol=1.0)


def test_current_diagnostic_is_gated_on_its_own():
    # Geometry where the current diagnostic dominates. The diagnostic includes the brain-side check, which sets it
    # here. The flux-term test below isolates the interface flux terms. The scalp zero-current residual sits at round-off
    # in every geometry tried and never binds, so its gate cannot be isolated through the public API.
    geometry = FourSphereGeometry((0.06359, 0.08362, 0.08843, 0.08857), (1.9365, 1.472e-4, 0.4449, 7.556e-4))
    sensors = np.array([[0.0, 0.0, 0.08857]])
    source, moment = (0.0, 0.0, 0.02), (0.0, 0.0, 1e-9)
    diag = forward_potentials(geometry, source, moment, sensors, max_degree=24,
                              residual_tol=1.0, tail_tol=1.0).diagnostics
    current = diag["interface_current_residual"]
    others = max(diag["interface_potential_residual"], diag["scalp_zero_current_residual"])
    assert others < current / 100.0
    with pytest.raises(FourSphereQualityError, match="residuals"):
        forward_potentials(geometry, source, moment, sensors, max_degree=24,
                           residual_tol=float(np.sqrt(others * current)), tail_tol=1.0)


def test_interface_flux_terms_are_gated_through_the_current_diagnostic():
    # Geometry found by search where the interface flux terms set the current diagnostic. With those terms zeroed,
    # the value falls about 15-fold, to the brain-side check alone. The potential and scalp residuals sit below both,
    # so a tolerance between them isolates the flux terms.
    geometry = FourSphereGeometry((0.0668662837, 0.0675861033, 0.0696360706, 0.0740530917),
                                  (0.032970468, 0.485646134, 0.000429393995, 0.000256329215))
    sensors = np.array([[0.0, 0.0, 0.0740530917]])
    source, moment = (0.0, 0.0, 0.5 * 0.0668662837), (0.0, 0.0, 1e-9)
    diag = forward_potentials(geometry, source, moment, sensors, max_degree=24,
                              residual_tol=1.0, tail_tol=1.0).diagnostics
    current = diag["interface_current_residual"]
    others = max(diag["interface_potential_residual"], diag["scalp_zero_current_residual"])
    assert 2.0 * others < current
    with pytest.raises(FourSphereQualityError, match="residuals"):
        forward_potentials(geometry, source, moment, sensors, max_degree=24,
                           residual_tol=float(np.sqrt(others * current)), tail_tol=1.0)


def test_converged_potentials_do_not_change_with_further_terms():
    sensors = _sensors(30)
    short = _values(LAYERED, SOURCE_AXIAL, MOMENT, sensors, max_degree=64)
    mid = _values(LAYERED, SOURCE_AXIAL, MOMENT, sensors, max_degree=128)
    long = _values(LAYERED, SOURCE_AXIAL, MOMENT, sensors, max_degree=256)
    _assert_close(short, long, scale=_scale(long), rel=1e-9)
    _assert_close(mid, long, scale=_scale(long), rel=1e-9)


def test_deep_source_is_refused_at_low_degree_and_accepted_at_high_degree():
    deep = (0.0, 0.0, 0.87 * R4)
    with pytest.raises(FourSphereQualityError, match="truncation tail"):
        _values(LAYERED, deep, RADIAL_Z, _sensors(31), max_degree=16)
    assert np.all(np.isfinite(_values(LAYERED, deep, RADIAL_Z, _sensors(31), max_degree=256)))


# ── 9. vectorisation ─────────────────────────────────────────────────────────

def test_documented_tail_diagnostics_are_reported():
    # Docs (truncation): tail_certified is always 0. tail_validated_range is 1 only for max_degree >= 64.
    sensors = _sensors(39)
    for degree, validated in ((32, 0.0), (64, 1.0)):
        diag = forward_potentials(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors, max_degree=degree, tail_tol=1.0).diagnostics
        assert diag["tail_certified"] == 0.0
        assert diag["tail_validated_range"] == validated


@pytest.mark.parametrize("moment", [MOMENT, (0.0, 0.0, 1e-9), (1e-9, 0.0, 0.0)],
                         ids=["mixed", "radial", "tangential"])
def test_tail_estimate_matches_the_documented_envelope_extrapolation(moment):
    # Docs (truncation section): envelope_l = |T_l| t^(l-1) (l|q_r| + l(l+1)/2 |q_t|) / (4 pi sigma1 r4^2). The dropped
    # tail is env_L r / (1 - r), with r = env_L / env_(L-1), relative to the largest sensor potential. The refusal
    # boundary must sit within 2 percent of that value: refused at 0.98x, accepted at 1.02x. Radial-only and
    # tangential-only moments give each envelope term a large share, so removing either term is visible.
    degrees = 32
    sensors = _sensors(27)
    depth = float(np.linalg.norm(SOURCE_AXIAL))
    axis = _unit(SOURCE_AXIAL)
    moment = np.array(moment, dtype=float)
    q_r = float(moment @ axis)
    q_t = float(np.linalg.norm(moment - q_r * axis))
    degree = np.arange(1, degrees + 1)
    envelope = (np.abs(transfer_ratios(LAYERED, degrees)) * (depth / R4) ** (degree - 1)
                * (degree * abs(q_r) + degree * (degree + 1) / 2.0 * q_t)
                / (4.0 * np.pi * SIG_LAYERED[0] * R4**2))
    ratio = envelope[-1] / envelope[-2]
    peak = _scale(_values(LAYERED, SOURCE_AXIAL, moment, sensors, max_degree=degrees, tail_tol=1.0))
    expected = envelope[-1] * ratio / (1.0 - ratio) / peak
    with pytest.raises(FourSphereQualityError, match="truncation tail"):
        _values(LAYERED, SOURCE_AXIAL, moment, sensors, max_degree=degrees, tail_tol=0.98 * expected)
    _values(LAYERED, SOURCE_AXIAL, moment, sensors, max_degree=degrees, tail_tol=1.02 * expected)


def test_batch_equals_one_sensor_at_a_time():
    sensors = _sensors(32)
    batch = _values(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors)
    single = np.concatenate([_values(LAYERED, SOURCE_OBLIQUE, MOMENT, row[None]) for row in sensors])
    _assert_close(batch, single, scale=_scale(batch), rel=1e-13)


def test_output_permutes_with_sensor_order():
    sensors = _sensors(33, n=6)
    order = np.array([4, 1, 5, 0, 3, 2])
    base = _values(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors)
    _assert_close(_values(LAYERED, SOURCE_OBLIQUE, MOMENT, sensors[order]), base[order], scale=_scale(base))


def test_duplicate_sensors_give_duplicate_outputs():
    sensors = _sensors(34, n=3)
    doubled = np.vstack([sensors, sensors[:1]])
    values = _values(LAYERED, SOURCE_OBLIQUE, MOMENT, doubled)
    np.testing.assert_array_equal(values[-1], values[0])
