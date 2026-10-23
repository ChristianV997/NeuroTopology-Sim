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
    deterministic_accumulator_bytes,
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


@pytest.mark.parametrize("allow_uneven_final", [None, 0, 1, "false", np.int64(0)])
def test_uneven_final_setting_requires_a_boolean(allow_uneven_final):
    with pytest.raises(StreamContractError, match="allow_uneven_final"):
        StreamBounds(
            max_chunk_samples=8,
            max_channels=2,
            allow_uneven_final=allow_uneven_final,
        )


def test_uneven_final_setting_accepts_and_normalizes_numpy_boolean():
    bounds = StreamBounds(
        max_chunk_samples=8,
        max_channels=2,
        allow_uneven_final=np.bool_(False),
    )
    assert bounds.allow_uneven_final is False


@pytest.mark.parametrize("n_channels", [1.5, True, "2", None])
def test_session_channel_count_requires_positive_integer(n_channels, bounds):
    with pytest.raises(StreamContractError):
        StreamSession(n_channels=n_channels, bounds=bounds, run_id="run-a")


def test_session_channel_count_accepts_numpy_integer(bounds):
    session = StreamSession(n_channels=np.int64(2), bounds=bounds, run_id="run-a")
    assert session.n_channels == 2


@pytest.mark.parametrize("run_id", ["", 1, True, [], None])
def test_session_run_id_requires_nonempty_string(run_id, bounds):
    with pytest.raises(StreamContractError, match="run_id"):
        StreamSession(n_channels=2, bounds=bounds, run_id=run_id)


def test_session_reset_rejects_non_string_run_id_without_mutating_state(bounds):
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    session.update(np.ones((3, 2)))

    with pytest.raises(StreamContractError, match="run_id"):
        session.reset(42)

    assert session.run_id == "run-a"
    assert session.samples_seen == 3
    assert session.chunks_seen == 1


def test_session_update_rejects_array_run_id_without_mutating_state(bounds):
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    chunk = np.ones((3, 2))

    with pytest.raises(StreamContractError, match="run_id"):
        session.update(chunk, run_id=np.array(["run-a"]))

    assert session.run_id == "run-a"
    assert session.samples_seen == 0
    assert session.chunks_seen == 0


def test_session_rejects_invalid_bounds_object_as_contract_error():
    with pytest.raises(StreamContractError, match="bounds"):
        StreamSession(n_channels=2, bounds=None, run_id="run-a")


# --- regression coverage for public-API gaps found on current main (fuzz audit) ---


def test_extreme_magnitude_chunk_cannot_poison_accumulators_or_advance_state(bounds):
    """Finite samples can still overflow the running sums; that must fail closed."""
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    session.update(np.ones((3, 2)), timestamps=np.arange(3.0))
    before = (
        session.chunks_seen,
        session.samples_seen,
        session.last_timestamp,
        session.cov.matrix(ddof=0).copy(),
        session.summary.mean.copy(),
        session.summary.checksum,
    )

    with pytest.raises(StreamContractError, match="overflow|non-finite|representable"):
        session.update(np.full((4, 2), 1.7e308), timestamps=np.arange(10.0, 14.0))

    assert (session.chunks_seen, session.samples_seen, session.last_timestamp) == before[:3]
    np.testing.assert_array_equal(session.cov.matrix(ddof=0), before[3])
    np.testing.assert_array_equal(session.summary.mean, before[4])
    assert session.summary.checksum == before[5]
    # The session is still usable and finite after the rejected chunk.
    session.update(np.ones((2, 2)), timestamps=np.array([20.0, 21.0]))
    assert np.isfinite(session.cov.matrix()).all()


@pytest.mark.parametrize("value", [True, False, 2.5, float("inf"), None, "3", 0, -1, [3]])
def test_accumulator_bytes_rejects_malformed_channel_counts(value):
    with pytest.raises(StreamContractError):
        deterministic_accumulator_bytes(value)


@pytest.mark.parametrize("value", [True, 1.5, "8", None, 0])
def test_accumulator_bytes_rejects_malformed_itemsize(value):
    with pytest.raises(StreamContractError):
        deterministic_accumulator_bytes(3, value)


def test_accumulator_bytes_accepts_numpy_integers_and_is_exact():
    assert deterministic_accumulator_bytes(np.int64(3)) == 3 * 3 * 8 + 3 * 8 + 4 * 3 * 8


@pytest.mark.parametrize(
    "policy, bounds_value",
    [
        (None, "bounds"),
        ({"chunk_size": 4}, "bounds"),
        (4, "bounds"),
        ("policy", None),
        ("policy", {"max_chunk_samples": 8, "max_channels": 2}),
    ],
)
def test_window_iteration_rejects_wrong_config_types_with_contract_error(
    policy, bounds_value, bounds
):
    resolved_policy = ChunkingPolicy(4) if policy == "policy" else policy
    resolved_bounds = bounds if bounds_value == "bounds" else bounds_value
    with pytest.raises(StreamContractError):
        list(iter_contract_windows(np.ones((8, 2)), resolved_policy, resolved_bounds))


def test_window_configuration_errors_surface_at_call_time_not_first_next(bounds):
    """Bad configuration must fail when requested, not lazily on first iteration."""
    with pytest.raises(ChunkBoundError):
        iter_contract_windows(np.ones((8, 2)), ChunkingPolicy(bounds.max_chunk_samples + 1), bounds)
    with pytest.raises(StreamContractError):
        iter_contract_windows(np.ones((8, 2)), None, bounds)
