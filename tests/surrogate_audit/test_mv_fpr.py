"""MV-FPR: shared-phase null preserves full cross-spectrum, not quantiles."""
from __future__ import annotations

import numpy as np
import pytest

from tests.surrogate_audit.fixtures import (
    constant_channel_mix,
    gaussian_linear,
    non_gaussian_skewed,
)
from tools.surrogate_audit.metrics import (
    marginal_sorted_error,
    relative_cross_spectral_error,
)
from tools.surrogate_audit.mv_fpr import generate_mv_fpr, randomized_frequency_bins
from tools.surrogate_audit.report import audit_surrogate


@pytest.mark.parametrize("n_t", [17, 32, 33, 64])  # odd/even + short
@pytest.mark.parametrize("n_ch", [1, 2, 5])
def test_mv_fpr_preserves_full_cross_spectrum(n_t, n_ch):
    x = gaussian_linear(n_ch=n_ch, n_t=n_t, seed=10 + n_t + n_ch)
    surr, meta = generate_mv_fpr(x, seed=123)
    err = relative_cross_spectral_error(x, surr)
    assert err <= 1e-10, err
    assert meta["randomized_bins"] == randomized_frequency_bins(n_t)
    assert 0 in meta["fixed_real_bins"]
    if n_t % 2 == 0:
        assert (n_t // 2) in meta["fixed_real_bins"] or (meta["n_freq"] - 1) in meta[
            "fixed_real_bins"
        ]


def test_mv_fpr_bins_documented_for_even_and_odd():
    even_bins = randomized_frequency_bins(16)
    odd_bins = randomized_frequency_bins(17)
    # even: n_freq=9, randomized 1..7 (exclude Nyquist 8)
    assert even_bins == list(range(1, 8))
    # odd: n_freq=9, randomized 1..8 (no Nyquist bin)
    assert odd_bins == list(range(1, 9))


def test_mv_fpr_does_not_restore_quantiles_on_non_gaussian():
    x = non_gaussian_skewed(n_ch=3, n_t=128, seed=4)
    surr, _ = generate_mv_fpr(x, seed=5)
    # Shared-phase FPR keeps spectra/cross-spectra but not exact sorted values
    # for non-trivial signals (phase change reshuffles time-domain order stats).
    assert marginal_sorted_error(x, surr) > 1e-6


def test_mv_fpr_deterministic_seed():
    x = gaussian_linear(n_ch=3, n_t=64, seed=0)
    a, _ = generate_mv_fpr(x, seed=99)
    b, _ = generate_mv_fpr(x, seed=99)
    c, _ = generate_mv_fpr(x, seed=100)
    np.testing.assert_array_equal(a, b)
    assert not np.allclose(a, c)


def test_mv_fpr_constant_and_zero_power_channel():
    x = constant_channel_mix(n_t=64, seed=2)
    surr, meta = generate_mv_fpr(x, seed=7)
    assert np.all(np.isfinite(surr))
    # Constant channel remains constant (zero non-DC power).
    assert np.allclose(surr[1], surr[1, 0])
    assert relative_cross_spectral_error(x, surr) <= 1e-10
    assert meta["interchangeable_with_mv_iaaft"] is False


def test_mv_fpr_audit_report_met_and_quantile_na():
    x = gaussian_linear(n_ch=4, n_t=128, seed=1)
    report = audit_surrogate(x, method="mv_fpr", seed=3)
    assert report["evidence_class"] == "SYNTHETIC_ONLY"
    assert report["scientific_validated"] is False
    assert report["hold"] is True
    assert report["spectral_gate_status"] == "MET"
    assert report["quantile_gate_status"] == "NOT_APPLICABLE"
    assert report["round6_candidate_tested"] is False if "round6_candidate_tested" in report else True
    assert report["meta"]["round6_candidate_tested"] is False


@pytest.mark.parametrize("scale", [1e-200, 1e-160, 1e160, 1e200])
def test_mv_fpr_extreme_scale_audit_preserves_cross_spectrum(scale: float):
    """MV-FPR must preserve cross-spectrum and report MET status across extreme dynamic ranges."""
    x = scale * gaussian_linear(n_ch=3, n_t=64, seed=15)
    report = audit_surrogate(x, method="mv_fpr", seed=4)
    assert report["status"] == "MET"
    assert report["spectral_gate_status"] == "MET"
    assert report["cross_spectral_error"] is not None
    assert report["cross_spectral_error"] <= 1e-10


def test_mv_fpr_n_time_2_noop_behavior():
    """At n_t=2, frequency bins are only DC and Nyquist (no randomized bins); array is unchanged."""
    x = np.array([[1.0, 2.0], [3.0, 4.0]])
    surr, meta = generate_mv_fpr(x, seed=0)
    assert meta["randomized_bins"] == []
    np.testing.assert_allclose(surr, x, atol=1e-12)
    assert relative_cross_spectral_error(x, surr) <= 1e-10
