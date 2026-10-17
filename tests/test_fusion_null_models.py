"""Tests for structure-sensitive null models in cross-modal fusion."""
from __future__ import annotations

import numpy as np
import pytest

from dual_engine.fusion_validation import (
    NullModelType,
    audit_null_model,
    block_permutation,
    compute_data_identity,
    independent_shuffle_null,
    label_permutation,
    matched_autocorrelation_null,
    matched_variance_null,
    phase_randomize_embeddings,
)


@pytest.fixture
def synthetic_multivariate_timeseries() -> np.ndarray:
    """Multivariate time series with known temporal autocorrelation and cross-channel covariance."""
    rng = np.random.default_rng(42)
    n_samples, n_dims = 200, 8
    # Shared underlying factor + private AR(1) dynamics
    shared_factor = np.sin(np.linspace(0, 8 * np.pi, n_samples))
    series = np.zeros((n_samples, n_dims))

    for d in range(n_dims):
        coupling = 0.5 * (d + 1) / n_dims
        ar = np.zeros(n_samples)
        innov = rng.normal(0, 0.5, n_samples)
        for t in range(1, n_samples):
            ar[t] = 0.7 * ar[t - 1] + innov[t]
        series[:, d] = coupling * shared_factor + ar + (d * 1.5)

    return series


class TestPhaseRandomization:
    """Test spectral phase-randomized surrogate properties."""

    def test_magnitude_spectrum_preservation(self, synthetic_multivariate_timeseries: np.ndarray):
        surrogate = phase_randomize_embeddings(synthetic_multivariate_timeseries, seed=42)

        assert surrogate.shape == synthetic_multivariate_timeseries.shape
        assert np.isrealobj(surrogate)

        for d in range(synthetic_multivariate_timeseries.shape[1]):
            orig_mag = np.abs(np.fft.fft(synthetic_multivariate_timeseries[:, d]))
            surr_mag = np.abs(np.fft.fft(surrogate[:, d]))
            # Preserved up to floating point precision
            assert np.allclose(orig_mag, surr_mag, atol=1e-10)

    def test_cross_channel_phase_disruption(self, synthetic_multivariate_timeseries: np.ndarray):
        surrogate = phase_randomize_embeddings(synthetic_multivariate_timeseries, seed=42)

        orig_corr = np.corrcoef(synthetic_multivariate_timeseries.T)
        surr_corr = np.corrcoef(surrogate.T)

        # Cross-channel correlation must be disrupted
        diff_norm = np.linalg.norm(orig_corr - surr_corr)
        assert diff_norm > 0.5

    def test_deterministic_seeding(self, synthetic_multivariate_timeseries: np.ndarray):
        s1 = phase_randomize_embeddings(synthetic_multivariate_timeseries, seed=123)
        s2 = phase_randomize_embeddings(synthetic_multivariate_timeseries, seed=123)
        s3 = phase_randomize_embeddings(synthetic_multivariate_timeseries, seed=456)

        assert np.array_equal(s1, s2)
        assert not np.array_equal(s1, s3)


class TestLabelPermutation:
    """Test condition label permutation null properties."""

    def test_marginal_counts_preserved(self):
        labels = np.array([0] * 35 + [1] * 65)
        perm = label_permutation(labels, seed=42)

        assert len(perm) == len(labels)
        assert np.sum(perm == 0) == 35
        assert np.sum(perm == 1) == 65

    def test_label_order_shuffled(self):
        labels = np.array([0] * 50 + [1] * 50)
        perm = label_permutation(labels, seed=42)

        # Labels must not remain identical in sequential position
        assert not np.array_equal(perm, labels)


class TestBlockPermutation:
    """Test block permutation null properties."""

    def test_intra_block_sequence_preserved(self, synthetic_multivariate_timeseries: np.ndarray):
        block_size = 20
        perm = block_permutation(synthetic_multivariate_timeseries, block_size=block_size, seed=42)

        assert perm.shape == synthetic_multivariate_timeseries.shape

        # Verify that within any non-edge contiguous chunk of size block_size - 1,
        # consecutive differences match some original block differences
        orig_diffs = np.diff(synthetic_multivariate_timeseries, axis=0)
        perm_diffs = np.diff(perm, axis=0)

        # At least 80% of step differences must match because transitions only occur at block boundaries
        matches = 0
        total = len(perm_diffs)
        for i in range(total):
            # Check if this diff exists in original diffs at the corresponding relative index
            if np.any(np.all(np.isclose(orig_diffs, perm_diffs[i], atol=1e-10), axis=1)):
                matches += 1

        assert matches / total > 0.85

    def test_deterministic_block_seeding(self, synthetic_multivariate_timeseries: np.ndarray):
        b1 = block_permutation(synthetic_multivariate_timeseries, block_size=15, seed=7)
        b2 = block_permutation(synthetic_multivariate_timeseries, block_size=15, seed=7)
        b3 = block_permutation(synthetic_multivariate_timeseries, block_size=15, seed=8)

        assert np.array_equal(b1, b2)
        assert not np.array_equal(b1, b3)


class TestMatchedVarianceNull:
    """Test matched-variance Gaussian surrogate null properties."""

    def test_mean_and_variance_preservation(self, synthetic_multivariate_timeseries: np.ndarray):
        # Using larger n for statistical stability of moments
        rng = np.random.default_rng(10)
        large_data = rng.normal(loc=3.5, scale=2.1, size=(2000, 4))
        surr = matched_variance_null(large_data, seed=42)

        assert surr.shape == large_data.shape
        orig_mean = np.mean(large_data, axis=0)
        surr_mean = np.mean(surr, axis=0)
        assert np.allclose(orig_mean, surr_mean, atol=0.2)

        orig_var = np.var(large_data, axis=0, ddof=1)
        surr_var = np.var(surr, axis=0, ddof=1)
        assert np.allclose(orig_var, surr_var, rtol=0.2)

    def test_covariance_and_autocorrelation_destroyed(self, synthetic_multivariate_timeseries: np.ndarray):
        surr = matched_variance_null(synthetic_multivariate_timeseries, seed=42)

        # Lag-1 autocorrelation of surrogate should drop toward zero
        for d in range(synthetic_multivariate_timeseries.shape[1]):
            c_orig = np.corrcoef(synthetic_multivariate_timeseries[:-1, d],
                                 synthetic_multivariate_timeseries[1:, d])[0, 1]
            c_surr = np.corrcoef(surr[:-1, d], surr[1:, d])[0, 1]
            # Original series had positive autocorrelation ~0.7
            assert c_orig > 0.5
            # Matched variance surrogate has near zero autocorrelation
            assert abs(c_surr) < 0.25


class TestMatchedAutocorrelationNull:
    """Test stationary AR(1) surrogate null properties."""

    def test_autocorrelation_preservation(self, synthetic_multivariate_timeseries: np.ndarray):
        surr = matched_autocorrelation_null(synthetic_multivariate_timeseries, seed=42)

        assert surr.shape == synthetic_multivariate_timeseries.shape

        for d in range(synthetic_multivariate_timeseries.shape[1]):
            orig_c1 = np.corrcoef(synthetic_multivariate_timeseries[:-1, d],
                                  synthetic_multivariate_timeseries[1:, d])[0, 1]
            surr_c1 = np.corrcoef(surr[:-1, d], surr[1:, d])[0, 1]
            # AR(1) surrogate preserves lag-1 correlation within sample tolerance
            assert abs(orig_c1 - surr_c1) < 0.35


class TestIndependentShuffleNull:
    """Test independent feature dimension shuffling null properties."""

    def test_marginal_distributions_identical(self, synthetic_multivariate_timeseries: np.ndarray):
        surr = independent_shuffle_null(synthetic_multivariate_timeseries, seed=42)

        assert surr.shape == synthetic_multivariate_timeseries.shape

        # Every feature dimension must contain the exact same set of values, just reordered
        for d in range(synthetic_multivariate_timeseries.shape[1]):
            assert np.array_equal(
                np.sort(synthetic_multivariate_timeseries[:, d]),
                np.sort(surr[:, d]),
            )

    def test_multivariate_covariance_destroyed(self, synthetic_multivariate_timeseries: np.ndarray):
        surr = independent_shuffle_null(synthetic_multivariate_timeseries, seed=42)

        corr_orig = np.corrcoef(synthetic_multivariate_timeseries.T)
        corr_surr = np.corrcoef(surr.T)

        # Off-diagonal correlations should collapse toward zero
        np.fill_diagonal(corr_orig, 0)
        np.fill_diagonal(corr_surr, 0)

        assert np.mean(np.abs(corr_surr)) < np.mean(np.abs(corr_orig))


class TestNullModelAuditAndDataIdentity:
    """Test diagnostic null model auditing and deterministic identity hashing."""

    def test_audit_null_model(self, synthetic_multivariate_timeseries: np.ndarray):
        audit_phase = audit_null_model(synthetic_multivariate_timeseries, NullModelType.PHASE_RANDOMIZE)
        assert audit_phase["passed_audit"] is True
        assert audit_phase["preserves_magnitude_spectrum"] is True

        audit_shuffle = audit_null_model(synthetic_multivariate_timeseries, NullModelType.INDEPENDENT_SHUFFLE)
        assert audit_shuffle["passed_audit"] is True
        assert audit_shuffle["preserves_exact_marginals"] is True

    def test_compute_data_identity_deterministic(self, synthetic_multivariate_timeseries: np.ndarray):
        id1 = compute_data_identity(synthetic_multivariate_timeseries)
        id2 = compute_data_identity(synthetic_multivariate_timeseries)
        assert id1 == id2
        assert len(id1) == 64  # SHA-256 hex digest

        mutated = synthetic_multivariate_timeseries.copy()
        mutated[0, 0] += 1e-4
        id3 = compute_data_identity(mutated)
        assert id1 != id3
