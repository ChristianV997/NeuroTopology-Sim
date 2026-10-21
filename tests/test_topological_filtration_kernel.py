"""Unit tests for accelerated topological filtration kernels and streaming monitors."""
from __future__ import annotations

import numpy as np
import pytest

from core.topological_filtration import (
    GraphTopologyCycleSummary,
    SpatialFieldDefectSummary,
    fast_betti_landscape,
    fast_plv_matrix,
    pruned_persistence_diagram,
)
from topo_monitor.streaming import BoundedStreamingTopologyMonitor, WelfordAccumulator


class TestFastPLVKernel:
    def test_plv_matches_broadcasting_reference(self):
        """BLAS-3 PLV must exactly match reference pairwise mean phase difference."""
        rng = np.random.default_rng(42)
        c, s = 8, 500
        phases = rng.uniform(-np.pi, np.pi, size=(c, s))

        # 1. Accelerated BLAS-3 PLV
        fast_plv = fast_plv_matrix(phases)

        # 2. Reference pairwise broadcast
        diff = phases[:, None, :] - phases[None, :, :]
        ref_plv = np.abs(np.mean(np.exp(1j * diff), axis=2))
        np.fill_diagonal(ref_plv, 1.0)

        err = np.max(np.abs(fast_plv - ref_plv))
        assert err < 1e-12, f"PLV mismatch with reference: {err}"
        assert np.all(fast_plv >= 0.0) and np.all(fast_plv <= 1.0)
        assert np.allclose(np.diag(fast_plv), 1.0)


class TestPrunedPersistence:
    def test_pruning_limits_distance(self):
        """Distance-pruned Ripser diagram must not contain birth times beyond cutoff."""
        rng = np.random.default_rng(101)
        phases = rng.uniform(-np.pi, np.pi, size=(10, 200))
        plv = fast_plv_matrix(phases)

        cutoff = 0.5
        dgm = pruned_persistence_diagram(plv, max_dimension=1, distance_cutoff=cutoff)

        if len(dgm) > 0:
            assert np.all(dgm[:, 0] <= cutoff + 1e-6)
            assert np.all(dgm[:, 1] >= dgm[:, 0])


class TestBettiLandscape:
    def test_landscape_properties(self):
        """Betti landscape curves must be non-negative and obey triangular tent peaks."""
        # Diagram with single pair (b=0.2, d=0.6), midpoint=0.4, peak=0.2
        dgm = np.array([[0.2, 0.6]], dtype=np.float64)
        grid = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])

        land = fast_betti_landscape(dgm, grid, k=1, noise_threshold=0.01)
        assert land.shape == (1, len(grid))

        # Values at b and d are 0
        assert np.isclose(land[0, 1], 0.0)  # at t=0.2
        assert np.isclose(land[0, 5], 0.0)  # at t=0.6

        # Peak at midpoint t=0.4 is 0.2
        assert np.isclose(land[0, 3], 0.2)  # at t=0.4

        # Zero outside [b, d]
        assert np.isclose(land[0, 0], 0.0)  # at t=0.1
        assert np.isclose(land[0, 6], 0.0)  # at t=0.7


class TestStreamingMonitor:
    def test_ring_buffer_and_welford_statistics(self):
        """Streaming monitor must enforce bounded deque capacity and accurate Welford stats."""
        monitor = BoundedStreamingTopologyMonitor(
            window_samples=100,
            channel_count=8,
            max_history_windows=5,
        )

        rng = np.random.default_rng(202)
        for i in range(12):
            window = rng.uniform(-np.pi, np.pi, size=(8, 100))
            rec = monitor.process_window(window, threshold=0.5)
            assert rec["buffered_windows"] <= 5
            assert rec["total_windows"] == i + 1

        summary = monitor.get_summary()
        assert summary["total_windows_processed"] == 12
        assert summary["retained_history_count"] == 5
        assert summary["mean_beta1"] >= 0.0
        assert summary["std_beta1"] >= 0.0


class TestModelDecoupling:
    def test_cycle_vs_charge_separation(self):
        """Graph cycles (H1) must not require or accept physical Cartesian coordinates."""
        cycle = GraphTopologyCycleSummary(
            graph_beta1=3,
            persistence_landscape_area=0.125,
            filtration_threshold=0.5,
            sweep_thresholds=[0.3, 0.5, 0.7],
            sweep_beta1=[1, 3, 0],
        )
        d_cycle = cycle.to_dict()
        assert d_cycle["topological_type"] == "graph_cycle_h1"
        assert "coordinate_frame" not in d_cycle

        defect = SpatialFieldDefectSummary(
            charge_q=-1,
            charge_q_abs=1.0,
            sensor_count=64,
            coordinate_frame="10-20_standard_eeg",
            grid_shape=(8, 8),
        )
        d_defect = defect.to_dict()
        assert d_defect["topological_type"] == "spatial_phase_defect"
        assert d_defect["coordinate_frame"] == "10-20_standard_eeg"
