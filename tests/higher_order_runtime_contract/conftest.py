"""Synthetic-only fixtures for streaming contracts (no network, no datasets)."""
from __future__ import annotations

import numpy as np
import pytest

from tools.higher_order_runtime.stream_contract import ChunkingPolicy, StreamBounds


@pytest.fixture
def bounds() -> StreamBounds:
    return StreamBounds(max_chunk_samples=64, max_channels=8, allow_uneven_final=True)


@pytest.fixture
def signal() -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.standard_normal((40, 4)).astype(np.float64)


@pytest.fixture
def timestamps() -> np.ndarray:
    return np.arange(40, dtype=np.float64) * 0.002


@pytest.fixture
def tumbling() -> ChunkingPolicy:
    return ChunkingPolicy(chunk_size=8)
