"""Production tests for ``neurotopology_sim.experimental.preprocessing.spherical_csd``.

HOLD / SYNTHETIC_ONLY. Synthetic sensor geometries only. Fixtures below record
how they were generated. Antigravity Agent C owns independent conformance
fixtures — this file does not edit or replace those.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from neurotopology_sim.experimental.preprocessing.spherical_csd import (
    MNE_PIN,
    SphericalCSDConfig,
    SphericalCSDError,
    apply_spherical_csd,
    compute_spherical_csd_transform,
    _calc_g,
    _calc_h,
)

# ---------------------------------------------------------------------------
# Deterministic fixtures (generation recorded)
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _regular_tetrahedron_unit() -> np.ndarray:
    """Unit-sphere tetrahedron vertices (deterministic, closed form).

    Generation: standard regular tetrahedron centered at origin, then L2-
    normalized. Not a clinical montage. Radius scale applied by caller.
    """
    verts = np.array(
        [
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ],
        dtype=float,
    )
    verts /= np.linalg.norm(verts, axis=1, keepdims=True)
    return verts


def _asymmetric_cap(n: int = 8, seed: int = 0) -> np.ndarray:
    """Deterministic pseudo-random upper-hemisphere sensors (seeded RNG).

    Generation: ``numpy.random.default_rng(seed)`` → azimuth/elevation, convert
    to Cartesian, keep z > 0.1, normalize. Synthetic only.
    """
    rng = np.random.default_rng(seed)
    az = rng.uniform(0, 2 * np.pi, size=n)
    el = rng.uniform(0.15, np.pi / 2 - 0.05, size=n)
    x = np.cos(el) * np.cos(az)
    y = np.cos(el) * np.sin(az)
    z = np.sin(el)
    pos = np.column_stack([x, y, z])
    pos /= np.linalg.norm(pos, axis=1, keepdims=True)
    return pos


def _cfg(radius: float = 0.095, **kwargs) -> SphericalCSDConfig:
    return SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, radius), **kwargs)


# ---------------------------------------------------------------------------
# Pin / attribution
# ---------------------------------------------------------------------------


def test_mne_pin_records_version_and_commit():
    assert MNE_PIN["version"] == "1.13.2"
    assert MNE_PIN["commit"] == "bf67729b805865b5bb0f2f97621e416278efd1b2"
    assert MNE_PIN["license"] == "BSD-3-Clause"
    assert MNE_PIN["not_source_localization"] is True


def test_legendre_g_h_at_endpoints_match_mne_series_constants():
    """Parity of scalar G/H(1) and G/H(0) for N=50, m=4 (necessary, not sufficient).

    Expected values recomputed from the MNE 1.13.2 series formula using
    ``numpy.polynomial.legendre.legval`` — same evaluation path as production.
    Full-matrix parity is covered separately; four scalars alone are not a
    claim of operator parity.
    """
    g1 = float(_calc_g(np.array(1.0), stiffness=4.0, n_legendre_terms=50))
    g0 = float(_calc_g(np.array(0.0), stiffness=4.0, n_legendre_terms=50))
    h1 = float(_calc_h(np.array(1.0), stiffness=4.0, n_legendre_terms=50))
    h0 = float(_calc_h(np.array(0.0), stiffness=4.0, n_legendre_terms=50))
    # Published MNE-convention 50-term values (PR #402 / MNE series); abs tol 1e-15
    assert g1 == pytest.approx(0.01526076169706111, abs=1e-15)
    assert g0 == pytest.approx(-0.0001519196990505138, abs=1e-15)
    assert h1 == pytest.approx(0.03215834904306064, abs=1e-15)
    assert h0 == pytest.approx(-0.0008910623830223247, abs=1e-15)


# ---------------------------------------------------------------------------
# Validation / fail-closed
# ---------------------------------------------------------------------------


def test_rejects_sphere_auto_string():
    with pytest.raises(SphericalCSDError, match="explicit"):
        SphericalCSDConfig(sphere="auto").validated()  # type: ignore[arg-type]


def test_rejects_non_finite_positions():
    pos = _regular_tetrahedron_unit() * 0.095
    pos[0, 0] = np.nan
    with pytest.raises(SphericalCSDError, match="finite"):
        compute_spherical_csd_transform(pos, _cfg())


def test_rejects_zero_coordinates():
    pos = _regular_tetrahedron_unit() * 0.095
    pos[1] = 0.0
    with pytest.raises(SphericalCSDError, match="zero"):
        compute_spherical_csd_transform(pos, _cfg())


def test_rejects_sensor_at_origin_after_centering():
    pos = _regular_tetrahedron_unit() * 0.095
    # Place sphere center on a sensor
    c = tuple(pos[0]) + (0.095,)
    with pytest.raises(SphericalCSDError, match="origin"):
        compute_spherical_csd_transform(pos, SphericalCSDConfig(sphere=c))


def test_rejects_duplicate_channel_names():
    pos = _regular_tetrahedron_unit() * 0.095
    with pytest.raises(SphericalCSDError, match="unique"):
        compute_spherical_csd_transform(
            pos, _cfg(), channel_names=["a", "a", "b", "c"]
        )


def test_rejects_nearly_coincident_sensors():
    pos = _regular_tetrahedron_unit() * 0.095
    pos[1] = pos[0] + 1e-15
    with pytest.raises(SphericalCSDError, match="coincident"):
        compute_spherical_csd_transform(pos, _cfg(coincident_cos_tol=1e-12))


def test_rejects_bad_lambda2():
    with pytest.raises(SphericalCSDError, match="lambda2"):
        SphericalCSDConfig(sphere=(0, 0, 0, 0.1), lambda2=1.0).validated()


def test_rejects_non_positive_radius():
    with pytest.raises(SphericalCSDError, match="radius"):
        SphericalCSDConfig(sphere=(0, 0, 0, 0.0)).validated()


# ---------------------------------------------------------------------------
# Operator properties (MNE convention)
# ---------------------------------------------------------------------------


def test_transform_shape_and_channel_order():
    pos = _regular_tetrahedron_unit() * 0.095
    names = ("A", "B", "C", "D")
    result = compute_spherical_csd_transform(pos, _cfg(), channel_names=names)
    assert result.transform.shape == (4, 4)
    assert result.matrix is result.transform  # full N×N alias for parity suites
    assert result.channel_names == names
    assert result.output_unit == "V/m^2"
    assert result.diagnostics["channel_order"] == list(names)


def test_average_reference_null_vector():
    pos = _asymmetric_cap(10, seed=7) * 0.09
    result = compute_spherical_csd_transform(pos, _cfg(radius=0.09))
    null = result.transform @ np.ones(result.n_channels)
    assert np.max(np.abs(null)) < 1e-8


def test_inverse_square_radius_scaling():
    pos_unit = _asymmetric_cap(6, seed=1)
    r1, r2 = 0.08, 0.12
    m1 = compute_spherical_csd_transform(pos_unit * r1, _cfg(radius=r1)).transform
    m2 = compute_spherical_csd_transform(pos_unit * r2, _cfg(radius=r2)).transform
    # M ∝ 1/R^2 with identical angular geometry
    rel = np.linalg.norm(m1 * (r1**2) - m2 * (r2**2)) / np.linalg.norm(m1 * (r1**2))
    assert rel < 1e-12


def test_channel_permutation_equivariance():
    pos = _asymmetric_cap(7, seed=3) * 0.095
    names = [f"e{i}" for i in range(len(pos))]
    base = compute_spherical_csd_transform(pos, _cfg(), channel_names=names)
    perm = np.array([2, 0, 4, 1, 6, 3, 5])
    ppos = pos[perm]
    pnames = [names[i] for i in perm]
    permuted = compute_spherical_csd_transform(ppos, _cfg(), channel_names=pnames)
    # P M P^T
    P = np.eye(len(pos))[perm]
    expected = P @ base.transform @ P.T
    rel = np.linalg.norm(permuted.transform - expected) / np.linalg.norm(expected)
    assert rel < 1e-12


def test_apply_preserves_channel_axis_and_order():
    pos = _regular_tetrahedron_unit() * 0.095
    result = compute_spherical_csd_transform(pos, _cfg())
    rng = np.random.default_rng(11)
    data = rng.normal(size=(4, 32))
    out = apply_spherical_csd(result.transform, data)
    assert out.shape == data.shape
    np.testing.assert_allclose(out, result.transform @ data, atol=1e-12)
    # epoch axis
    epochs = rng.normal(size=(5, 4, 16))
    out_e = apply_spherical_csd(result.transform, epochs, channel_axis=1)
    assert out_e.shape == epochs.shape


def test_apply_rejects_channel_mismatch():
    pos = _regular_tetrahedron_unit() * 0.095
    result = compute_spherical_csd_transform(pos, _cfg())
    with pytest.raises(SphericalCSDError, match="channel count"):
        apply_spherical_csd(result.transform, np.zeros((3, 10)))


def test_full_matrix_snapshot_recorded_generation():
    """Full N×N tetrahedron parity against an independent MNE 1.13.2 fixture.

    Fixture provenance (JSON sidecar; not generated by this candidate):
      - matrix extracted from PR #419 ``tetrahedron_4`` reference, itself
        produced by live MNE-Python 1.13.2 ``compute_current_source_density``
        on identity data (BSD-3-Clause)
      - params: lambda2=1e-5, stiffness=4, n_legendre_terms=50, R=0.095 m
      - ``generated_by_candidate`` must be false
    Missing fixture files fail the test (no silent regeneration).
    """
    matrix_path = FIXTURE_DIR / "tetrahedron_csd_matrix_mne_1_13_2.npy"
    meta_path = FIXTURE_DIR / "tetrahedron_csd_matrix_mne_1_13_2.json"
    assert matrix_path.is_file(), f"missing independent fixture {matrix_path}"
    assert meta_path.is_file(), f"missing fixture provenance {meta_path}"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    gen = meta["generation"]
    assert gen.get("hand_edited") is False
    assert gen.get("generated_by_candidate") is False
    assert gen["mne_pin_version"] == "1.13.2"
    assert gen["mne_pin_commit"] == MNE_PIN["commit"]
    pos = np.asarray(gen["positions_m"], dtype=float)
    names = tuple(gen["channel_names"])
    sphere = tuple(float(x) for x in gen["sphere_m"])
    result = compute_spherical_csd_transform(
        pos, SphericalCSDConfig(sphere=sphere), channel_names=names
    )
    expected = np.load(matrix_path)
    rel = np.linalg.norm(result.transform - expected) / np.linalg.norm(expected)
    assert rel < 1e-9  # production gate vs independent MNE fixture


# ---------------------------------------------------------------------------
# Offline MNE-pin gate (no live importorskip — Round-6 treats skips as FAIL)
# Live MNE identity-matrix parity remains optional outside this candidate file;
# recorded fixtures + test_full_matrix_snapshot_recorded_generation are the
# CI-authoritative full-matrix check under HOLD / SYNTHETIC_ONLY.
# ---------------------------------------------------------------------------


def test_offline_mne_pin_fixture_is_ci_authoritative_gate():
    """Ensure the offline fixture gate exists so CI never needs pytest.skip."""
    matrix_path = FIXTURE_DIR / "tetrahedron_csd_matrix_mne_1_13_2.npy"
    meta_path = FIXTURE_DIR / "tetrahedron_csd_matrix_mne_1_13_2.json"
    assert matrix_path.is_file(), "missing recorded MNE 1.13.2 full-matrix fixture"
    assert meta_path.is_file(), "missing recorded MNE 1.13.2 fixture metadata"
    gen = json.loads(meta_path.read_text(encoding="utf-8"))
    assert gen["mne_pin_version"] == MNE_PIN["version"] == "1.13.2"
    assert gen["mne_pin_commit"] == MNE_PIN["commit"]
    # Production transform must still match the recorded pin fixture.
    pos = np.asarray(gen["positions_m"], dtype=float)
    names = list(gen["channel_names"])
    sphere = tuple(gen["sphere_xyzr_m"])
    result = compute_spherical_csd_transform(
        pos, SphericalCSDConfig(sphere=sphere), channel_names=names
    )
    expected = np.load(matrix_path)
    rel = np.linalg.norm(result.transform - expected) / np.linalg.norm(expected)
    assert rel < 1e-9
