"""Performance-contract tests for tools/streaming/bounded.py.

These assert *behavioral* guarantees (determinism, bounded memory, buffer reuse,
finite checks, chunk-size invariance within tolerance) rather than wall-clock
speed, so they are stable in CI. Synthetic fixtures are performance scaffolding
only, never scientific evidence.
"""
from __future__ import annotations

import numpy as np
import pytest

from tools.streaming import (
    MemoryTelemetry,
    StreamAggregate,
    bounded_stream,
    iter_chunks,
    iter_windows,
)


def _fixture(n=8000, c=6, seed=0):
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n, c)).astype(np.float64)


def test_deterministic_equality_same_chunk_size():
    sig = _fixture()
    a = bounded_stream(sig, 256)
    b = bounded_stream(sig, 256)
    assert np.array_equal(a.mean, b.mean)
    assert np.array_equal(a.variance, b.variance)
    assert a.checksum == b.checksum
    assert np.array_equal(a.minimum, b.minimum)
    assert np.array_equal(a.maximum, b.maximum)


def test_matches_full_array_reference_within_tolerance():
    sig = _fixture()
    r = bounded_stream(sig, 512)
    assert np.allclose(r.mean, sig.mean(axis=0), rtol=0, atol=1e-12)
    assert np.allclose(r.variance, sig.var(axis=0), rtol=0, atol=1e-10)
    assert np.allclose(r.minimum, sig.min(axis=0), rtol=0, atol=0)
    assert np.allclose(r.maximum, sig.max(axis=0), rtol=0, atol=0)
    assert abs(r.checksum - float(sig.sum())) <= 1e-6


@pytest.mark.parametrize("chunk", [1, 7, 64, 500, 8000])
def test_chunk_size_invariance_within_tolerance(chunk):
    sig = _fixture()
    ref = bounded_stream(sig, 8000)  # single chunk == full array
    r = bounded_stream(sig, chunk)
    # Mean/variance agree within a declared floating-point tolerance across
    # chunk sizes (summation grouping differs; no data dropped).
    assert np.allclose(r.mean, ref.mean, rtol=0, atol=1e-12)
    assert np.allclose(r.variance, ref.variance, rtol=0, atol=1e-9)
    assert np.array_equal(r.minimum, ref.minimum)   # min/max are exact
    assert np.array_equal(r.maximum, ref.maximum)


def test_history_suppressed_by_default_and_optional():
    sig = _fixture()
    assert bounded_stream(sig, 256).history is None
    r = bounded_stream(sig, 256, store_history=True)
    assert r.history is not None and len(r.history) == r.n_chunks


def test_buffer_reuse_single_work_buffer():
    sig = _fixture(n=4000, c=4)
    seen = set()

    def transform(chunk, out):
        base = out.base if out.base is not None else out
        seen.add(id(base))
        np.multiply(chunk, 3.0, out=out)
        return out

    bounded_stream(sig, 200, transform=transform)
    # Every chunk's transform output must reuse the same backing buffer.
    assert len(seen) == 1


def test_bounded_memory_peak_does_not_scale_with_chunks():
    sig = _fixture(n=40000, c=8)
    full = bounded_stream(sig, 40000, track_memory=True).peak_bytes
    chunked = bounded_stream(sig, 200, track_memory=True).peak_bytes
    assert isinstance(chunked, int) and isinstance(full, int)
    # Streaming in small chunks keeps a much smaller transient peak.
    assert chunked < full


def test_summaries_callback_bounded_output():
    sig = _fixture()
    r = bounded_stream(sig, 1000, summarize=lambda i, v: int(v.shape[0]))
    assert r.summaries is not None
    assert len(r.summaries) == r.n_chunks
    assert sum(r.summaries) == r.n_samples


def test_finite_check_raises_on_nan_and_inf():
    sig = _fixture()
    bad = sig.copy(); bad[3, 0] = np.nan
    with pytest.raises(ValueError):
        bounded_stream(bad, 100)
    bad2 = sig.copy(); bad2[9, 1] = np.inf
    with pytest.raises(ValueError):
        bounded_stream(bad2, 100)
    # With checking disabled it must not raise (opt-out is explicit).
    bounded_stream(bad, 100, check_finite=False)


def test_no_nan_inf_in_clean_aggregates():
    sig = _fixture()
    r = bounded_stream(sig, 333)
    for arr in (r.mean, r.variance, r.minimum, r.maximum):
        assert np.all(np.isfinite(arr))
    assert np.isfinite(r.checksum)


def test_memory_telemetry_reports_int_and_nests():
    with MemoryTelemetry() as outer:
        buf = np.empty((1000, 10), dtype=np.float64)
        with MemoryTelemetry() as inner:
            _ = buf * 2.0
        assert isinstance(inner.peak_bytes, int)
    assert isinstance(outer.peak_bytes, int)
    assert outer.peak_bytes >= 0


def test_iter_chunks_and_windows_shapes():
    sig = _fixture(n=1000, c=3)
    chunks = list(iter_chunks(sig, 256))
    assert [c.shape[0] for c in chunks] == [256, 256, 256, 232]
    assert all(c.shape[1] == 3 for c in chunks)
    wins = list(iter_windows(sig, 250))
    assert len(wins) == 4 and all(w.shape == (250, 3) for w in wins)
    # Overlapping windows via step.
    wins2 = list(iter_windows(sig, 250, step=125))
    assert len(wins2) == 7


def test_one_d_signal_supported():
    sig = _fixture(n=5000, c=1).ravel()
    r = bounded_stream(sig, 128)
    assert r.n_channels == 1
    assert np.allclose(r.mean, sig.mean(), atol=1e-12)


def test_invalid_arguments_rejected():
    sig = _fixture()
    with pytest.raises(ValueError):
        bounded_stream(sig, 0)
    with pytest.raises(ValueError):
        list(iter_chunks(sig, 0))
    with pytest.raises(ValueError):
        list(iter_windows(sig, 0))
    with pytest.raises(ValueError):
        bounded_stream(np.zeros((2, 2, 2)), 1)


def test_stream_aggregate_empty_is_zero():
    agg = StreamAggregate.empty(4)
    assert agg.count == 0
    assert np.array_equal(agg.variance, np.zeros(4))
