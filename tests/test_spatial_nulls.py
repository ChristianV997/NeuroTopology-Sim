"""Tests for validation/spatial_nulls.py — the sensor-space spin test.

Covers the statistical-correctness invariants that make a spin test a valid
spatial null: rotations are proper isometries about the centroid, the bijective
assignment is a true permutation, the whole pipeline is seed-deterministic, and
— the two properties that actually matter — the null is *calibrated* (a map
whose smoothness is unaligned to the region partition does not spuriously pass)
and *powered* (a map genuinely concentrated in one region is detected).
"""
from __future__ import annotations

import numpy as np
import pytest

from validation.spatial_nulls import (
    _greedy_bijective_assignment,
    _random_rotation_2d,
    region_contrast_statistic,
    spatial_spin_test,
    spin_null_distribution,
    spin_permutation_2d,
    spin_test_signed_defect_region_contrast,
)
from validation.montage_topology import signed_defect_map, triangulate_xy


def _ring_layout(n: int = 24) -> np.ndarray:
    """n sensors on a circle — a clean, symmetric montage-like layout."""
    ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return np.column_stack([np.cos(ang), np.sin(ang)])


def _grid_layout(side: int = 6) -> np.ndarray:
    xs, ys = np.meshgrid(np.linspace(-1, 1, side), np.linspace(-1, 1, side))
    return np.column_stack([xs.ravel(), ys.ravel()])


# ---------------------------------------------------------------------------
# rotation matrix
# ---------------------------------------------------------------------------

def test_random_rotation_is_orthogonal():
    rng = np.random.default_rng(0)
    for _ in range(50):
        R = _random_rotation_2d(rng, reflect=True)
        np.testing.assert_allclose(R @ R.T, np.eye(2), atol=1e-12)


def test_random_rotation_reflect_flag_controls_determinant():
    rng = np.random.default_rng(1)
    # without reflection determinant is always +1 (pure rotation)
    dets = [np.linalg.det(_random_rotation_2d(rng, reflect=False)) for _ in range(50)]
    np.testing.assert_allclose(dets, 1.0, atol=1e-12)
    # with reflection both +1 and -1 appear
    rng2 = np.random.default_rng(2)
    dets2 = np.array([np.linalg.det(_random_rotation_2d(rng2, reflect=True)) for _ in range(200)])
    assert np.any(dets2 > 0) and np.any(dets2 < 0)


# ---------------------------------------------------------------------------
# greedy bijective assignment
# ---------------------------------------------------------------------------

def test_greedy_assignment_is_a_permutation():
    rng = np.random.default_rng(3)
    pts = rng.normal(size=(20, 2))
    diff = pts[:, None, :] - pts[None, :, :]
    dist2 = np.einsum("ijk,ijk->ij", diff, diff)
    perm = _greedy_bijective_assignment(dist2)
    assert sorted(perm.tolist()) == list(range(20))


def test_greedy_assignment_identity_when_targets_equal_sources():
    # zero rotation ⇒ each original's nearest is itself ⇒ identity permutation
    diff_pts = _grid_layout(5)
    diff = diff_pts[:, None, :] - diff_pts[None, :, :]
    dist2 = np.einsum("ijk,ijk->ij", diff, diff)
    perm = _greedy_bijective_assignment(dist2)
    np.testing.assert_array_equal(perm, np.arange(diff_pts.shape[0]))


# ---------------------------------------------------------------------------
# spin_permutation_2d
# ---------------------------------------------------------------------------

def test_spin_permutation_is_permutation_bijective():
    xy = _ring_layout(24)
    rng = np.random.default_rng(4)
    perm = spin_permutation_2d(xy, rng, bijective=True)
    assert sorted(perm.tolist()) == list(range(24))


def test_spin_permutation_preserves_value_multiset_bijective():
    xy = _ring_layout(24)
    vals = np.arange(24, dtype=float)
    rng = np.random.default_rng(5)
    perm = spin_permutation_2d(xy, rng, bijective=True)
    np.testing.assert_array_equal(np.sort(vals[perm]), np.sort(vals))


def test_spin_permutation_nonbijective_may_not_be_permutation():
    # On a ring, a generic rotation lands each rotated point between two
    # originals; independent nearest-neighbour can reuse/skip targets. We only
    # assert it returns valid in-range indices (not necessarily a permutation).
    xy = _ring_layout(24)
    rng = np.random.default_rng(6)
    perm = spin_permutation_2d(xy, rng, bijective=False)
    assert perm.min() >= 0 and perm.max() < 24


def test_spin_permutation_rejects_degenerate_layout():
    with pytest.raises(ValueError):
        spin_permutation_2d(np.zeros((2, 2)), np.random.default_rng(0))


# ---------------------------------------------------------------------------
# isometry: a rigid spin preserves pairwise distances (the reason SA is kept)
# ---------------------------------------------------------------------------

def test_rotation_is_a_true_isometry_of_the_cloud():
    """The rotation the spin actually applies (about the centroid) preserves the
    full pairwise-distance spectrum of the sensor cloud — the reason spatial
    autocorrelation survives. The ROTATED coordinates must enter the assertion:
    an earlier form compared xy[perm], which is permutation-invariant by
    construction (identical for ANY perm, even a random shuffle) and therefore
    could not detect a broken permutation at all."""
    xy = _grid_layout(6)
    rng = np.random.default_rng(7)
    centroid = xy.mean(axis=0, keepdims=True)
    R = _random_rotation_2d(rng, reflect=True)
    rotated = (xy - centroid) @ R.T + centroid
    d_orig = np.sort(np.linalg.norm(xy[:, None] - xy[None], axis=-1).ravel())
    d_rot = np.sort(np.linalg.norm(rotated[:, None] - rotated[None], axis=-1).ravel())
    np.testing.assert_allclose(d_orig, d_rot, atol=1e-9)


def test_spin_preserves_local_smoothness_unlike_shuffle():
    """The property that actually distinguishes a valid spin from a broken
    (geometry-ignoring) shuffle: applying the spin permutation to a smooth field
    keeps neighbouring sensors similar (smoothness preserved), whereas an
    independent shuffle destroys it. Smoothness = mean squared difference between
    each sensor and its nearest neighbour (lower = smoother)."""
    xy = _grid_layout(8)
    vals = xy[:, 0] + xy[:, 1]  # smooth planar field
    D = np.linalg.norm(xy[:, None] - xy[None], axis=-1)
    np.fill_diagonal(D, np.inf)
    nn = D.argmin(axis=1)
    msd = lambda v: float(np.mean((v - v[nn]) ** 2))
    rng = np.random.default_rng(3)
    perm_spin = spin_permutation_2d(xy, rng, bijective=True)
    perm_shuf = rng.permutation(xy.shape[0])
    msd_spin = msd(vals[perm_spin])
    msd_shuf = msd(vals[perm_shuf])
    # the spun field stays markedly smoother than the shuffled field
    assert msd_spin < 0.5 * msd_shuf


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------

def test_spin_null_distribution_deterministic():
    xy = _ring_layout(20)
    vals = np.sin(np.linspace(0, 4 * np.pi, 20))
    stat = lambda v: float(v[:10].mean() - v[10:].mean())
    a = spin_null_distribution(vals, xy, stat, n_rotations=100, seed=42)
    b = spin_null_distribution(vals, xy, stat, n_rotations=100, seed=42)
    np.testing.assert_array_equal(a, b)


def test_spatial_spin_test_deterministic():
    xy = _grid_layout(6)
    vals = xy[:, 0]  # value = x-coordinate (a smooth anterior-posterior gradient)
    labels = (xy[:, 0] > 0).astype(int)
    stat = region_contrast_statistic(labels, 1, 0)
    r1 = spatial_spin_test(vals, xy, stat, n_rotations=200, seed=1)
    r2 = spatial_spin_test(vals, xy, stat, n_rotations=200, seed=1)
    assert r1 == r2


# ---------------------------------------------------------------------------
# region_contrast_statistic
# ---------------------------------------------------------------------------

def test_region_contrast_statistic_value():
    labels = np.array([0, 0, 1, 1])
    stat = region_contrast_statistic(labels, 1, 0)
    vals = np.array([1.0, 3.0, 10.0, 20.0])
    assert stat(vals) == pytest.approx(15.0 - 2.0)


def test_region_contrast_statistic_rejects_empty_region():
    labels = np.array([0, 0, 0])
    with pytest.raises(ValueError):
        region_contrast_statistic(labels, 1, 0)


# ---------------------------------------------------------------------------
# THE TWO THAT MATTER: calibration (no false positive) and power (true positive)
# ---------------------------------------------------------------------------

def test_spin_test_powered_on_genuine_region_effect():
    """A map whose values are strongly concentrated in region A (aligned to the
    partition) must yield a small spin-test p-value: the observed contrast sits
    in the tail of the spun null."""
    xy = _grid_layout(8)
    labels = (xy[:, 0] > 0).astype(int)
    # values LARGE in region 1, small in region 0 — a real, partition-aligned map
    vals = np.where(labels == 1, 5.0, 0.0) + 0.01 * xy[:, 1]
    stat = region_contrast_statistic(labels, 1, 0)
    res = spatial_spin_test(vals, xy, stat, n_rotations=500, seed=0, two_sided=True)
    assert res["observed"] > 3.0
    assert res["p_value"] < 0.05
    assert res["passes_gate_p05"] is True


def test_spin_test_calibrated_against_partition_orthogonal_gradient():
    """A smooth spatial gradient laid along an axis ORTHOGONAL to the region
    split (values track y, partition splits on x) has real spatial
    autocorrelation but no alignment to the partition. Its observed contrast
    must NOT be flagged — the spin null, which preserves that smoothness, easily
    reproduces the near-zero contrast, so p is far from significant."""
    xy = _grid_layout(8)
    labels = (xy[:, 0] > 0).astype(int)      # partition on x
    vals = xy[:, 1]                           # smooth gradient on y (orthogonal)
    stat = region_contrast_statistic(labels, 1, 0)
    res = spatial_spin_test(vals, xy, stat, n_rotations=500, seed=0, two_sided=True)
    assert abs(res["observed"]) < 1e-6        # symmetric ⇒ ~zero contrast
    assert res["p_value"] > 0.05
    assert res["passes_gate_p05"] is False


def test_spin_null_is_wider_than_shuffle_null_on_smooth_map():
    """THE discriminating property (the one a too-weak null fails). On a smooth
    field aligned to the partition axis, the spin null — which preserves spatial
    autocorrelation — spans a WIDE range (the gradient sometimes rotates into
    alignment with the region split, sometimes orthogonal to it), whereas an
    independent label-shuffle null destroys the smoothness and collapses to a
    narrow band near zero. A broken geometry-ignoring null would look like the
    shuffle; this test fails loudly for it."""
    xy = _grid_layout(8)
    labels = (xy[:, 0] > 0).astype(int)
    vals = xy[:, 0] + 0.05 * np.sin(3 * xy[:, 1])  # smooth, strongly autocorrelated
    stat = region_contrast_statistic(labels, 1, 0, agg="mean")
    spin_null = spin_null_distribution(vals, xy, stat, n_rotations=500, seed=0)
    rng = np.random.default_rng(0)
    shuffle_null = np.array(
        [stat(vals[rng.permutation(vals.shape[0])]) for _ in range(500)]
    )
    # the smoothness-preserving null is materially wider than the shuffle null
    assert spin_null.std() > 1.5 * shuffle_null.std()


def test_spin_test_null_false_positive_rate_is_controlled():
    """Calibration in aggregate: across many random smooth maps that are NOT
    aligned to the partition, the fraction of spin-test rejections at alpha=0.05
    stays near 0.05 (not inflated). The correct bijective spin yields FPR=0.00 on
    this fixed ensemble, so the ceiling is set tight (0.10) — a broken
    independent-shuffle null inflates this to ~0.20 and is caught here (the
    earlier 0.20 ceiling sat exactly on that failure value and let it pass)."""
    xy = _grid_layout(7)
    labels = (xy[:, 0] > 0).astype(int)
    stat = region_contrast_statistic(labels, 1, 0)
    rng = np.random.default_rng(123)
    n_maps = 40
    rejections = 0
    for m in range(n_maps):
        # a smooth random field: low-frequency sinusoid at a random orientation,
        # deliberately independent of the x-partition
        theta = rng.uniform(0, 2 * np.pi)
        k = rng.uniform(0.8, 1.6)
        proj = xy @ np.array([np.cos(theta), np.sin(theta)])
        vals = np.sin(k * np.pi * proj) + 0.1 * rng.normal(size=xy.shape[0])
        res = spatial_spin_test(vals, xy, stat, n_rotations=200, seed=int(m), two_sided=True)
        if res["p_value"] < 0.05:
            rejections += 1
    fpr = rejections / n_maps
    # correct null gives 0.00 here; tight ceiling catches a too-weak (shuffle) null
    assert fpr <= 0.10, f"false-positive rate {fpr:.2f} indicates an invalid (too-weak) null"


def test_spin_test_rejects_too_few_usable_spins():
    """If the observed statistic computes fine but every spin fails, there is no
    null distribution to test against and the function must raise (not silently
    return a degenerate result). Uses a fn that succeeds on the first (observed)
    call and raises on every subsequent (spun) call."""
    xy = _ring_layout(12)
    vals = np.arange(12, dtype=float)
    state = {"n": 0}

    def _fails_after_observed(v):
        state["n"] += 1
        if state["n"] == 1:
            return float(v.mean())  # observed call succeeds
        raise RuntimeError("boom")  # all spins fail

    with pytest.raises(ValueError, match="too few usable spins"):
        spatial_spin_test(vals, xy, _fails_after_observed, n_rotations=50, seed=0)


def test_spatial_spin_test_reports_n_failed():
    """n_failed must reflect spins on which the statistic could not be computed,
    for parity with surrogate_testing's explicit failure accounting."""
    xy = _grid_layout(6)
    vals = xy[:, 0]
    labels = (xy[:, 0] > 0).astype(int)
    stat = region_contrast_statistic(labels, 1, 0)
    res = spatial_spin_test(vals, xy, stat, n_rotations=100, seed=0)
    assert res["n_failed"] == 0
    assert res["n_used"] + res["n_failed"] == res["n_rotations"]


def test_region_contrast_statistic_sum_vs_mean():
    labels = np.array([0, 0, 1, 1, 1])
    vals = np.array([1.0, 3.0, 10.0, 20.0, 30.0])
    mean_stat = region_contrast_statistic(labels, 1, 0, agg="mean")
    sum_stat = region_contrast_statistic(labels, 1, 0, agg="sum")
    assert mean_stat(vals) == pytest.approx(20.0 - 2.0)   # 60/3 - 4/2
    assert sum_stat(vals) == pytest.approx(60.0 - 4.0)
    with pytest.raises(ValueError):
        region_contrast_statistic(labels, 1, 0, agg="median")


# ---------------------------------------------------------------------------
# END-TO-END integration: real signed_defect_map -> spin-test wrapper
# ---------------------------------------------------------------------------

def test_spin_test_signed_defect_wrapper_end_to_end():
    """The bridge that closes the spatial-null gap: run signed_defect_map on a
    real triangulated montage, then spin-test the net-charge contrast between two
    regions directly from the defect_map + region labels, with no caller-side
    re-implementation of the triangle->region labeling."""
    n = 24
    ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    xy = np.column_stack([np.cos(ang), np.sin(ang)])
    tri = triangulate_xy(xy)
    rng = np.random.default_rng(0)
    phase = rng.uniform(-np.pi, np.pi, size=n)
    dm = signed_defect_map(phase, xy, tri)
    names = [f"c{i}" for i in range(n)]
    # left/right hemisphere split by x-coordinate — a real two-region hypothesis
    region_labels = {names[i]: ("R" if xy[i, 0] > 0 else "L") for i in range(n)}

    res = spin_test_signed_defect_region_contrast(
        dm, region_labels, names, "R", "L", n_rotations=200, seed=0,
    )
    assert res["metric_kind"] == "spatial_spin_net_charge_contrast"
    assert res["agg"] == "sum"
    assert res["n_triangles_used"] >= 3
    assert res["n_triangles_used"] + res["n_triangles_unassigned"] == dm["n_valid_triangles"]
    assert 0.0 < res["p_value"] <= 1.0
    assert np.isfinite(res["observed"]) and np.isfinite(res["z"])


def test_spin_test_wrapper_matches_net_charge_by_region_labeling():
    """The wrapper's triangle->region assignment must be exactly the one
    net_charge_by_region uses (both go through assign_triangles_to_regions), so
    the count of region-assigned triangles agrees with net_charge_by_region."""
    from validation.montage_topology import net_charge_by_region

    n = 20
    ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    xy = np.column_stack([np.cos(ang), np.sin(ang)])
    tri = triangulate_xy(xy)
    rng = np.random.default_rng(1)
    phase = rng.uniform(-np.pi, np.pi, size=n)
    dm = signed_defect_map(phase, xy, tri)
    names = [f"c{i}" for i in range(n)]
    region_labels = {names[i]: ("R" if xy[i, 0] > 0 else "L") for i in range(n)}

    nc = net_charge_by_region(dm, region_labels, names)
    res = spin_test_signed_defect_region_contrast(
        dm, region_labels, names, "R", "L", n_rotations=100, seed=0,
    )
    assert res["n_triangles_unassigned"] == nc["n_unassigned"]
    assert res["n_triangles_used"] == sum(nc["region_n_triangles"].values())
