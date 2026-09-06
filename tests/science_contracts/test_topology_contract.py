from __future__ import annotations

import numpy as np
import pytest

from analysis.connectivity_topology import (
    compute_graph_beta1,
    generate_null_controls,
    topology_metric_record,
)
from topo_monitor.graph_persistence import analyze_adjacency, node_order_invariant
from topo_monitor.spatial_phase import analytic_vortex_fixture, spatial_winding_charge


def _ring(n: int = 8) -> np.ndarray:
    adjacency = np.zeros((n, n), dtype=float)
    for i in range(n):
        adjacency[i, (i + 1) % n] = adjacency[(i + 1) % n, i] = 0.95
        adjacency[i, (i + 2) % n] = adjacency[(i + 2) % n, i] = 0.8
    np.fill_diagonal(adjacency, 1.0)
    return adjacency


def test_graph_and_spatial_metrics_are_separate():
    record = topology_metric_record(graph_beta1=2, spatial_winding_q=1, scalar_chirality=0.25)
    assert record["metrics"]["graph_beta1"] == 2
    assert record["metrics"]["spatial_winding_q"] == 1
    assert record["separation"]["graph_beta1_is_spatial_charge"] is False
    assert record["separation"]["spatial_winding_requires_coordinates"] is True


def test_graph_persistence_has_deterministic_sweep_and_method_metadata():
    pytest.importorskip("ripser")
    result = analyze_adjacency(_ring(), threshold=0.5)
    assert result.metric_name == "graph_beta1"
    assert result.method.startswith("vietoris_rips_h1")
    assert result.coordinate_frame is None
    assert np.all(np.diff(result.sweep_thresholds) > 0)
    assert np.all(np.isfinite(result.sweep_beta1))
    assert result.to_dict()["graph_beta1"] == result.graph_beta1
    assert node_order_invariant(_ring(), np.arange(8)[::-1])


def test_known_analytic_vortex_requires_and_recovers_geometry():
    fixture = analytic_vortex_fixture((65, 65), charge=1)
    missing = spatial_winding_charge(fixture["phases"], None)
    assert missing["status"] == "INCONCLUSIVE"
    assert missing["winding_q"] is None

    result = spatial_winding_charge(
        fixture["phases"],
        fixture["coordinates"],
        coordinate_frame=fixture["coordinate_frame"],
        amplitude=fixture["amplitude"],
        amplitude_threshold=0.0,
        return_details=True,
    )
    assert result.status == "VALID"
    # The plaquette traversal convention is clockwise for this array layout;
    # recovery is therefore checked by the known unit magnitude.
    assert abs(result.winding_q) == 1.0
    assert result.coordinate_frame == "fixture_cartesian_xy"
    assert result.interpolation_method == "plaquette_grid"
    assert result.amplitude_mask is not None


def test_null_controls_are_seeded_and_reproducible():
    signals = np.arange(4 * 32, dtype=float).reshape(4, 32)
    coordinates = np.arange(8, dtype=float).reshape(4, 2)
    first = generate_null_controls(signals, coordinates=coordinates, block_size=4, seed=7)
    second = generate_null_controls(signals, coordinates=coordinates, block_size=4, seed=7)
    assert set(first) == {
        "phase_randomization",
        "channel_shuffling",
        "time_reversal",
        "coordinate_shuffling",
        "block_permutation",
        "stationary_null",
    }
    for name in first:
        assert first[name]["seed"] == 7
        assert first[name]["method"]
        key = "coordinates" if name == "coordinate_shuffling" else "values"
        np.testing.assert_array_equal(first[name][key], second[name][key])


def test_graph_beta1_is_not_a_spatial_charge_api():
    pytest.importorskip("ripser")
    assert isinstance(compute_graph_beta1(_ring(), threshold=0.5), int)
