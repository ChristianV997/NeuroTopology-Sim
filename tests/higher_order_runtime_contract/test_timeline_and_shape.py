"""Timestamp, empty/malformed input, and channel-shape contracts."""
from __future__ import annotations

import numpy as np
import pytest

from tools.higher_order_runtime.stream_contract import (
    ChunkBoundError,
    ChunkingPolicy,
    EmptyInputError,
    ShapeContractError,
    StreamContractError,
    StreamSession,
    TimelineContractError,
    batch_stream_covariance_parity,
    iter_contract_windows,
    validate_signal_shape,
    validate_timestamps,
)


def test_validate_timestamps_happy(timestamps):
    got = validate_timestamps(timestamps, n_samples=timestamps.shape[0])
    np.testing.assert_array_equal(got, timestamps)


def test_non_monotonic_timestamps_rejected(timestamps):
    bad = timestamps.copy()
    bad[10] = bad[9]  # repeated sample time
    with pytest.raises(TimelineContractError, match="strictly monotonic"):
        validate_timestamps(bad, n_samples=bad.shape[0])


def test_reversed_timestamps_rejected(timestamps):
    bad = timestamps[::-1].copy()
    with pytest.raises(TimelineContractError, match="strictly monotonic"):
        validate_timestamps(bad, n_samples=bad.shape[0])


def test_non_finite_timestamps_rejected(timestamps):
    bad = timestamps.copy()
    bad[3] = np.nan
    with pytest.raises(TimelineContractError, match="non-finite"):
        validate_timestamps(bad, n_samples=bad.shape[0])


def test_timestamp_length_mismatch_rejected(signal, timestamps, bounds):
    with pytest.raises(TimelineContractError, match="timestamp length"):
        list(
            iter_contract_windows(
                signal, ChunkingPolicy(8), bounds, timestamps=timestamps[:-1]
            )
        )


def test_empty_signal_rejected(bounds):
    with pytest.raises(EmptyInputError):
        list(iter_contract_windows(np.zeros((0, 4)), ChunkingPolicy(4), bounds))


def test_malformed_rank3_rejected(bounds):
    with pytest.raises(ShapeContractError):
        list(iter_contract_windows(np.zeros((5, 2, 2)), ChunkingPolicy(2), bounds))


def test_oned_chunk_layout_rejected(bounds):
    """Array layout contract: chunks must be 2-D (samples, channels), not a flat vector."""
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    with pytest.raises(ShapeContractError, match="2-D"):
        session.update(np.zeros(8, dtype=np.float64))


def test_oned_signal_rejected_by_iter_contract_windows(bounds):
    """Regression: windowing must not silently reshape 1-D signals to (n, 1).

    ``StreamSession.update`` already rejects ndim != 2. ``iter_contract_windows``
    must use the same layout contract so batch windowing and session ingest agree.
    """
    with pytest.raises(ShapeContractError, match="2-D"):
        list(iter_contract_windows(np.zeros(8, dtype=np.float64), ChunkingPolicy(4), bounds))


def test_column_permutation_is_caller_owned_not_identity_checked(bounds):
    """Same channel count with swapped columns is accepted; identity is caller-owned."""
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    a = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    session.update(a)
    session.update(a[:, ::-1])
    assert session.chunks_seen == 2


def test_channel_count_change_mid_stream_rejected(bounds):
    session = StreamSession(n_channels=4, bounds=bounds, run_id="run-a")
    session.update(np.zeros((4, 4)))
    with pytest.raises(ShapeContractError, match="channel count changed"):
        session.update(np.zeros((4, 3)))


def test_too_many_channels_rejected(bounds):
    with pytest.raises(ChunkBoundError, match="max_channels"):
        list(iter_contract_windows(np.zeros((10, 16)), ChunkingPolicy(4), bounds))

def test_session_rejects_timeline_gap(bounds):
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    session.update(np.zeros((4, 2)), timestamps=np.array([0.0, 0.1, 0.2, 0.3]))
    with pytest.raises(TimelineContractError, match="not continuous"):
        session.update(np.zeros((2, 2)), timestamps=np.array([0.3, 0.4]))  # not > last


def test_complex_signal_rejected_not_silently_cast(bounds):
    """Regression: complex chunks must fail closed; casting would discard imaginary parts."""
    z = np.full((8, 2), 1.0 + 5.0j)
    with pytest.raises(StreamContractError, match="real-valued"):
        list(iter_contract_windows(z, ChunkingPolicy(4), bounds))
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    with pytest.raises(StreamContractError, match="real-valued"):
        session.update(z[:4])
    assert session.samples_seen == 0


def test_complex_timestamps_rejected_not_silently_cast():
    """Regression: complex timestamps must fail closed, not lose their imaginary part."""
    ts = np.array([0.0, 1.0, 2.0]) + 1j * np.array([0.0, 5.0, 9.0])
    with pytest.raises(TimelineContractError, match="real-valued"):
        validate_timestamps(ts, n_samples=3)


def test_ragged_timestamp_input_raises_contract_error_not_numpy_value_error():
    with pytest.raises(TimelineContractError, match="timestamps"):
        validate_timestamps([[0.0], [1.0, 2.0]], n_samples=2)


def test_timestamp_cast_overflow_cannot_return_nonfinite_validated_values():
    timestamps = np.array([0.0, np.longdouble("1e400")], dtype=np.longdouble)
    with pytest.raises(TimelineContractError, match="timestamps|float64"):
        validate_timestamps(timestamps, n_samples=2)


def test_timestamp_gap_is_allowed_when_order_remains_strictly_increasing(bounds):
    """The contract requires monotonicity, not an invented fixed sampling interval."""
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    session.update(np.zeros((2, 2)), timestamps=np.array([0.0, 0.1]))
    session.update(np.ones((2, 2)), timestamps=np.array([0.5, 0.6]))
    assert session.last_timestamp == 0.6


def test_rejected_timestamp_chunk_does_not_advance_session_state(bounds):
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    session.update(np.ones((2, 2)), timestamps=np.array([0.0, 0.1]))

    with pytest.raises(TimelineContractError):
        session.update(np.full((2, 2), 2.0), timestamps=np.array([0.1, 0.2]))

    assert session.samples_seen == 2
    assert session.chunks_seen == 1
    assert session.last_timestamp == 0.1
    assert session.summary.checksum == 4.0


@pytest.mark.parametrize(
    "values",
    [
        np.array([["1.0", "2.0"], ["3.0", "4.0"]]),
        np.array([[b"1", b"2"], [b"3", b"4"]]),
        np.array([[np.datetime64("2020-01-01")] * 2] * 2),
        np.array([[np.timedelta64(1, "s")] * 2] * 2),
        np.array([["1.0", 2.0], [3.0, 4.0]], dtype=object),
    ],
    ids=["str", "bytes", "datetime64", "timedelta64", "object-with-str"],
)
def test_non_numeric_signal_dtypes_are_rejected_not_cast_to_float(values, bounds):
    with pytest.raises(StreamContractError, match="numeric"):
        validate_signal_shape(values, max_channels=bounds.max_channels)
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    with pytest.raises(StreamContractError, match="numeric"):
        session.update(values)
    assert session.samples_seen == 0 and session.chunks_seen == 0
    with pytest.raises(StreamContractError, match="numeric"):
        batch_stream_covariance_parity(np.vstack([values, values]), chunk_sizes=[1])
