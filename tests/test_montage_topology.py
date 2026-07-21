from __future__ import annotations

import numpy as np
import pytest

from validation.montage_topology import (
    EPS,
    defect_spatial_clustering,
    get_channel_xy_templateflow,
    net_charge_by_region,
    phase_grid_topology_from_band,
    sensor_phase_topology_metrics,
    signed_defect_map,
    signed_defect_topology_from_band,
    triangle_winding,
    triangulate_xy,
)

# tolerance for the net-vs-abs charge separation assertion (named, not a bare literal)
CANCEL_TOL = 1e-6


def _vortex_antivortex(n=7):
    """Grid phase field with a +1 vortex (left) and a -1 antivortex (right).

    phase = angle(r - z1) - angle(r - z2); winding is +1 around z1, -1 around z2.
    Returns (xy, phase, triangles, channel_names).
    """
    gx, gy = np.meshgrid(np.linspace(-1, 1, n), np.linspace(-1, 1, n))
    xy = np.c_[gx.ravel(), gy.ravel()]
    z1 = np.array([-0.5, 0.0])
    z2 = np.array([0.5, 0.0])
    phase = (np.arctan2(xy[:, 1] - z1[1], xy[:, 0] - z1[0])
             - np.arctan2(xy[:, 1] - z2[1], xy[:, 0] - z2[0]))
    tri = triangulate_xy(xy)
    names = [f"c{i}" for i in range(xy.shape[0])]
    return xy, phase, tri, names


def test_triangulate_xy_square_points():
    xy = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
    tri = triangulate_xy(xy)
    assert tri.ndim == 2 and tri.shape[1] == 3
    assert tri.shape[0] >= 2


def test_triangle_winding_finite():
    w = triangle_winding(0.1, 1.2, -0.7)
    assert np.isfinite(w)


def test_sensor_phase_topology_metrics_keys_finite():
    xy = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
    tri = triangulate_xy(xy)
    phase = np.array([0.0, 0.3, 0.6, 1.0])
    m = sensor_phase_topology_metrics(phase, xy, tri)
    for k in ("Q", "Qabs", "f_dress", "phase_grad", "n_triangles", "n_valid_triangles", "defect_density"):
        assert k in m
        assert np.isfinite(m[k])


def test_sensor_phase_topology_metrics_too_few_points():
    with pytest.raises(ValueError):
        sensor_phase_topology_metrics(np.array([0.0, 0.1]), np.array([[0, 0], [1, 0]]), np.array([[0, 1, 1]]))


def test_low_amplitude_mask_reduces_valid_triangles():
    xy = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
    tri = triangulate_xy(xy)
    phase = np.array([0.0, 0.2, 0.5, 0.7])
    amp = np.array([1.0, 1.0, 0.01, 1.0])
    m_all = sensor_phase_topology_metrics(phase, xy, tri, amp_vec=None)
    m_mask = sensor_phase_topology_metrics(phase, xy, tri, amp_vec=amp, amp_quantile=0.2)
    assert m_mask["n_valid_triangles"] <= m_all["n_valid_triangles"]


def test_phase_grid_topology_from_band_finite():
    xy = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
    tri = triangulate_xy(xy)
    phase = np.tile(np.array([[0.0], [0.5], [1.0], [1.5]]), (1, 20))
    m = phase_grid_topology_from_band(phase, xy, tri)
    assert np.isfinite(m["Qabs"])


def test_vortex_like_phase_nonzero_qabs():
    angles = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    xy = np.c_[np.cos(angles), np.sin(angles)]
    tri = triangulate_xy(xy)
    phase = np.tile(angles[:, None], (1, 10))
    m = phase_grid_topology_from_band(phase, xy, tri)
    assert m["Qabs"] > 0


def test_invalid_phase_shape_raises():
    xy = np.array([[0, 0], [1, 0], [0, 1]], dtype=float)
    tri = triangulate_xy(xy)
    with pytest.raises(ValueError):
        phase_grid_topology_from_band(np.zeros(10), xy, tri)


# ── signed / localized phase-defect metrics ──────────────────────────────────


def test_signed_defect_map_preserves_sign():
    # One clockwise + one counter-clockwise vortex must leave both a positive and
    # a negative signed winding -- the exact information the old Qabs destroys.
    xy, phase, tri, _ = _vortex_antivortex()
    dm = signed_defect_map(phase, xy, tri)
    sw = dm["signed_winding"]
    assert np.any(sw > 0) and np.any(sw < 0)
    # Proof that the new function is a strict refinement, not a different
    # computation: summing |signed_winding| reproduces the old unsigned Qabs, and
    # rounding the signed sum reproduces the old signed Q, on the same inputs.
    old = sensor_phase_topology_metrics(phase, xy, tri)
    assert np.isclose(np.sum(np.abs(sw)), old["Qabs"])
    assert np.isclose(np.round(np.sum(sw)), old["Q"])
    assert dm["chirality"].tolist().count(1) >= 1 and dm["chirality"].tolist().count(-1) >= 1


def test_signed_defect_map_two_opposite_defects_cancel_net_charge():
    # Equal-and-opposite defects: net signed charge cancels toward zero while the
    # unsigned (Qabs-equivalent) sum stays clearly nonzero.
    xy, phase, tri, _ = _vortex_antivortex()
    dm = signed_defect_map(phase, xy, tri)
    sw = dm["signed_winding"]
    net = abs(float(np.sum(sw)))
    unsigned = float(np.sum(np.abs(sw)))
    assert unsigned > CANCEL_TOL
    assert net < unsigned - CANCEL_TOL


def test_net_charge_by_region_basic():
    xy = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
    tri = triangulate_xy(xy)
    phase = np.array([0.0, 0.3, 0.6, 1.0])
    names = ["c0", "c1", "c2", "c3"]
    dm = signed_defect_map(phase, xy, tri)
    labels = {"c0": "A", "c1": "A", "c2": "B", "c3": "B"}
    nc = net_charge_by_region(dm, labels, names)
    # every triangle is accounted for: assigned counts + unassigned == n_valid
    assert sum(nc["region_n_triangles"].values()) + nc["n_unassigned"] == dm["n_valid_triangles"]
    # only regions that received triangles are keys, and they are a subset of {A,B}
    assert set(nc["region_net_charge"]) <= {"A", "B"}
    assert set(nc["region_net_charge"]) == set(nc["region_n_triangles"])
    for r in nc["region_net_charge"]:
        assert np.isfinite(nc["region_net_charge"][r])
        assert np.isfinite(nc["region_mean_chirality"][r])


def test_net_charge_by_region_partial_labels_unassigned():
    xy = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
    tri = triangulate_xy(xy)
    phase = np.array([0.0, 0.3, 0.6, 1.0])
    names = ["c0", "c1", "c2", "c3"]
    dm = signed_defect_map(phase, xy, tri)
    labels = {"c0": "A", "c1": "A", "c3": "B"}  # c2 deliberately omitted
    nc = net_charge_by_region(dm, labels, names)
    # triangles touching the unlabeled channel are unassigned, never dropped/crashed
    assert nc["n_unassigned"] >= 1
    assert sum(nc["region_n_triangles"].values()) + nc["n_unassigned"] == dm["n_valid_triangles"]


def _defect_map(centroids, windings):
    """Construct a minimal signed_defect_map-shaped dict for clustering tests."""
    centroids = np.asarray(centroids, dtype=float)
    windings = np.asarray(windings, dtype=float)
    return {
        "triangle_indices": np.zeros((len(windings), 3), dtype=int),
        "signed_winding": windings,
        "centroid_xy": centroids,
        "chirality": np.sign(windings).astype(int),
        "n_valid_triangles": int(len(windings)),
        "metric_kind": "signed_defect_map",
    }


def test_defect_spatial_clustering_insufficient_data():
    # only 2 triangles clear the min_winding_abs threshold; below min_samples=3
    dm = _defect_map([[0.0, 0.0], [0.01, 0.0], [5.0, 5.0]], [0.9, 0.9, 0.0])
    res = defect_spatial_clustering(dm)
    assert res["n_clusters"] == 0
    assert "note" in res and "insufficient" in res["note"]


def test_defect_spatial_clustering_finds_cluster():
    # a tight group of 5 strong defects in one corner + 2 far scattered ones
    tight = [[0.00, 0.00], [0.01, 0.00], [0.00, 0.01], [0.01, 0.01], [0.005, 0.005]]
    scattered = [[5.0, 5.0], [-6.0, 4.0]]
    cents = tight + scattered
    winds = [0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9]
    res = defect_spatial_clustering(_defect_map(cents, winds))
    assert res["n_clusters"] >= 1
    assert res["cluster_sizes"].sum() + res["n_noise"] == 7


def test_signed_defect_topology_from_band_no_region_labels():
    xy, phase1d, tri, names = _vortex_antivortex()
    phase = np.tile(phase1d[:, None], (1, 6))
    out = signed_defect_topology_from_band(phase, xy, tri, names, region_labels=None)
    assert out["mean_net_charge_by_region"] is None
    assert out["mean_abs_charge_by_region"] is None
    assert out["mean_region_chirality"] is None
    assert np.isfinite(out["mean_n_clusters"])
    assert np.isfinite(out["mean_cluster_persistence_proxy"])
    assert isinstance(out["time_resolved_n_clusters"], list) and len(out["time_resolved_n_clusters"]) == 6


def test_signed_defect_topology_from_band_with_region_labels():
    xy, phase1d, tri, names = _vortex_antivortex()
    phase = np.tile(phase1d[:, None], (1, 5))
    # split montage into left / right hemispheres by x coordinate
    labels = {names[i]: ("L" if xy[i, 0] < 0 else "R") for i in range(len(names))}
    out = signed_defect_topology_from_band(phase, xy, tri, names, region_labels=labels)
    assert out["mean_net_charge_by_region"] is not None
    assert len(out["mean_net_charge_by_region"]) >= 1
    for d in (out["mean_net_charge_by_region"], out["mean_abs_charge_by_region"], out["mean_region_chirality"]):
        assert all(np.isfinite(v) for v in d.values())


def test_signed_defect_topology_persistence_proxy_short_series():
    xy, phase1d, tri, names = _vortex_antivortex()
    phase = phase1d[:, None]  # single timepoint
    out = signed_defect_topology_from_band(phase, xy, tri, names, region_labels=None)
    assert out["mean_cluster_persistence_proxy"] == 0.0
    assert out["n_timepoints"] == 1


def test_get_channel_xy_templateflow_requires_mne_raw():
    """Test that get_channel_xy_templateflow requires a valid raw object."""
    pytest.importorskip("templateflow")
    pytest.importorskip("nibabel")
    with pytest.raises(ValueError, match="No EEG channels"):
        get_channel_xy_templateflow(
            type('MockRaw', (), {'ch_names': [], 'get_montage': lambda: None})(),
            montage="standard_1020",
        )
