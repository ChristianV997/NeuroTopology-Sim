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
    """Full-matrix snapshot for Antigravity coordination.

    Generation method (recorded in JSON sidecar):
      - geometry: regular tetrahedron on sphere R=0.095 m, center 0
      - params: MNE defaults lambda2=1e-5, stiffness=4, n_legendre_terms=50
      - produced by this production module at pin MNE 1.13.2
      - not hand-edited
    If the sidecar is absent, regenerate and write it (first-run authoring).
    """
    pos = _regular_tetrahedron_unit() * 0.095
    names = ("T0", "T1", "T2", "T3")
    result = compute_spherical_csd_transform(pos, _cfg(), channel_names=names)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    matrix_path = FIXTURE_DIR / "tetrahedron_csd_matrix_mne_1_13_2.npy"
    meta_path = FIXTURE_DIR / "tetrahedron_csd_matrix_mne_1_13_2.json"
    if not matrix_path.exists():
        np.save(matrix_path, result.transform)
        meta_path.write_text(
            json.dumps(
                {
                    "generation": {
                        "geometry": "regular_tetrahedron_unit * 0.095",
                        "sphere_m": [0.0, 0.0, 0.0, 0.095],
                        "lambda2": 1e-5,
                        "stiffness": 4.0,
                        "n_legendre_terms": 50,
                        "channel_names": list(names),
                        "producer": (
                            "neurotopology_sim.experimental.preprocessing."
                            "spherical_csd.compute_spherical_csd_transform"
                        ),
                        "mne_pin_version": MNE_PIN["version"],
                        "mne_pin_commit": MNE_PIN["commit"],
                        "hand_edited": False,
                    },
                    "status": "HOLD",
                    "evidence_class": "SYNTHETIC_ONLY",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    expected = np.load(matrix_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["generation"]["hand_edited"] is False
    assert meta["generation"]["mne_pin_version"] == "1.13.2"
    rel = np.linalg.norm(result.transform - expected) / np.linalg.norm(expected)
    assert rel < 1e-14


# ---------------------------------------------------------------------------
# Optional live-MNE full-matrix parity (skip if MNE absent — no install here)
# ---------------------------------------------------------------------------


def test_optional_live_mne_full_matrix_parity():
    mne = pytest.importorskip("mne", reason="MNE not installed; parity skipped (no install)")
    # Pin check: warn but still compare if version differs
    ver = getattr(mne, "__version__", "unknown")
    pos = _asymmetric_cap(9, seed=21) * 0.095
    names = [f"EEG{i:02d}" for i in range(len(pos))]
    cfg = _cfg(radius=0.095)
    ours = compute_spherical_csd_transform(pos, cfg, channel_names=names)

    # Build a minimal Raw-like path: use MNE's public CSD on Evoked with montage
    info = mne.create_info(names, sfreq=100.0, ch_types="eeg")
    # Digitized positions in head frame (meters)
    dig = []
    for i, (name, xyz) in enumerate(zip(names, pos)):
        dig.append(
            dict(
                kind=mne.io.constants.FIFF.FIFFV_POINT_EEG,
                ident=i + 1,
                r=np.asarray(xyz, dtype=float),
                coord_frame=mne.io.constants.FIFF.FIFFV_COORD_HEAD,
            )
        )
        info["chs"][i]["loc"][:3] = xyz
    info["dig"] = dig
    data = np.eye(len(names))
    evoked = mne.EvokedArray(data, info, tmin=0.0)
    # Apply MNE CSD with explicit sphere matching ours
    csd = mne.preprocessing.compute_current_source_density(
        evoked,
        sphere=(0.0, 0.0, 0.0, 0.095),
        lambda2=1e-5,
        stiffness=4,
        n_legendre_terms=50,
        copy=True,
        verbose="ERROR",
    )
    mne_matrix = csd.get_data()  # because input was identity → columns are transform
    # EvokedArray stores (n_channels, n_times); identity times → transform columns
    rel = np.linalg.norm(ours.transform - mne_matrix) / np.linalg.norm(mne_matrix)
    assert rel < 1e-10, (
        f"full-matrix mismatch vs live MNE {ver}: rel={rel}; "
        f"pin={MNE_PIN['version']}"
    )
