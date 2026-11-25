"""Memory-bounded streaming topology monitor with online Welford statistical accumulators."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np

from core.topological_filtration import (
    GraphTopologyCycleSummary,
    fast_betti_landscape,
    fast_plv_matrix,
    pruned_persistence_diagram,
)


class WelfordAccumulator:
    """Numerically stable online mean and variance accumulator using Welford's algorithm."""

    def __init__(self) -> None:
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, x: float) -> None:
        """Add a single observation x in O(1) memory."""
        self.count += 1
        delta = x - self.mean
        self.mean += delta / float(self.count)
        delta2 = x - self.mean
        self.m2 += delta * delta2

    @property
    def variance(self) -> float:
        """Sample variance (or 0.0 if count < 2)."""
        return float(self.m2 / (self.count - 1)) if self.count > 1 else 0.0

    @property
    def std(self) -> float:
        """Sample standard deviation."""
        return float(np.sqrt(self.variance))


class BoundedStreamingTopologyMonitor:
    """Streaming topology monitor processing windowed phase series with fixed memory ceilings.

    Guarantees:
    - Fixed memory footprint via maxlen-bounded ring buffers.
    - O(1) online tracking of running mean and variance without buffering full time series.
    - Zero unbounded heap growth.
    """

    def __init__(
        self,
        window_samples: int,
        channel_count: int,
        max_history_windows: int = 100,
        filtration_grid: Optional[np.ndarray] = None,
    ) -> None:
        """Initialize the bounded streaming topology monitor.

        Args:
            window_samples: Number of time samples per processing window.
            channel_count: Number of recording/sensor channels.
            max_history_windows: Maximum number of recent window summaries to retain.
            filtration_grid: Optional 1D evaluation points for Betti landscapes.
        """
        if window_samples <= 0 or channel_count <= 0 or max_history_windows <= 0:
            raise ValueError("All dimension arguments must be positive integers")

        self.window_samples = window_samples
        self.channel_count = channel_count
        self.max_history_windows = max_history_windows
        self.filtration_grid = (
            np.asarray(filtration_grid, dtype=np.float64)
            if filtration_grid is not None
            else np.linspace(0.1, 0.9, 9, dtype=np.float64)
        )

        # Ring buffer of recent window metrics (fixed length, discards oldest)
        self._history: deque[Dict[str, Any]] = deque(maxlen=max_history_windows)

        # Running online statistics
        self.beta1_stats = WelfordAccumulator()
        self.landscape_area_stats = WelfordAccumulator()
        self.mean_connectivity_stats = WelfordAccumulator()
        self.total_windows_processed = 0

    def process_window(
        self,
        phases_window: np.ndarray,
        threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """Process a single window of instantaneous phase data.

        Args:
            phases_window: Array of phase angles, shape (channel_count, window_samples).
            threshold: Adjacency threshold for beta1 extraction.

        Returns:
            Dictionary containing window topology summary and updated running statistics.
        """
        arr = np.asarray(phases_window, dtype=np.float64)
        if arr.shape != (self.channel_count, self.window_samples):
            raise ValueError(
                f"Expected phase window shape ({self.channel_count}, {self.window_samples}), "
                f"got {arr.shape}"
            )

        # 1. Accelerated BLAS-3 PLV computation
        plv = fast_plv_matrix(arr)
        mean_conn = float(np.mean(plv[np.triu_indices(self.channel_count, k=1)]))
        self.mean_connectivity_stats.update(mean_conn)

        # 2. Pruned Vietoris-Rips filtration
        dgm = pruned_persistence_diagram(plv, max_dimension=1, min_threshold=0.1)

        # 3. Fast Betti-1 landscape computation
        landscape = fast_betti_landscape(dgm, self.filtration_grid, k=3)
        y_vals = np.sum(landscape, axis=0)
        if hasattr(np, "trapezoid"):
            landscape_area = float(np.trapezoid(y_vals, self.filtration_grid))
        elif hasattr(np, "trapz"):
            landscape_area = float(np.trapz(y_vals, self.filtration_grid))
        else:
            from scipy import integrate
            landscape_area = float(integrate.trapezoid(y_vals, self.filtration_grid))
        self.landscape_area_stats.update(landscape_area)

        # 4. Extract beta1 at specific filtration threshold
        # In distance filtration: edge present if d <= (1 - threshold), so birth <= (1 - threshold) < death
        dist_t = 1.0 - threshold
        if len(dgm) > 0:
            births = dgm[:, 0]
            deaths = np.where(np.isfinite(dgm[:, 1]), dgm[:, 1], 1.0)
            beta1 = int(np.count_nonzero((births <= dist_t) & (deaths > dist_t)))
        else:
            beta1 = 0
        self.beta1_stats.update(float(beta1))

        self.total_windows_processed += 1

        window_record = {
            "window_index": self.total_windows_processed - 1,
            "graph_beta1": beta1,
            "persistence_landscape_area": landscape_area,
            "mean_connectivity": mean_conn,
            "threshold": float(threshold),
        }
        self._history.append(window_record)

        return {
            **window_record,
            "running_mean_beta1": self.beta1_stats.mean,
            "running_std_beta1": self.beta1_stats.std,
            "running_mean_landscape_area": self.landscape_area_stats.mean,
            "running_std_landscape_area": self.landscape_area_stats.std,
            "total_windows": self.total_windows_processed,
            "buffered_windows": len(self._history),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Return cumulative summary of streaming monitoring metrics."""
        return {
            "total_windows_processed": self.total_windows_processed,
            "retained_history_count": len(self._history),
            "channel_count": self.channel_count,
            "window_samples": self.window_samples,
            "mean_beta1": float(self.beta1_stats.mean),
            "std_beta1": float(self.beta1_stats.std),
            "mean_landscape_area": float(self.landscape_area_stats.mean),
            "std_landscape_area": float(self.landscape_area_stats.std),
            "mean_connectivity": float(self.mean_connectivity_stats.mean),
            "std_connectivity": float(self.mean_connectivity_stats.std),
        }
