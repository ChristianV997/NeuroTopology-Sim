"""Base class and telemetry instrumentation for persistent homology backends."""
from __future__ import annotations

import abc
import time
import tracemalloc
from contextlib import contextmanager
from typing import Generator

import numpy as np

from .types import (
    BackendCapability,
    InputKind,
    PersistenceInterval,
    PersistencePair,
    ScientificStatus,
    TDAConfig,
    TDAPersistenceResult,
    compute_deterministic_checksum,
)
from .landscape import compute_persistence_landscape


@contextmanager
def track_execution_telemetry(enable_memory: bool = True) -> Generator[dict[str, Any], None, None]:
    """Track wall-clock runtime and peak memory consumption."""
    telemetry: dict[str, Any] = {"runtime_seconds": 0.0, "peak_memory_bytes": None}
    track_mem = enable_memory
    if track_mem:
        tracemalloc.start()

    start_time = time.perf_counter()
    try:
        yield telemetry
    finally:
        end_time = time.perf_counter()
        telemetry["runtime_seconds"] = max(0.0, end_time - start_time)
        if track_mem:
            try:
                _, peak = tracemalloc.get_traced_memory()
                telemetry["peak_memory_bytes"] = int(peak)
            finally:
                tracemalloc.stop()


class BaseTDABackend(abc.ABC):
    """Abstract persistent homology backend adapter."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier of the backend."""
        pass

    @abc.abstractmethod
    def get_capability(self) -> BackendCapability:
        """Return status and capability metadata for this backend."""
        pass

    @abc.abstractmethod
    def _compute_intervals_and_pairs(
        self,
        data: np.ndarray,
        input_kind: InputKind,
        config: TDAConfig,
    ) -> tuple[list[PersistenceInterval], list[PersistenceInterval], list[PersistencePair], tuple[float, float | None]]:
        """Compute raw persistence intervals and pairs.

        Returns:
            (beta_0_intervals, beta_1_intervals, persistence_pairs, filtration_range)
        """
        pass

    @property
    def scientific_status(self) -> ScientificStatus:
        """Scientific classification of this backend's results."""
        return ScientificStatus.STRICT_COHOMOLOGY

    def compute(
        self,
        data: np.ndarray,
        input_kind: InputKind,
        config: TDAConfig | None = None,
    ) -> TDAPersistenceResult:
        """Run persistent homology computation with telemetry and validation."""
        cfg = config or TDAConfig()
        n_points = data.shape[0]

        with track_execution_telemetry(enable_memory=cfg.track_memory) as tel:
            b0_intervals, b1_intervals, pairs, filt_range = self._compute_intervals_and_pairs(
                data, input_kind, cfg
            )

        # Compute landscape if requested
        landscape_layers = None
        landscape_grid = None
        landscape_area = None
        if cfg.compute_landscape:
            landscape_layers, landscape_grid, landscape_area = compute_persistence_landscape(
                intervals=b1_intervals,
                num_layers=cfg.landscape_layers,
                resolution=cfg.landscape_resolution,
                filtration_range=filt_range,
            )

        # Compute deterministic checksum
        checksum = compute_deterministic_checksum(
            backend=self.name,
            filtration_range=filt_range,
            beta_0_intervals=b0_intervals,
            beta_1_intervals=b1_intervals,
            input_kind=input_kind.value,
            num_points=n_points,
            landscape_area=landscape_area,
        )

        return TDAPersistenceResult(
            beta_0_intervals=b0_intervals,
            beta_1_intervals=b1_intervals,
            persistence_pairs=pairs,
            filtration_range=filt_range,
            backend=self.name,
            runtime_seconds=tel["runtime_seconds"],
            memory_telemetry_bytes=tel["peak_memory_bytes"],
            deterministic_checksum=checksum,
            scientific_status=self.scientific_status,
            input_kind=input_kind,
            num_points=n_points,
            landscape=landscape_layers,
            landscape_grid=landscape_grid,
            landscape_integrated_area=landscape_area,
            metadata={"node_order_provided": cfg.node_order is not None},
        )
