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
    batch_stream_covariance_parity,
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


def test_chunk_and_stride_configuration_rejects_non_integer_values():
    """Integer annotations are runtime contracts, not late slice-time failures."""
    invalid_configurations = (
        lambda: ChunkingPolicy(chunk_size=4.5),
        lambda: ChunkingPolicy(chunk_size=4.0),
        lambda: ChunkingPolicy(chunk_size=True),
        lambda: ChunkingPolicy(chunk_size="4"),
        lambda: ChunkingPolicy(chunk_size=4, stride=2.5),
        lambda: ChunkingPolicy(chunk_size=4, stride=2.0),
        lambda: ChunkingPolicy(chunk_size=4, stride=True),
        lambda: ChunkingPolicy(chunk_size=4, stride="2"),
        lambda: StreamBounds(max_chunk_samples=8.5, max_channels=2),
        lambda: StreamBounds(max_chunk_samples=8, max_channels=2.5),
        lambda: StreamBounds(max_chunk_samples=True, max_channels=2),
        lambda: StreamBounds(max_chunk_samples=8, max_channels="2"),
    )

    for make_config in invalid_configurations:
        with pytest.raises(StreamContractError, match="must be an integer"):
            make_config()


def test_stream_configuration_accepts_numpy_integer_scalars(bounds):
    """Reject ambiguous floats/bools without excluding NumPy's integer scalars."""
    policy = ChunkingPolicy(chunk_size=np.int64(4), stride=np.int32(2))
    assert policy.chunk_size == 4
    assert policy.stride == 2

    numpy_bounds = StreamBounds(
        max_chunk_samples=np.int64(8), max_channels=np.int32(4)
    )
    windows = list(
        iter_contract_windows(np.arange(8.0).reshape(8, 1), policy, numpy_bounds)
    )
    assert [(start, stop) for _, _, start, stop in windows] == [
        (0, 4),
        (2, 6),
        (4, 8),
    ]


def test_batch_parity_rejects_non_integer_chunk_sizes():
    with pytest.raises(StreamContractError, match="must be an integer"):
        batch_stream_covariance_parity(
            np.arange(8.0).reshape(4, 2), chunk_sizes=(2.5,)
        )


def test_batch_parity_rejects_zero_channel_array():
    with pytest.raises(EmptyInputError, match="channel"):
        batch_stream_covariance_parity(np.empty((4, 0)), chunk_sizes=(2,))


@pytest.mark.parametrize("signal", [np.empty((0, 2)), np.ones((1, 2))])
def test_batch_parity_rejects_too_few_samples(signal):
    with pytest.raises(EmptyInputError, match="at least 2 samples"):
        batch_stream_covariance_parity(signal, chunk_sizes=(1,))


def test_batch_parity_rejects_three_dimensional_signal():
    with pytest.raises(StreamContractError, match="2-D"):
        batch_stream_covariance_parity(np.zeros((4, 2, 1)), chunk_sizes=(2,))


def test_batch_parity_rejects_non_numeric_signal_dtype():
    signal = np.full((4, 2), "not-numeric")
    with pytest.raises(StreamContractError, match="float64"):
        batch_stream_covariance_parity(signal, chunk_sizes=(2,))


def test_batch_parity_rejects_ragged_signal_array():
    with pytest.raises(StreamContractError, match="signal"):
        batch_stream_covariance_parity([[1.0, 2.0], [3.0]], chunk_sizes=(1,))


@pytest.mark.parametrize("signal", [
    np.arange(24, dtype=np.int64).reshape(12, 2),
    np.arange(24, dtype=np.float32).reshape(12, 2),
])
def test_batch_parity_canonicalizes_real_numeric_input_dtype(signal):
    results = batch_stream_covariance_parity(signal, chunk_sizes=(1, 5, 12))
    assert all(ok and np.isfinite(diff) for _size, ok, diff in results), results


@pytest.mark.parametrize("chunk_sizes", [(), None])
def test_batch_parity_rejects_empty_or_missing_chunk_sizes(chunk_sizes):
    with pytest.raises(StreamContractError, match="chunk_sizes"):
        batch_stream_covariance_parity(np.arange(12.0).reshape(6, 2), chunk_sizes=chunk_sizes)


@pytest.mark.parametrize("atol,rtol", [
    (-1.0, 0.0),
    (0.0, -1.0),
    (np.nan, 0.0),
    (0.0, np.inf),
    ("1e-8", 0.0),
    (True, 0.0),
])
def test_batch_parity_rejects_invalid_tolerances(atol, rtol):
    with pytest.raises(StreamContractError, match="tolerance"):
        batch_stream_covariance_parity(
            np.arange(12.0).reshape(6, 2), chunk_sizes=(2,), atol=atol, rtol=rtol
        )
