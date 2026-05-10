from __future__ import annotations

import numpy as np
import pytest

from validation.montage_topology import (
    phase_grid_topology_from_band,
    sensor_phase_topology_metrics,
    triangle_winding,
    triangulate_xy,
)


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
