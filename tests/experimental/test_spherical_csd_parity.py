"""Independent conformance tests for spherical-spline CSD transform.

Verifies the full N×N spherical Current Source Density (CSD) operator against
independent mathematical ground truth and pinned upstream reference fixtures
(MNE-Python 1.13.2 / Perrin et al. 1989).

Project Posture:
    HOLD / SYNTHETIC_ONLY.
    This is a sensor-space spatial transform (surface Laplacian).
    It is NOT anatomical source localization and does NOT validate biological
    mechanisms, consciousness, or clinical effects.

Attribution & Upstream Pin:
    - MNE-Python release: 1.13.2 (tag v1.13.2, commit bf67729b805865b5bb0f2f97621e416278efd1b2)
    - Algorithm sources: mne/preprocessing/_csd.py, mne/channels/interpolation.py
    - License: BSD-3-Clause
    - Mathematical formulation: Perrin et al. (1989), Electroencephalogr Clin Neurophysiol
      72(2):184–187; Corrigenda (1990) 76:565.
"""

from __future__ import annotations

import importlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from numpy.polynomial.legendre import legval
import pytest

# ---------------------------------------------------------------------------
# Dynamic import of Cursor Agent C production implementation
# ---------------------------------------------------------------------------

try:
    from neurotopology_sim.experimental.preprocessing.spherical_csd import (
        DEFAULT_LAMBDA2,
        DEFAULT_N_LEGENDRE_TERMS,
        DEFAULT_STIFFNESS,
        MNE_PIN,
        OUTPUT_UNIT_SI,
        SphericalCSDConfig,
        SphericalCSDError,
        SphericalCSDResult,
        apply_spherical_csd,
        compute_spherical_csd_transform,
    )

    HAS_PRODUCTION_CSD = True
except ImportError:
    HAS_PRODUCTION_CSD = False

# Live MNE check (optional integration only; never required for local pass)
try:
    import mne

    HAS_MNE = True
except ImportError:
    HAS_MNE = False

FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "spherical_csd_mne_1_13_2_reference.json"


# ---------------------------------------------------------------------------
# Independent Mathematical Oracle (Pure NumPy, Perrin et al. 1989 / MNE 1.13.2)
# ---------------------------------------------------------------------------


def independent_legendre_coeffs(stiffness: float, n_terms: int) -> tuple[np.ndarray, np.ndarray]:
    """Compute independent Legendre expansion coefficients c_G and c_H.

    c_G[n] = (2n + 1) / (4 * pi * (n * (n + 1))^m)
    c_H[n] = (2n + 1) / (4 * pi * (n * (n + 1))^(m - 1))
    for n = 1 .. n_terms, with c[0] = 0.
    """
    n = np.arange(1, n_terms + 1, dtype=float)
    cG = np.zeros(n_terms + 1, dtype=float)
    cH = np.zeros(n_terms + 1, dtype=float)
    cG[1:] = (2.0 * n + 1.0) / (4.0 * np.pi * (n * (n + 1.0)) ** stiffness)
    cH[1:] = (2.0 * n + 1.0) / (4.0 * np.pi * (n * (n + 1.0)) ** (stiffness - 1.0))
    return cG, cH


def independent_calc_g(cosines: np.ndarray, stiffness: float = 4.0, n_terms: int = 50) -> np.ndarray:
    """Evaluate G kernel independently via Legendre polynomials."""
    cG, _ = independent_legendre_coeffs(stiffness, n_terms)
    return legval(cosines, cG)


def independent_calc_h(cosines: np.ndarray, stiffness: float = 4.0, n_terms: int = 50) -> np.ndarray:
    """Evaluate H kernel independently via Legendre polynomials."""
    _, cH = independent_legendre_coeffs(stiffness, n_terms)
    return legval(cosines, cH)


def independent_compute_csd_matrix(
    positions: np.ndarray,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    radius: float = 0.095,
    stiffness: float = 4.0,
    n_legendre_terms: int = 50,
    lambda2: float = 1e-5,
) -> np.ndarray:
    """Compute the full N×N spherical CSD operator independently in pure NumPy.

    Matches MNE 1.13.2 projection-form spline solver:
        G_reg = G + lambda2 * I
        G_i = G_reg^-1
        TC = G_i @ 1
        sgi = 1^T G_i 1
        Z = I - (1/N) * 1 1^T
        C = G_i @ Z - (TC @ (1^T G_i Z)) / sgi
        M = (H^T @ C) / (radius^2)
    """
    pos = np.asarray(positions, dtype=float)
    centred = pos - np.asarray(origin, dtype=float)
    norms = np.linalg.norm(centred, axis=1, keepdims=True)
    unit = centred / norms
    cos = np.clip(unit @ unit.T, -1.0, 1.0)

    G = independent_calc_g(cos, stiffness=stiffness, n_terms=n_legendre_terms)
    H = independent_calc_h(cos, stiffness=stiffness, n_terms=n_legendre_terms)

    n = pos.shape[0]
    Greg = G + lambda2 * np.eye(n, dtype=float)
    Gi = np.linalg.inv(Greg)

    ones = np.ones((n, 1), dtype=float)
    TC = Gi @ ones
    sgi = float((ones.T @ TC)[0, 0])

    Z = np.eye(n, dtype=float) - (1.0 / float(n)) * np.ones((n, n), dtype=float)
    C = Gi @ Z - (TC @ (ones.T @ Gi @ Z)) / sgi
    M = (H.T @ C) / (float(radius) ** 2)
    return M


@pytest.fixture(scope="module")
def reference_fixtures() -> dict[str, Any]:
    """Load the verified reference fixtures."""
    assert FIXTURES_PATH.exists(), f"Reference fixture file missing: {FIXTURES_PATH}"
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 1. Pinned Upstream Attribution & Governance Checks
# ---------------------------------------------------------------------------


def test_mne_pin_attribution_metadata() -> None:
    """Verify pinned MNE release, source commit, and non-source-localization posture."""
    if not HAS_PRODUCTION_CSD:
        pytest.skip("Cursor C production spherical_csd.py not yet available on branch")

    assert MNE_PIN["version"] == "1.13.2"
    assert MNE_PIN["tag"] == "v1.13.2"
    assert MNE_PIN["commit"] == "bf67729b805865b5bb0f2f97621e416278efd1b2"
    assert MNE_PIN["license"] == "BSD-3-Clause"
    assert MNE_PIN["not_source_localization"] is True
    assert OUTPUT_UNIT_SI == "V/m^2"
    assert DEFAULT_LAMBDA2 == 1e-5
    assert DEFAULT_STIFFNESS == 4.0
    assert DEFAULT_N_LEGENDRE_TERMS == 50


# ---------------------------------------------------------------------------
# 2. Legendre Series Scalar Endpoint Parity
# ---------------------------------------------------------------------------


def test_legendre_series_scalar_constants() -> None:
    """Verify Legendre series endpoints at x=1 and x=0 against published MNE 1.13.2 constants."""
    g1 = float(independent_calc_g(np.array(1.0), stiffness=4.0, n_terms=50))
    g0 = float(independent_calc_g(np.array(0.0), stiffness=4.0, n_terms=50))
    h1 = float(independent_calc_h(np.array(1.0), stiffness=4.0, n_terms=50))
    h0 = float(independent_calc_h(np.array(0.0), stiffness=4.0, n_terms=50))

    # Published MNE 50-term series values (relative tolerance < 1e-14)
    assert math.isclose(g1, 0.01526076169706111, rel_tol=1e-14, abs_tol=1e-16)
    assert math.isclose(g0, -0.0001519196990505138, rel_tol=1e-14, abs_tol=1e-16)
    assert math.isclose(h1, 0.03215834904306064, rel_tol=1e-14, abs_tol=1e-16)
    assert math.isclose(h0, -0.0008910623830223247, rel_tol=1e-14, abs_tol=1e-16)


# ---------------------------------------------------------------------------
# 3. Complete N×N Transform Matrix Parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "montage_key,expected_n",
    [
        ("tetrahedron_4", 4),
        ("octahedron_6", 6),
        ("asymmetric_cap_8", 8),
        ("synthetic_cap_12", 12),
    ],
)
def test_full_matrix_parity_against_reference_fixtures(
    reference_fixtures: dict[str, Any],
    montage_key: str,
    expected_n: int,
) -> None:
    """Verify the COMPLETE N×N transform matrix against the pinned reference fixtures."""
    montage_data = reference_fixtures["montages"][montage_key]
    assert montage_data["n_channels"] == expected_n

    positions = np.array(montage_data["positions_m"], dtype=float)
    expected_M = np.array(montage_data["transform_matrix"], dtype=float)
    radius = float(montage_data["sphere_m"][3])

    # 1. Independent Oracle check
    oracle_M = independent_compute_csd_matrix(
        positions,
        origin=(0.0, 0.0, 0.0),
        radius=radius,
        stiffness=4.0,
        n_legendre_terms=50,
        lambda2=1e-5,
    )
    assert oracle_M.shape == (expected_n, expected_n)
    np.testing.assert_allclose(
        oracle_M,
        expected_M,
        rtol=1e-12,
        atol=1e-12,
        err_msg=f"Oracle vs reference fixture mismatch on {montage_key}",
    )

    # 2. Production implementation check (if available)
    if not HAS_PRODUCTION_CSD:
        return

    cfg = SphericalCSDConfig(
        sphere=(0.0, 0.0, 0.0, radius),
        stiffness=4.0,
        n_legendre_terms=50,
        lambda2=1e-5,
    )
    result = compute_spherical_csd_transform(positions, cfg)

    assert result.transform.shape == (expected_n, expected_n)
    assert result.output_unit == "V/m^2"
    np.testing.assert_allclose(
        result.transform,
        expected_M,
        rtol=1e-9,
        atol=1e-9,
        err_msg=f"Production vs reference fixture mismatch on {montage_key}",
    )


# ---------------------------------------------------------------------------
# 4. Discriminator Tests (Detection of Erroneous Formulation Variants)
# ---------------------------------------------------------------------------


def test_discriminator_stiffness_sensitivity() -> None:
    """Changing stiffness from m=4 to m=3 or m=5 must produce a significant parity failure."""
    pos = np.array(
        [
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ]
    ) * (0.095 / np.sqrt(3.0))

    M_m4 = independent_compute_csd_matrix(pos, stiffness=4.0)
    M_m3 = independent_compute_csd_matrix(pos, stiffness=3.0)
    M_m5 = independent_compute_csd_matrix(pos, stiffness=5.0)

    assert np.max(np.abs(M_m4 - M_m3)) > 1.0
    assert np.max(np.abs(M_m4 - M_m5)) > 1.0


def test_discriminator_truncation_sensitivity() -> None:
    """Changing truncation N from 50 to 30 or 100 must produce detectable matrix shifts."""
    pos = np.array(
        [
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ]
    ) * (0.095 / np.sqrt(3.0))

    M_50 = independent_compute_csd_matrix(pos, n_legendre_terms=50)
    M_30 = independent_compute_csd_matrix(pos, n_legendre_terms=30)
    assert np.max(np.abs(M_50 - M_30)) > 1e-4


def test_discriminator_lambda2_sensitivity() -> None:
    """Changing regularization lambda2 from 1e-5 to 1e-3 must produce significant matrix shifts."""
    pos = np.array(
        [
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ]
    ) * (0.095 / np.sqrt(3.0))

    M_1e5 = independent_compute_csd_matrix(pos, lambda2=1e-5)
    M_1e3 = independent_compute_csd_matrix(pos, lambda2=1e-3)
    assert np.max(np.abs(M_1e5 - M_1e3)) > 0.01


def test_discriminator_average_reference_constraint() -> None:
    """Omitting average-reference / zero-sum projection must be detected.

    An unconstrained spherical spline solver C = Gi lacks the zero-sum
    null-vector constraint (Perrin et al. 1989 Eq. 5). The true operator
    projects C = Gi - (TC @ (1^T Gi)) / sgi, which ensures M @ 1 = 0.
    Omitting this constraint yields a radically different matrix that fails
    constant potential annihilation.
    """
    rng = np.random.default_rng(0)
    az = rng.uniform(0, 2 * np.pi, size=7)
    el = rng.uniform(0.15, np.pi / 2 - 0.05, size=7)
    pos = np.column_stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    pos = pos / np.linalg.norm(pos, axis=1, keepdims=True) * 0.095

    # Standard operator with average-reference / zero-sum projection
    M_constrained = independent_compute_csd_matrix(pos)

    # Broken operator omitting the zero-sum constraint (C_unconstrained = Gi)
    centred = pos
    unit = centred / np.linalg.norm(centred, axis=1, keepdims=True)
    cos = np.clip(unit @ unit.T, -1.0, 1.0)
    G = independent_calc_g(cos, 4.0, 50)
    H = independent_calc_h(cos, 4.0, 50)
    n = 7
    Gi = np.linalg.inv(G + 1e-5 * np.eye(n))
    M_unconstrained = (H.T @ Gi) / (0.095**2)

    # Constrained operator annihilates constant potentials; unconstrained does not
    null_constrained = M_constrained @ np.ones(n)
    null_unconstrained = M_unconstrained @ np.ones(n)

    assert np.max(np.abs(null_constrained)) < 1e-9
    assert np.max(np.abs(null_unconstrained)) > 10.0
    assert np.max(np.abs(M_constrained - M_unconstrained)) > 10.0


# ---------------------------------------------------------------------------
# 5. Invariant Operator Properties
# ---------------------------------------------------------------------------


def test_constant_potential_annihilation_null_vector(reference_fixtures: dict[str, Any]) -> None:
    """The CSD matrix must annihilate constant potentials: M @ 1 == 0 to machine precision."""
    for key, montage in reference_fixtures["montages"].items():
        M = np.array(montage["transform_matrix"], dtype=float)
        n = montage["n_channels"]
        null_res = M @ np.ones(n)
        max_err = float(np.max(np.abs(null_res)))
        assert max_err < 1e-9, f"Constant potential annihilation failed on {key}: {max_err}"


def test_inverse_square_radius_scaling() -> None:
    """CSD matrix must scale strictly as 1 / R^2."""
    pos = np.array(
        [
            [1.0, 0.0, 0.0],
            [-1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0],
        ]
    )
    R1 = 0.095
    R2 = 0.190  # Exactly 2 * R1

    M1 = independent_compute_csd_matrix(pos * R1, radius=R1)
    M2 = independent_compute_csd_matrix(pos * R2, radius=R2)

    # M2 must be exactly (1 / 4) * M1
    np.testing.assert_allclose(M2, 0.25 * M1, rtol=1e-12, atol=1e-12)


def test_channel_permutation_equivariance() -> None:
    """Permuting sensor order P transforms the CSD matrix to P @ M @ P^T."""
    rng = np.random.default_rng(123)
    az = rng.uniform(0, 2 * np.pi, size=8)
    el = rng.uniform(0.15, np.pi / 2 - 0.05, size=8)
    pos = np.column_stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    pos = pos / np.linalg.norm(pos, axis=1, keepdims=True) * 0.095

    perm = np.array([3, 0, 7, 1, 6, 2, 5, 4])
    pos_perm = pos[perm]

    M_orig = independent_compute_csd_matrix(pos)
    M_perm = independent_compute_csd_matrix(pos_perm)

    # Permutation matrix P
    P = np.eye(8)[perm]
    M_expected_perm = P @ M_orig @ P.T

    np.testing.assert_allclose(M_perm, M_expected_perm, rtol=1e-8, atol=1e-8)


# ---------------------------------------------------------------------------
# 6. Deterministic Data Application
# ---------------------------------------------------------------------------


def test_apply_spherical_csd_2d_and_3d() -> None:
    """Test applying CSD matrix to deterministic multichannel sensor data in 2D and 3D."""
    if not HAS_PRODUCTION_CSD:
        pytest.skip("Cursor C production spherical_csd.py not yet available on branch")

    n_channels = 4
    n_times = 100
    n_epochs = 5

    # Random deterministic data
    rng = np.random.default_rng(42)
    data_2d = rng.normal(size=(n_channels, n_times))
    data_3d = rng.normal(size=(n_epochs, n_channels, n_times))

    # Tetrahedron transform
    verts = np.array(
        [
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ]
    ) * (0.095 / np.sqrt(3.0))
    cfg = SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095))
    res = compute_spherical_csd_transform(verts, cfg)
    T = res.transform

    # 1. 2D application (channel_axis = 0)
    csd_2d = apply_spherical_csd(T, data_2d, channel_axis=0)
    assert csd_2d.shape == (n_channels, n_times)
    np.testing.assert_allclose(csd_2d, T @ data_2d, rtol=1e-14, atol=1e-14)

    # 2. 3D application (channel_axis = 1)
    csd_3d = apply_spherical_csd(T, data_3d, channel_axis=1)
    assert csd_3d.shape == (n_epochs, n_channels, n_times)
    for ep in range(n_epochs):
        np.testing.assert_allclose(csd_3d[ep], T @ data_3d[ep], rtol=1e-14, atol=1e-14)


# ---------------------------------------------------------------------------
# 7. Fail-Closed Precondition Checks
# ---------------------------------------------------------------------------


def test_precondition_rejections() -> None:
    """Verify that malformed or degenerate sensor geometries fail closed."""
    if not HAS_PRODUCTION_CSD:
        pytest.skip("Cursor C production spherical_csd.py not yet available on branch")

    cfg = SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095))

    # 1. Coordinate (0, 0, 0)
    pos_zero = np.array([[0.0, 0.0, 0.0], [0.095, 0.0, 0.0], [0.0, 0.095, 0.0]])
    with pytest.raises(SphericalCSDError, match="zero .* sensor coordinate"):
        compute_spherical_csd_transform(pos_zero, cfg)

    # 2. Fewer than two channels
    pos_one = np.array([[0.095, 0.0, 0.0]])
    with pytest.raises(SphericalCSDError, match="at least two channels"):
        compute_spherical_csd_transform(pos_one, cfg)

    # 3. Duplicate coordinates
    pos_dup = np.array(
        [
            [0.095, 0.0, 0.0],
            [0.095, 0.0, 0.0],
            [0.0, 0.095, 0.0],
        ]
    )
    with pytest.raises(SphericalCSDError, match="nearly coincident sensors"):
        compute_spherical_csd_transform(pos_dup, cfg)

    # 4. Nearly coincident sensors (within 1e-12 cosine)
    pos_near = np.array(
        [
            [0.095, 0.0, 0.0],
            [0.095, 1e-10, 0.0],
            [0.0, 0.095, 0.0],
        ]
    )
    with pytest.raises(SphericalCSDError, match="nearly coincident sensors"):
        compute_spherical_csd_transform(pos_near, cfg)

    # 5. Non-finite coordinates
    pos_nan = np.array([[0.095, 0.0, np.nan], [0.0, 0.095, 0.0]])
    with pytest.raises(SphericalCSDError, match="must be finite"):
        compute_spherical_csd_transform(pos_nan, cfg)

    # 6. Channel name count mismatch
    pos_valid = np.array(
        [
            [0.095, 0.0, 0.0],
            [0.0, 0.095, 0.0],
            [0.0, 0.0, 0.095],
        ]
    )
    with pytest.raises(SphericalCSDError, match="channel_names length"):
        compute_spherical_csd_transform(pos_valid, cfg, channel_names=["C1", "C2"])

    # 7. Duplicate channel names
    with pytest.raises(SphericalCSDError, match="must be unique"):
        compute_spherical_csd_transform(pos_valid, cfg, channel_names=["C1", "C1", "C3"])


# ---------------------------------------------------------------------------
# 8. Optional Live MNE Integration
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_MNE, reason="Live MNE-Python not installed in environment")
def test_optional_live_mne_full_matrix_parity(reference_fixtures: dict[str, Any]) -> None:
    """Optional live integration test running against official MNE-Python compute_current_source_density."""
    montage_tet = reference_fixtures["montages"]["tetrahedron_4"]
    pos = np.array(montage_tet["positions_m"])
    ch_names = montage_tet["channel_names"]

    # Construct RawArray in MNE
    info = mne.create_info(ch_names=ch_names, sfreq=100.0, ch_types="eeg")
    data = np.eye(4)  # Identity data to extract the full N×N matrix
    raw = mne.io.RawArray(data, info)
    montage = mne.channels.make_dig_montage(
        ch_pos={name: pos[i] for i, name in enumerate(ch_names)},
        coord_frame="head",
    )
    raw.set_montage(montage)

    # Call official MNE CSD
    csd_raw = mne.preprocessing.compute_current_source_density(
        raw,
        sphere=(0.0, 0.0, 0.0, 0.095),
        stiffness=4.0,
        n_legendre_terms=50,
        lambda2=1e-5,
    )
    mne_M = csd_raw.get_data()

    expected_M = np.array(montage_tet["transform_matrix"])
    np.testing.assert_allclose(mne_M, expected_M, rtol=1e-7, atol=1e-7)
