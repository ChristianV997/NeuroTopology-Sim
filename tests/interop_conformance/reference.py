"""Reference data structures and synthetic adapter for conformance testing.

Enables full self-testing of the 16 contract rules even when external PRs
(PR #212, #214, #220) are tested independently or in environments where they
have not yet been merged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterator, Sequence
import numpy as np


@dataclass
class ConformingSignalChunk:
    data: np.ndarray
    timestamps: np.ndarray
    sample_rate_hz: float
    channel_names: tuple[str, ...]
    units: tuple[str, ...]
    source_sha256: str
    source_id: str = "synthetic_ref"
    recording_id: str = "rec_001"
    chunk_index: int = 0
    start_sample: int = 0
    dropped_samples: int = 0
    montage_name: str | None = None
    montage_coordinates: list[list[float]] | None = None
    warnings: list[str] = field(default_factory=list)


def create_synthetic_chunk(
    channels: int = 4,
    samples: int = 100,
    sample_rate: float = 200.0,
    has_coordinates: bool = True,
    channel_names: Sequence[str] | None = None,
    units: Sequence[str] | None = None,
    chunk_index: int = 0,
    start_sample: int = 0,
) -> ConformingSignalChunk:
    data = np.zeros((channels, samples), dtype=np.float64)
    # deterministic non-zero values
    for ch in range(channels):
        data[ch] = np.sin(2 * np.pi * 10.0 * np.arange(samples) / sample_rate) + ch
    
    t0 = start_sample / sample_rate
    timestamps = t0 + np.arange(samples, dtype=np.float64) / sample_rate
    
    names = tuple(channel_names) if channel_names else tuple(f"EEG_{i+1}" for i in range(channels))
    u = tuple(units) if units else tuple("uV" for _ in range(channels))
    
    coords = None
    montage_name = None
    if has_coordinates:
        montage_name = "standard_1020"
        coords = [[float(i) * 0.01, float(i) * 0.02, 0.05] for i in range(channels)]
        
    return ConformingSignalChunk(
        data=data,
        timestamps=timestamps,
        sample_rate_hz=sample_rate,
        channel_names=names,
        units=u,
        source_sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        chunk_index=chunk_index,
        start_sample=start_sample,
        montage_name=montage_name,
        montage_coordinates=coords,
    )


def synthetic_conforming_adapter(
    source_input: Any,
    chunk_seconds: float = 1.0,
    total_seconds: float = 2.0,
    sample_rate: float = 200.0,
    channels: int = 4,
) -> Iterator[ConformingSignalChunk]:
    """An idealized adapter yielding strictly conforming signal chunks."""
    win_samples = int(chunk_seconds * sample_rate)
    total_samples = int(total_seconds * sample_rate)
    n_chunks = total_samples // win_samples
    
    for i in range(n_chunks):
        yield create_synthetic_chunk(
            channels=channels,
            samples=win_samples,
            sample_rate=sample_rate,
            chunk_index=i,
            start_sample=i * win_samples,
        )
