"""Chunk sizes, ordering, warm-up/overlap, and end-of-stream contracts."""
from __future__ import annotations

import numpy as np
import pytest

from tools.higher_order_runtime.bounded import iter_spectral_segments
from tools.higher_order_runtime.stream_contract import (
    ChunkBoundError,
    ChunkingPolicy,
    StreamBounds,
    iter_contract_windows,
)


def test_chunk_size_one_preserves_all_samples(signal, bounds):
    windows = list(iter_contract_windows(signal, ChunkingPolicy(1), bounds))
    assert len(windows) == signal.shape[0]
    reconstructed = np.vstack([w[0] for w in windows])
    np.testing.assert_array_equal(reconstructed, signal)


@pytest.mark.parametrize("chunk_size", [5, 8, 10, 40])
def test_short_uneven_and_exact_divisor_coverage(signal, bounds, chunk_size):
    """short (5), exact divisor (8/40), and uneven remainder (10) are all explicit."""
    windows = list(iter_contract_windows(signal, ChunkingPolicy(chunk_size), bounds))
    starts = [w[2] for w in windows]
    stops = [w[3] for w in windows]
    assert starts == sorted(starts)
    assert starts[0] == 0
    assert stops[-1] == signal.shape[0]
    lengths = [w[0].shape[0] for w in windows]
    if signal.shape[0] % chunk_size == 0:
        assert set(lengths) == {chunk_size}
    else:
        assert lengths[-1] == signal.shape[0] % chunk_size
        assert all(length == chunk_size for length in lengths[:-1])


def test_timestamp_continuity_with_chunks(signal, timestamps, bounds):
    windows = list(
        iter_contract_windows(signal, ChunkingPolicy(7), bounds, timestamps=timestamps)
    )
    # Ordering + continuity: each window's last ts < next window's first ts
    # for non-overlapping tumbling (adjacent but strictly increasing overall).
    prev_last = None
    for chunk, chunk_ts, start, stop in windows:
        assert chunk_ts is not None
        assert chunk_ts.shape[0] == chunk.shape[0]
        np.testing.assert_array_equal(chunk_ts, timestamps[start:stop])
        if prev_last is not None:
            assert chunk_ts[0] > prev_last
        prev_last = float(chunk_ts[-1])


def test_overlap_warmup_is_explicit(signal, bounds):
    policy = ChunkingPolicy(chunk_size=8, stride=5)
    assert policy.overlapping is True
    assert policy.warmup_samples == 3
    windows = list(iter_contract_windows(signal, policy, bounds))
    assert windows[0][2] == 0 and windows[0][3] == 8
    assert windows[1][2] == 5 and windows[1][3] == 13
    # Warm-up overlap region is identical across consecutive windows.
    np.testing.assert_array_equal(windows[0][0][5:], windows[1][0][:3])


def test_overlap_end_of_stream_does_not_pad(signal, bounds):
    policy = ChunkingPolicy(chunk_size=16, stride=10)
    windows = list(iter_contract_windows(signal, policy, bounds))
    # Last full window must be complete; no zero-padded remainder.
    assert all(w[0].shape[0] == 16 for w in windows)
    last_stop = windows[-1][3]
    assert last_stop + policy.effective_stride > signal.shape[0] or last_stop <= signal.shape[0]
    # Remainder after last full window is not fabricated.
    assert last_stop <= signal.shape[0]


def test_uneven_final_rejected_when_disabled(signal):
    bounds = StreamBounds(max_chunk_samples=64, max_channels=8, allow_uneven_final=False)
    with pytest.raises(ChunkBoundError, match="uneven finals are disabled"):
        list(iter_contract_windows(signal, ChunkingPolicy(chunk_size=9), bounds))


def test_spectral_incomplete_tail_dropped_not_padded():
    """Existing spectral iterator drops incomplete tails; padding would change power."""
    x = np.arange(25, dtype=np.float64).reshape(25, 1)
    segs = list(iter_spectral_segments(x, segment_len=8))
    assert len(segs) == 3  # samples 0..23; sample 24 dropped
    assert all(seg.shape[0] == 8 for seg in segs)


def test_oversize_chunk_policy_rejected(signal, bounds):
    with pytest.raises(ChunkBoundError, match="exceeds max_chunk_samples"):
        list(iter_contract_windows(signal, ChunkingPolicy(chunk_size=65), bounds))


def test_stride_none_matches_explicit_nonoverlap(signal, bounds):
    """Regression: ``stride is None`` must equal ``stride == chunk_size`` tumbling."""
    tumbling = list(iter_contract_windows(signal, ChunkingPolicy(chunk_size=8), bounds))
    explicit = list(
        iter_contract_windows(signal, ChunkingPolicy(chunk_size=8, stride=8), bounds)
    )
    assert [(w[2], w[3], w[0].shape) for w in tumbling] == [
        (w[2], w[3], w[0].shape) for w in explicit
    ]
    np.testing.assert_array_equal(tumbling[0][0], explicit[0][0])


def test_overlap_remainder_not_emitted_even_when_uneven_final_allowed(signal):
    """Overlap mode must not emit a short final window even if uneven finals are on."""
    bounds = StreamBounds(max_chunk_samples=64, max_channels=8, allow_uneven_final=True)
    policy = ChunkingPolicy(chunk_size=16, stride=10)
    windows = list(iter_contract_windows(signal, policy, bounds))
    assert windows
    assert all(w[0].shape[0] == 16 for w in windows)
    assert windows[-1][3] < signal.shape[0] or windows[-1][3] == signal.shape[0]
    # If a remainder exists below chunk_size, it was dropped (not padded).
    remainder = signal.shape[0] - windows[-1][3]
    if remainder:
        assert remainder < policy.chunk_size


def test_overlap_tail_refused_when_uneven_finals_disabled():
    """Regression: overlap mode must not silently drop samples past the last full window.

    n=40, chunk=16, stride=10 leaves samples 36..39 uncovered. With uneven finals
    disabled the contract says a short remainder raises, so this must not pass.
    """
    bounds = StreamBounds(max_chunk_samples=64, max_channels=8, allow_uneven_final=False)
    x = np.zeros((40, 2))
    with pytest.raises(ChunkBoundError, match="uneven finals are disabled"):
        list(iter_contract_windows(x, ChunkingPolicy(chunk_size=16, stride=10), bounds))


def test_overlap_without_tail_accepted_when_uneven_finals_disabled():
    """Positive control: when the last full window ends at n, nothing is left over."""
    bounds = StreamBounds(max_chunk_samples=64, max_channels=8, allow_uneven_final=False)
    x = np.zeros((36, 2))
    windows = list(iter_contract_windows(x, ChunkingPolicy(chunk_size=16, stride=10), bounds))
    assert [(w[2], w[3]) for w in windows] == [(0, 16), (10, 26), (20, 36)]
