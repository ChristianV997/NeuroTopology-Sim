"""Tests for null-control surrogate transforms."""
from __future__ import annotations

import numpy as np
import pytest

from validation.nulls import (
    channel_shuffle,
    compute_null_summary,
    phase_randomize_time,
    time_reverse,
)


# ── channel_shuffle ──────────────────────────────────────────────────────────

def test_channel_shuffle_preserves_shape():
    data = np.arange(40).reshape(4, 10).astype(float)
    out = channel_shuffle(data, seed=0)
    assert out.shape == data.shape
    assert np.all(np.isfinite(out))


def test_channel_shuffle_deterministic():
    rng = np.random.default_rng(0)
    data = rng.standard_normal((6, 32))
    a = channel_shuffle(data, seed=42)
    b = channel_shuffle(data, seed=42)
    assert np.array_equal(a, b)


def test_channel_shuffle_changes_order_when_possible():
    data = np.arange(32).reshape(8, 4).astype(float)
    out = channel_shuffle(data, seed=1)
    # With 8 channels, seed=1 must yield a non-identity permutation
    assert not np.array_equal(out, data)
    # Channel content (sorted by row sum) is preserved
    orig_sums = sorted(data.sum(axis=1).tolist())
    out_sums = sorted(out.sum(axis=1).tolist())
    assert orig_sums == out_sums


def test_channel_shuffle_requires_2d():
    with pytest.raises(ValueError):
        channel_shuffle(np.zeros(10))


# ── time_reverse ─────────────────────────────────────────────────────────────

def test_time_reverse_reverses_samples():
    data = np.arange(20).reshape(2, 10).astype(float)
    out = time_reverse(data)
    assert out.shape == data.shape
    assert np.array_equal(out[:, 0], data[:, -1])
    assert np.array_equal(out[:, -1], data[:, 0])


def test_time_reverse_idempotent_twice():
    rng = np.random.default_rng(2)
    data = rng.standard_normal((3, 16))
    out = time_reverse(time_reverse(data))
    assert np.array_equal(out, data)


def test_time_reverse_requires_2d():
    with pytest.raises(ValueError):
        time_reverse(np.zeros(10))


# ── phase_randomize_time ─────────────────────────────────────────────────────

def test_phase_randomize_preserves_shape_and_finite():
    rng = np.random.default_rng(3)
    data = rng.standard_normal((4, 256))
    out = phase_randomize_time(data, seed=0)
    assert out.shape == data.shape
    assert np.all(np.isfinite(out))


def test_phase_randomize_preserves_amplitude_spectrum():
    rng = np.random.default_rng(4)
    data = rng.standard_normal((3, 256))
    out = phase_randomize_time(data, seed=0)
    obs_mag = np.abs(np.fft.rfft(data, axis=-1))
    out_mag = np.abs(np.fft.rfft(out, axis=-1))
    assert np.allclose(obs_mag, out_mag, atol=1e-6)


def test_phase_randomize_deterministic_with_seed():
    rng = np.random.default_rng(5)
    data = rng.standard_normal((2, 128))
    a = phase_randomize_time(data, seed=7)
    b = phase_randomize_time(data, seed=7)
    assert np.array_equal(a, b)


def test_phase_randomize_requires_2d():
    with pytest.raises(ValueError):
        phase_randomize_time(np.zeros(64))


# ── compute_null_summary ─────────────────────────────────────────────────────

def test_null_summary_keys_and_values():
    summary = compute_null_summary(observed=2.0, null_values=[0.0, 1.0, 2.0, 3.0])
    expected = {"observed", "null_mean", "null_std", "z", "n_nulls"}
    assert expected.issubset(summary.keys())
    assert summary["n_nulls"] == 4
    assert summary["null_mean"] == pytest.approx(1.5)
    assert np.isfinite(summary["z"])


def test_null_summary_handles_empty():
    summary = compute_null_summary(observed=1.0, null_values=[])
    assert summary["n_nulls"] == 0
    assert np.isnan(summary["null_mean"])
    assert np.isnan(summary["null_std"])
    assert np.isnan(summary["z"])


def test_null_summary_zero_std_returns_nan_z():
    summary = compute_null_summary(observed=1.0, null_values=[2.0, 2.0, 2.0])
    assert summary["null_std"] == 0.0
    assert np.isnan(summary["z"])
