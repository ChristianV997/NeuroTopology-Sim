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
import os
from pathlib import Path
import sys
from typing import Any, Mapping

import numpy as np
from numpy.polynomial.legendre import legval
import pytest

# ---------------------------------------------------------------------------
# Dynamic import of Cursor Agent C production implementation (PR #414)
# ---------------------------------------------------------------------------

# Locate candidate root if neurotopology_sim is not already on sys.path
if "neurotopology_sim" not in sys.modules:
    candidate_roots = [
        os.environ.get("CSD_CANDIDATE_PATH"),
        Path(__file__).resolve().parents[3] / "cursor-csd-production-d374",
        Path(__file__).resolve().parents[2],
        Path(__file__).resolve().parents[4] / "NeuroTopology-Sim",
    ]
    for root in candidate_roots:
        if root:
            root_path = Path(root)
            candidate_file = (
                root_path
                / "neurotopology_sim"
                / "experimental"
                / "preprocessing"
                / "spherical_csd.py"
            )
            if candidate_file.is_file():
                if str(root_path) not in sys.path:
                    sys.path.insert(0, str(root_path))
                break

try:
    from neurotopology_sim.experimental.preprocessing.spherical_csd import (
        DEFAULT_COINCIDENT_COS_TOL,
        DEFAULT_CONDITION_MAX,
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

FIXTURES_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "spherical_csd_mne_1_13_2_reference.json"
)


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


def test_mne_pin_attribution_metadata(reference_fixtures: dict[str, Any]) -> None:
    """Verify pinned MNE release, source commit, and non-source-localization posture."""
    prov = reference_fixtures["provenance"]
    assert prov["upstream_package"] == "mne-python"
    assert prov["pinned_version"] == "1.13.2"
    assert prov["pinned_tag"] == "v1.13.2"
    assert prov["pinned_commit"] == "bf67729b805865b5bb0f2f97621e416278efd1b2"
    assert prov["license"] == "BSD-3-Clause"
    assert prov["generator_status"] == "HOLD / SYNTHETIC_ONLY"
    assert prov["is_source_localization"] is False
    assert "Identity matrix data" in prov["generator_method"]

    if not HAS_PRODUCTION_CSD:
        pytest.skip("Candidate spherical_csd.py not available in environment")

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
# 3. Complete N×N Transform Matrix Parity (Frobenius & Entrywise)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "montage_key,expected_n",
    [
        ("tetrahedron_4", 4),
        ("octahedron_6", 6),
        ("asymmetric_cap_8", 8),
        ("synthetic_cap_12", 12),
        ("cap_20", 20),
        ("cap_64", 64),
    ],
)
def test_full_matrix_parity_against_reference_fixtures(
    reference_fixtures: dict[str, Any],
    montage_key: str,
    expected_n: int,
) -> None:
    """Verify the COMPLETE N×N transform matrix against the pinned reference fixtures.

    Includes full-matrix relative Frobenius norm evaluation with justified tolerance:
        rel_frob = ||M - M_ref||_F / ||M_ref||_F
    Tolerances:
        - Independent Oracle vs Fixture: rel_frob < 1e-12 (identical BLAS operations)
        - Production Candidate vs Fixture: rel_frob < 1e-9 (justified by float64
          BLAS matrix-vector product vs pairwise summation order difference <= 3e-13).
    """
    montage_data = reference_fixtures["montages"][montage_key]
    assert montage_data["n_channels"] == expected_n

    positions = np.array(montage_data["positions_m"], dtype=float)
    expected_M = np.array(montage_data["transform_matrix"], dtype=float)
    radius = float(montage_data["sphere_m"][3])
    frob_ref = float(np.linalg.norm(expected_M, "fro"))
    assert frob_ref > 0.0

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

    rel_frob_oracle = float(np.linalg.norm(oracle_M - expected_M, "fro") / frob_ref)
    assert rel_frob_oracle < 1e-12, (
        f"Oracle relative Frobenius error {rel_frob_oracle} on {montage_key}"
    )
    np.testing.assert_allclose(
        oracle_M,
        expected_M,
        rtol=1e-12,
        atol=1e-12,
        err_msg=f"Oracle vs reference fixture mismatch on {montage_key}",
    )

    # 2. Production candidate check
    if not HAS_PRODUCTION_CSD:
        pytest.skip("Candidate spherical_csd.py not available in environment")

    cfg = SphericalCSDConfig(
        sphere=(0.0, 0.0, 0.0, radius),
        stiffness=4.0,
        n_legendre_terms=50,
        lambda2=1e-5,
    )
    result = compute_spherical_csd_transform(positions, cfg)

    assert result.transform.shape == (expected_n, expected_n)
    assert result.output_unit == "V/m^2"
    # Verify .matrix alias exposed by candidate (commit 241b078)
    assert result.matrix is result.transform
    assert result.n_channels == expected_n

    rel_frob_prod = float(np.linalg.norm(result.transform - expected_M, "fro") / frob_ref)
    assert rel_frob_prod < 1e-9, (
        f"Production relative Frobenius error {rel_frob_prod} on {montage_key}"
    )
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
    """The CSD matrix must annihilate constant potentials: M @ 1 == 0 to machine precision.

    Evaluates both absolute ||M @ 1||_inf and relative ||M @ 1||_2 / (||M||_F * sqrt(N)),
    and verifies with non-unit constant fields (e.g. c = 42.0 * 1).
    """
    for key, montage in reference_fixtures["montages"].items():
        M = np.array(montage["transform_matrix"], dtype=float)
        n = montage["n_channels"]
        frob_M = float(np.linalg.norm(M, "fro"))

        # 1. Unit constant field
        null_res = M @ np.ones(n)
        max_err = float(np.max(np.abs(null_res)))
        assert max_err < 1e-9, f"Constant potential annihilation failed on {key}: {max_err}"

        rel_null = float(np.linalg.norm(null_res) / (frob_M * np.sqrt(n)))
        assert rel_null < 1e-11, f"Relative null residual failed on {key}: {rel_null}"

        # 2. Arbitrary constant field (c = 42.0)
        c_field = 42.0 * np.ones(n)
        c_res = M @ c_field
        assert np.max(np.abs(c_res)) < 1e-7

    # Also test production candidate directly if available
    if HAS_PRODUCTION_CSD:
        montage_tet = reference_fixtures["montages"]["tetrahedron_4"]
        pos = np.array(montage_tet["positions_m"])
        cfg = SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095))
        res = compute_spherical_csd_transform(pos, cfg)
        prod_null = res.transform @ np.ones(4)
        assert np.max(np.abs(prod_null)) < 1e-9


def test_inverse_square_radius_scaling() -> None:
    """CSD matrix must scale strictly as 1 / R^2 when sphere radius doubles."""
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

    # 1. Independent Oracle test
    M1 = independent_compute_csd_matrix(pos * R1, radius=R1)
    M2 = independent_compute_csd_matrix(pos * R2, radius=R2)

    # M2 must be exactly (1 / 4) * M1
    np.testing.assert_allclose(M2, 0.25 * M1, rtol=1e-12, atol=1e-12)
    rel_frob_scale = float(np.linalg.norm(M2 - 0.25 * M1, "fro") / np.linalg.norm(M1, "fro"))
    assert rel_frob_scale < 1e-12

    # 2. Production candidate test
    if HAS_PRODUCTION_CSD:
        cfg1 = SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, R1))
        cfg2 = SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, R2))
        res1 = compute_spherical_csd_transform(pos * R1, cfg1)
        res2 = compute_spherical_csd_transform(pos * R2, cfg2)
        np.testing.assert_allclose(res2.transform, 0.25 * res1.transform, rtol=1e-12, atol=1e-12)


def test_channel_permutation_equivariance() -> None:
    """Permuting sensor order P transforms the CSD matrix to P @ M @ P^T."""
    rng = np.random.default_rng(123)
    az = rng.uniform(0, 2 * np.pi, size=8)
    el = rng.uniform(0.15, np.pi / 2 - 0.05, size=8)
    pos = np.column_stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    pos = pos / np.linalg.norm(pos, axis=1, keepdims=True) * 0.095

    perm = np.array([3, 0, 7, 1, 6, 2, 5, 4])
    pos_perm = pos[perm]

    # Permutation matrix P
    P = np.eye(8)[perm]

    # 1. Independent Oracle test
    M_orig = independent_compute_csd_matrix(pos)
    M_perm = independent_compute_csd_matrix(pos_perm)
    M_expected_perm = P @ M_orig @ P.T

    np.testing.assert_allclose(M_perm, M_expected_perm, rtol=1e-8, atol=1e-8)
    rel_frob_perm = float(np.linalg.norm(M_perm - M_expected_perm, "fro") / np.linalg.norm(M_orig, "fro"))
    assert rel_frob_perm < 1e-8

    # 2. Production candidate test
    if HAS_PRODUCTION_CSD:
        cfg = SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095))
        res_orig = compute_spherical_csd_transform(pos, cfg)
        res_perm = compute_spherical_csd_transform(pos_perm, cfg)
        np.testing.assert_allclose(
            res_perm.transform, P @ res_orig.transform @ P.T, rtol=1e-8, atol=1e-8
        )


# ---------------------------------------------------------------------------
# 6. Deterministic Data Application & Bad / Dropped Channel Behavior
# ---------------------------------------------------------------------------


def test_apply_spherical_csd_2d_and_3d() -> None:
    """Test applying CSD matrix to deterministic multichannel sensor data in 2D and 3D."""
    if not HAS_PRODUCTION_CSD:
        pytest.skip("Candidate spherical_csd.py not available in environment")

    n_channels = 4
    n_times = 100
    n_epochs = 5

    rng = np.random.default_rng(42)
    data_2d = rng.normal(size=(n_channels, n_times))
    data_3d = rng.normal(size=(n_epochs, n_channels, n_times))

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


def test_bad_and_dropped_channel_behavior() -> None:
    """Test behavior when sensors/channels are marked bad or dropped."""
    if not HAS_PRODUCTION_CSD:
        pytest.skip("Candidate spherical_csd.py not available in environment")

    # Start with 6-channel octahedron
    pos_6 = np.array(
        [
            [0.095, 0.0, 0.0],
            [-0.095, 0.0, 0.0],
            [0.0, 0.095, 0.0],
            [0.0, -0.095, 0.0],
            [0.0, 0.0, 0.095],
            [0.0, 0.0, -0.095],
        ]
    )
    names_6 = ["O1", "O2", "O3", "O4", "O5", "O6"]
    cfg = SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095))
    res_6 = compute_spherical_csd_transform(pos_6, cfg, channel_names=names_6)
    assert res_6.transform.shape == (6, 6)

    # 1. Applying 6-channel operator to dropped-channel data (5 channels) must fail closed
    bad_data = np.ones((5, 50))
    with pytest.raises((SphericalCSDError, ValueError)):
        apply_spherical_csd(res_6.transform, bad_data, channel_axis=0)

    # 2. Dropping bad channel (e.g. index 2: O3) before computing transform
    good_mask = [True, True, False, True, True, True]
    pos_5 = pos_6[good_mask]
    names_5 = [n for i, n in enumerate(names_6) if good_mask[i]]

    res_5 = compute_spherical_csd_transform(pos_5, cfg, channel_names=names_5)
    assert res_5.transform.shape == (5, 5)
    assert res_5.channel_names == tuple(names_5)

    # The reduced operator must satisfy all invariants
    null_5 = res_5.transform @ np.ones(5)
    assert np.max(np.abs(null_5)) < 1e-9

    # Applying to 5-channel data succeeds
    data_5 = np.ones((5, 50))
    out_5 = apply_spherical_csd(res_5.transform, data_5, channel_axis=0)
    assert out_5.shape == (5, 50)
    assert np.max(np.abs(out_5)) < 1e-9  # Annihilates constant data


# ---------------------------------------------------------------------------
# 7. Fail-Closed Precondition Checks
# ---------------------------------------------------------------------------


def test_precondition_rejections() -> None:
    """Verify that malformed or degenerate sensor geometries fail closed."""
    if not HAS_PRODUCTION_CSD:
        pytest.skip("Candidate spherical_csd.py not available in environment")

    cfg = SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095))

    # 1. Coordinate (0, 0, 0)
    pos_zero = np.array([[0.0, 0.0, 0.0], [0.095, 0.0, 0.0], [0.0, 0.095, 0.0]])
    with pytest.raises(SphericalCSDError, match="zero .* sensor coordinate"):
        compute_spherical_csd_transform(pos_zero, cfg)

    # 2. Fewer than two channels (N=1)
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

    # 5. Non-finite coordinates (NaN and Inf)
    pos_nan = np.array([[0.095, 0.0, np.nan], [0.0, 0.095, 0.0]])
    with pytest.raises(SphericalCSDError, match="must be finite"):
        compute_spherical_csd_transform(pos_nan, cfg)

    pos_inf = np.array([[0.095, 0.0, np.inf], [0.0, 0.095, 0.0]])
    with pytest.raises(SphericalCSDError, match="must be finite"):
        compute_spherical_csd_transform(pos_inf, cfg)

    # 6. Invalid positions shape (1D or 3D)
    pos_1d = np.array([0.095, 0.0, 0.0])
    with pytest.raises(SphericalCSDError, match="shape"):
        compute_spherical_csd_transform(pos_1d, cfg)

    # 7. Channel name count mismatch
    pos_valid = np.array(
        [
            [0.095, 0.0, 0.0],
            [0.0, 0.095, 0.0],
            [0.0, 0.0, 0.095],
        ]
    )
    with pytest.raises(SphericalCSDError, match="channel_names length"):
        compute_spherical_csd_transform(pos_valid, cfg, channel_names=["C1", "C2"])

    # 8. Duplicate channel names
    with pytest.raises(SphericalCSDError, match="must be unique"):
        compute_spherical_csd_transform(pos_valid, cfg, channel_names=["C1", "C1", "C3"])

    # 9. Zero radius
    with pytest.raises(SphericalCSDError, match="radius must be > 0"):
        compute_spherical_csd_transform(pos_valid, SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.0)))

    # 10. Negative radius
    with pytest.raises(SphericalCSDError, match="radius must be > 0"):
        compute_spherical_csd_transform(pos_valid, SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, -0.095)))

    # 11. Non-finite sphere parameter
    with pytest.raises(SphericalCSDError, match="must be finite"):
        compute_spherical_csd_transform(pos_valid, SphericalCSDConfig(sphere=(0.0, 0.0, np.nan, 0.095)))

    # 12. String sphere ("auto" rejected)
    with pytest.raises(SphericalCSDError, match="explicit .* tuple"):
        compute_spherical_csd_transform(pos_valid, SphericalCSDConfig(sphere="auto"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 8. Conditioning and Regularization Dynamics
# ---------------------------------------------------------------------------


def test_conditioning_and_regularization_behavior() -> None:
    """Test conditioning checks and lambda2 regularization bounds."""
    if not HAS_PRODUCTION_CSD:
        pytest.skip("Candidate spherical_csd.py not available in environment")

    pos_valid = np.array(
        [
            [0.095, 0.0, 0.0],
            [-0.095, 0.0, 0.0],
            [0.0, 0.095, 0.0],
            [0.0, -0.095, 0.0],
        ]
    )

    # 1. Invalid lambda2: negative or >= 1.0
    with pytest.raises(SphericalCSDError, match="0 <= lambda2 < 1"):
        compute_spherical_csd_transform(
            pos_valid, SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095), lambda2=-1e-5)
        )

    with pytest.raises(SphericalCSDError, match="0 <= lambda2 < 1"):
        compute_spherical_csd_transform(
            pos_valid, SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095), lambda2=1.5)
        )

    # 2. Invalid condition_max (<= 0)
    with pytest.raises(SphericalCSDError, match="condition_max must be positive"):
        compute_spherical_csd_transform(
            pos_valid, SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095), condition_max=0.0)
        )

    # 3. Ill-conditioned geometry detection: condition_max threshold
    # Set condition_max very low to trigger fail-closed threshold
    with pytest.raises(SphericalCSDError, match="ill-conditioned"):
        compute_spherical_csd_transform(
            pos_valid, SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095), condition_max=1.0)
        )

    # 4. Monotonic conditioning improvement with lambda2
    res_small_reg = compute_spherical_csd_transform(
        pos_valid, SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095), lambda2=1e-7)
    )
    res_large_reg = compute_spherical_csd_transform(
        pos_valid, SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095), lambda2=1e-2)
    )
    cond_small = float(res_small_reg.diagnostics["cond_G_reg"])
    cond_large = float(res_large_reg.diagnostics["cond_G_reg"])
    assert cond_large < cond_small, (
        f"Increasing lambda2 must reduce condition number: {cond_large} vs {cond_small}"
    )


# ---------------------------------------------------------------------------
# 9. Optional Live MNE Integration
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not HAS_MNE,
    reason=(
        "Live MNE-Python not installed in environment; "
        "live parity gate blocked in this environment (reproducible commands provided)"
    ),
)
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
    frob_ref = float(np.linalg.norm(expected_M, "fro"))
    rel_frob_mne = float(np.linalg.norm(mne_M - expected_M, "fro") / frob_ref)
    assert rel_frob_mne < 1e-9
    np.testing.assert_allclose(mne_M, expected_M, rtol=1e-7, atol=1e-7)
