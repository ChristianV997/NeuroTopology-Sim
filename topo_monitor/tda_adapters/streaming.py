"""Streaming and memory-bounded windowed point-cloud persistent homology processing.

Supports:
- Memory-bounded windowing over temporal/sequential point clouds (T, D).
- Generator-based lazy streaming to minimize memory footprint.
- Telemetry aggregation (peak memory, total runtime, rolling cycle metrics).
- Strict bounds checking against max_allowed_points_per_window.
"""
from __future__ import annotations

import hashlib
from typing import Generator, Sequence
import numpy as np

from .base import BaseTDABackend
from .registry import get_backend
from .types import (
    InputKind,
    ScientificStatus,
    StreamingTDAResult,
    StreamingWindowConfig,
    TDAConfig,
    TDAPersistenceResult,
)
from .validation import validate_point_cloud


def stream_point_cloud_generator(
    point_cloud: np.ndarray | Sequence[Sequence[float]],
    config: StreamingWindowConfig | None = None,
) -> Generator[tuple[tuple[int, int], TDAPersistenceResult], None, None]:
    """Yield persistent homology results lazily for each point cloud window."""
    cfg = config or StreamingWindowConfig()
    pts = validate_point_cloud(point_cloud)
    t_total, _ = pts.shape

    if cfg.window_size < 2:
        raise ValueError(f"window_size must be >= 2, got {cfg.window_size}")
    if cfg.window_size > cfg.max_allowed_points_per_window:
        raise ValueError(
            f"window_size ({cfg.window_size}) exceeds memory limit "
            f"max_allowed_points_per_window ({cfg.max_allowed_points_per_window})"
        )
    if cfg.step_size < 1:
        raise ValueError(f"step_size must be >= 1, got {cfg.step_size}")
    if t_total < cfg.window_size:
        raise ValueError(f"point_cloud length ({t_total}) is smaller than window_size ({cfg.window_size})")

    backend = get_backend(cfg.backend)
    tda_config = TDAConfig(
        max_edge_length=cfg.max_edge_length,
        max_dimension=1,
        compute_landscape=True,
        track_memory=True,
    )

    start = 0
    while start + cfg.window_size <= t_total:
        end = start + cfg.window_size
        window_pts = pts[start:end]
        res = backend.compute(window_pts, InputKind.POINT_CLOUD, tda_config)
        yield (start, end), res
        start += cfg.step_size


def stream_point_cloud_windows(
    point_cloud: np.ndarray | Sequence[Sequence[float]],
    config: StreamingWindowConfig | None = None,
) -> StreamingTDAResult:
    """Execute windowed persistent homology and return aggregate streaming summary."""
    cfg = config or StreamingWindowConfig()
    window_results: list[TDAPersistenceResult] = []
    window_ranges: list[tuple[int, int]] = []

    for rng, res in stream_point_cloud_generator(point_cloud, cfg):
        # Explicitly tag as streaming status
        res.scientific_status = ScientificStatus.BOUNDED_WINDOW_STREAMING
        window_ranges.append(rng)
        window_results.append(res)

    if not window_results:
        raise ValueError("No windows were processed.")

    b0_counts = [len(w.beta_0_intervals) for w in window_results]
    b1_counts = [len(w.beta_1_intervals) for w in window_results]
    runtimes = [w.runtime_seconds for w in window_results]
    mems = [w.memory_telemetry_bytes for w in window_results if w.memory_telemetry_bytes is not None]

    mean_b0 = float(np.mean(b0_counts))
    mean_b1 = float(np.mean(b1_counts))
    max_b1 = int(np.max(b1_counts))
    total_time = float(sum(runtimes))
    peak_mem = int(max(mems)) if mems else None

    # Cumulative deterministic checksum over window checksums
    combined_checksums = ",".join(w.deterministic_checksum for w in window_results)
    stream_checksum = hashlib.sha256(combined_checksums.encode("utf-8")).hexdigest()

    return StreamingTDAResult(
        window_results=window_results,
        window_ranges=window_ranges,
        mean_beta_0_count=mean_b0,
        mean_beta_1_count=mean_b1,
        max_beta_1_count=max_b1,
        peak_memory_bytes=peak_mem,
        total_runtime_seconds=total_time,
        deterministic_checksum=stream_checksum,
    )
