"""State reset (no cross-run leakage) and batch/stream numerical parity."""
from __future__ import annotations

import numpy as np
import pytest

from tools.higher_order_runtime.benchmark import WorkloadConfig, compute_bounded, compute_full, make_signal, verify_equivalence
from tools.higher_order_runtime.stream_contract import (
    ShapeContractError,
    StreamBounds,
    StreamContractError,
    StreamSession,
    batch_stream_covariance_parity,
    deterministic_accumulator_bytes,
)


def test_reset_clears_state_between_independent_runs(bounds):
    session = StreamSession(n_channels=3, bounds=bounds, run_id="sub-01")
    a = np.ones((8, 3))
    session.update(a)
    assert session.samples_seen == 8
    assert session.summary.checksum == float(a.sum())

    session.reset("sub-02")
    assert session.run_id == "sub-02"
    assert session.chunks_seen == 0
    assert session.samples_seen == 0
    assert session.summary.checksum == 0.0
    assert session.cov.count == 0
    assert session.last_timestamp is None

    b = np.full((5, 3), 2.0)
    session.update(b)
    assert session.samples_seen == 5
    assert session.summary.checksum == float(b.sum())
    # No leakage from sub-01's ones into sub-02's checksum.
    assert session.summary.checksum != float(a.sum() + b.sum())


def test_run_id_mismatch_without_reset_fails_closed(bounds):
    session = StreamSession(n_channels=2, bounds=bounds, run_id="run-a")
    session.update(np.zeros((3, 2)))
    with pytest.raises(StreamContractError, match="run_id mismatch"):
        session.update(np.zeros((3, 2)), run_id="run-b")


def test_covariance_parity_chunk_sizes_1_short_uneven_exact():
    rng = np.random.default_rng(1)
    x = rng.standard_normal((120, 6))
    # 1, short(7), uneven rem vs 120, exact divisor(10), full(120)
    results = batch_stream_covariance_parity(
        x, chunk_sizes=(1, 7, 11, 10, 120), atol=1e-8, rtol=0.0
    )
    assert all(ok for _size, ok, _diff in results), results
    assert all(diff <= 1e-8 for _size, _ok, diff in results)


def test_bounded_vs_full_feature_parity_declared_tolerance():
    """Where batch and streaming are mathematically expected to agree, check 1e-9."""
    cfg = WorkloadConfig(
        n_samples=4096,
        n_channels=8,
        seed=2,
        segment_len=256,
        candidate_limit=20,
        surrogate_limit=6,
    )
    signal = make_signal(cfg)
    full = compute_full(signal, cfg)
    for chunk in (1, 64, 333, 1024, 4096):
        bounded = compute_bounded(signal, cfg, chunk_size=chunk)
        rep = verify_equivalence(full, bounded, tolerance=1e-9)
        assert rep.equivalent, (chunk, rep.to_dict())


def test_deterministic_accumulator_bytes_scales_with_channels():
    b4 = deterministic_accumulator_bytes(4)
    b8 = deterministic_accumulator_bytes(8)
    assert b4 > 0 and b8 > b4
    # O(C^2) dominant term: 8-channel cov is 4x 4-channel cov block.
    assert b8 >= 4 * (4 * 4 * 8)


def test_overlap_not_claimed_as_batch_window_independence():
    """Documented non-equivalence: overlap is a streaming view, not a batch rewrite."""
    from tools.higher_order_runtime.stream_contract import ChunkingPolicy

    policy = ChunkingPolicy(chunk_size=16, stride=8)
    assert policy.overlapping is True
    # Contract docs: do not claim overlap windows == independent batch partitions.
    assert policy.warmup_samples == 8


def test_batch_parity_rejects_oned_signal_like_the_stream_path():
    """Regression: batch parity must not reshape a 1-D signal into one channel.

    ``StreamSession.update`` and ``iter_contract_windows`` reject 1-D input, so the
    batch reference must refuse the same layout instead of returning a verdict.
    """
    with pytest.raises(ShapeContractError, match="2-D"):
        batch_stream_covariance_parity(np.arange(10.0), chunk_sizes=(5,))


def test_batch_parity_rejects_complex_signal():
    """Regression: complex input must fail closed rather than drop its imaginary part."""
    with pytest.raises(StreamContractError, match="real-valued"):
        batch_stream_covariance_parity(np.full((10, 2), 1.0 + 2.0j), chunk_sizes=(5,))
