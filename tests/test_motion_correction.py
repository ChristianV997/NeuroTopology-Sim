"""Offline tests for tools/motion_correction.py's lightweight centroid-drift motion proxy.

No network, no real BOLD data -- a tiny synthetic 4D NIfTI with a known, deliberately
shifted "hot spot" is enough to check the centroid math and FD/scrub logic in isolation.
"""
from __future__ import annotations

import numpy as np
import pytest

nib = pytest.importorskip("nibabel")

from tools.motion_correction import (  # noqa: E402
    _center_of_mass_world,
    _rms_framewise_displacement,
    estimate_motion_lightweight,
    get_or_compute_motion,
    scrub_mask,
)


def _make_bold(shifts: list[tuple[int, int, int]], dim: int = 12) -> nib.Nifti1Image:
    """4D volume where each frame has a single bright voxel offset by `shifts[t]` from center."""
    T = len(shifts)
    data = np.zeros((dim, dim, dim, T), dtype=np.float32)
    center = dim // 2
    for t, (dx, dy, dz) in enumerate(shifts):
        data[center + dx, center + dy, center + dz, t] = 1000.0
    return nib.Nifti1Image(data, affine=np.eye(4))  # identity affine: voxel mm == world mm


def test_center_of_mass_world_tracks_a_shifted_hotspot():
    img = _make_bold([(0, 0, 0), (2, 0, 0)])
    data = np.asanyarray(img.dataobj)
    com0 = _center_of_mass_world(data[..., 0], img.affine)
    com1 = _center_of_mass_world(data[..., 1], img.affine)
    assert np.allclose(com1 - com0, [2, 0, 0], atol=1e-6)


def test_center_of_mass_falls_back_to_affine_origin_for_empty_volume():
    data = np.zeros((4, 4, 4), dtype=np.float32)
    affine = np.eye(4)
    affine[:3, 3] = [1.0, 2.0, 3.0]
    com = _center_of_mass_world(data, affine)
    assert np.allclose(com, [1.0, 2.0, 3.0])


def test_estimate_motion_lightweight_zero_for_static_run(tmp_path):
    img = _make_bold([(0, 0, 0)] * 5)
    path = tmp_path / "static.nii.gz"
    nib.save(img, str(path))

    result = estimate_motion_lightweight(str(path))
    assert result["n_timepoints"] == 5
    assert np.allclose(result["motion_params"], 0.0)
    assert np.allclose(result["framewise_displacement"], 0.0)


def test_estimate_motion_lightweight_detects_a_real_shift(tmp_path):
    img = _make_bold([(0, 0, 0), (0, 0, 0), (3, 4, 0), (3, 4, 0)])  # jump of |[3,4,0]| = 5mm at t=2
    path = tmp_path / "shift.nii.gz"
    nib.save(img, str(path))

    result = estimate_motion_lightweight(str(path))
    fd = result["framewise_displacement"]
    assert fd[0] == 0.0
    assert fd[1] == pytest.approx(0.0, abs=1e-6)
    assert fd[2] == pytest.approx(5.0, abs=1e-6)  # sqrt(3^2+4^2)
    assert fd[3] == pytest.approx(0.0, abs=1e-6)


def test_rms_framewise_displacement_is_euclidean_norm_of_frame_deltas():
    params = np.array([[0, 0, 0], [3, 4, 0], [3, 4, 0]], dtype=float)
    fd = _rms_framewise_displacement(params)
    assert fd[0] == 0.0
    assert fd[1] == pytest.approx(5.0)
    assert fd[2] == pytest.approx(0.0)


def test_scrub_mask_thresholds_correctly():
    fd = np.array([0.0, 0.3, 0.5, 0.51, 2.0])
    keep = scrub_mask(fd, threshold=0.5)
    assert keep.tolist() == [True, True, True, False, False]


def test_get_or_compute_motion_uses_cache(tmp_path, monkeypatch):
    img = _make_bold([(0, 0, 0), (1, 0, 0)])
    path = tmp_path / "run.nii.gz"
    nib.save(img, str(path))
    cache_dir = tmp_path / "cache"

    calls = {"n": 0}
    import tools.motion_correction as mod

    real_fn = mod.estimate_motion_lightweight

    def counting_fn(*args, **kwargs):
        calls["n"] += 1
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(mod, "estimate_motion_lightweight", counting_fn)

    first = get_or_compute_motion(str(path), cache_dir)
    second = get_or_compute_motion(str(path), cache_dir)

    assert calls["n"] == 1  # second call served from cache
    assert np.allclose(first["framewise_displacement"], second["framewise_displacement"])
