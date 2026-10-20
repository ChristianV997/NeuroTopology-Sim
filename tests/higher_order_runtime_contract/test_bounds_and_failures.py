"""Explicit backpressure / size limits and fail-closed malformed paths."""
from __future__ import annotations

import numpy as np
import pytest

from tools.higher_order_runtime.stream_contract import (
    ChunkBoundError,
    ChunkingPolicy,
    EmptyInputError,
    StreamBounds,
    StreamContractError,
    StreamSession,
    iter_contract_windows,
)


def test_session_rejects_oversize_chunk_no_silent_truncation(bounds):
    session = StreamSession(n_channels=4, bounds=bounds, run_id="run-a")
    oversize = np.zeros((bounds.max_chunk_samples + 1, 4))
    with pytest.raises(ChunkBoundError, match="exceeds max_chunk_samples"):
        session.update(oversize)
    # State unchanged (no partial ingest / silent truncation).
    assert session.chunks_seen == 0
    assert session.samples_seen == 0


def test_session_rejects_empty_chunk(bounds):
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    with pytest.raises(EmptyInputError):
        session.update(np.zeros((0, 2)))


def test_session_rejects_non_finite_chunk(bounds):
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    bad = np.zeros((4, 2))
    bad[1, 0] = np.inf
    with pytest.raises(StreamContractError, match="non-finite"):
        session.update(bad)


def test_deterministic_replay_of_window_sequence(signal, timestamps, bounds):
    policy = ChunkingPolicy(chunk_size=6)
    a = list(iter_contract_windows(signal, policy, bounds, timestamps=timestamps))
    b = list(iter_contract_windows(signal, policy, bounds, timestamps=timestamps))
    assert len(a) == len(b)
    for (c1, t1, s1, e1), (c2, t2, s2, e2) in zip(a, b):
        np.testing.assert_array_equal(c1, c2)
        np.testing.assert_array_equal(t1, t2)
        assert (s1, e1) == (s2, e2)


def test_contract_error_is_not_scientific_pass():
    """A raised contract error is an engineering failure, never a validated result."""
    bounds = StreamBounds(max_chunk_samples=4, max_channels=2)
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    scientific_pass = False
    try:
        session.update(np.zeros((8, 2)))  # oversize
        scientific_pass = True  # unreachable if contract holds
    except ChunkBoundError:
        scientific_pass = False
    assert scientific_pass is False


def test_invalid_policy_rejected():
    with pytest.raises(StreamContractError):
        ChunkingPolicy(chunk_size=0)
    with pytest.raises(StreamContractError):
        ChunkingPolicy(chunk_size=8, stride=9)
    with pytest.raises(StreamContractError):
        StreamBounds(max_chunk_samples=0, max_channels=2)
