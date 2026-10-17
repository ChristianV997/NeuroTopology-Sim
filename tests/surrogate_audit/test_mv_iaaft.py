"""MV-IAAFT: exact marginals; honest pre/post-rank full cross-spectral errors."""
from __future__ import annotations

import numpy as np
import pytest

from tests.surrogate_audit.fixtures import (
    constant_channel_mix,
    gaussian_linear,
    non_gaussian_skewed,
)
from tools.surrogate_audit.metrics import SPECTRAL_GATE_1E3, marginal_sorted_error
from tools.surrogate_audit.mv_iaaft import generate_mv_iaaft
from tools.surrogate_audit.report import audit_surrogate, dumps_report


@pytest.mark.parametrize("n_t", [16, 17, 32, 33])
@pytest.mark.parametrize("n_ch", [1, 2, 4])
def test_mv_iaaft_exact_sorted_value_restoration(n_t, n_ch):
    x = non_gaussian_skewed(n_ch=n_ch, n_t=n_t, seed=20 + n_t)
    surr, meta = generate_mv_iaaft(x, seed=11, max_iter=40)
    assert meta["returned_signal"] == "post_rank"
    assert marginal_sorted_error(x, surr) <= 1e-12
    for c in range(n_ch):
        np.testing.assert_allclose(np.sort(surr[c]), np.sort(x[c]), atol=1e-12)


def test_mv_iaaft_reports_pre_and_post_rank_full_cross_spectral_errors():
    x = non_gaussian_skewed(n_ch=4, n_t=128, seed=8)
    _surr, meta = generate_mv_iaaft(x, seed=3, max_iter=30)
    assert "pre_rank_cross_spectral_error" in meta
    assert "post_rank_cross_spectral_error" in meta
    assert meta["pre_rank_cross_spectral_error"] >= 0.0
    assert meta["post_rank_cross_spectral_error"] >= 0.0
    # Post-rank is the gated quantity; guarantee flag must be false.
    assert meta["strict_1e3_post_rank_gate_guaranteed"] is False
    assert meta["spectral_gate"] == SPECTRAL_GATE_1E3


def test_mv_iaaft_unmet_when_post_rank_exceeds_gate_on_skewed_data():
    """Strict 1e-3 is not guaranteed; skewed multivariate data is expected UNMET."""
    x = non_gaussian_skewed(n_ch=5, n_t=256, seed=42)
    surr, meta = generate_mv_iaaft(x, seed=7, max_iter=25)
    # Exact marginals still hold even when spectral gate is UNMET.
    assert marginal_sorted_error(x, surr) <= 1e-12
    assert meta["post_rank_cross_spectral_error"] > SPECTRAL_GATE_1E3
    assert meta["spectral_gate_status"] == "UNMET"
    # Returned array is post-rank (not a pre-rank swap that would hide UNMET).
    assert meta["returned_signal"] == "post_rank"
    for c in range(x.shape[0]):
        np.testing.assert_allclose(np.sort(surr[c]), np.sort(x[c]), atol=1e-12)


def test_mv_iaaft_does_not_hide_unmet_by_autospectra_only():
    x = non_gaussian_skewed(n_ch=4, n_t=200, seed=9)
    report = audit_surrogate(x, method="mv_iaaft", seed=1, max_iter=20)
    text = dumps_report(report)
    assert "post_rank_cross_spectral_error" in text
    assert "pre_rank_cross_spectral_error" in text
    # Must not claim scientific validation.
    assert report["scientific_validated"] is False
    assert report["evidence_class"] == "SYNTHETIC_ONLY"
    assert report["strict_1e3_post_rank_gate_guaranteed"] is False


def test_mv_iaaft_gaussian_linear_fixture_runs():
    x = gaussian_linear(n_ch=3, n_t=128, seed=0)
    surr, meta = generate_mv_iaaft(x, seed=2, max_iter=20)
    assert surr.shape == x.shape
    assert meta["round6_candidate_tested"] is False
    assert meta["interchangeable_with_mv_fpr"] is False


def test_mv_iaaft_constant_channel():
    x = constant_channel_mix(n_t=48, seed=3)
    surr, meta = generate_mv_iaaft(x, seed=4, max_iter=15)
    assert np.allclose(np.sort(surr[1]), np.sort(x[1]))
    assert meta["marginal_sorted_error"] <= 1e-12


def test_mv_iaaft_deterministic_seed():
    x = gaussian_linear(n_ch=2, n_t=64, seed=5)
    a, _ = generate_mv_iaaft(x, seed=12, max_iter=10)
    b, _ = generate_mv_iaaft(x, seed=12, max_iter=10)
    np.testing.assert_array_equal(a, b)


def test_nulls_are_not_interchangeable():
    from tools.surrogate_audit.mv_fpr import generate_mv_fpr

    x = non_gaussian_skewed(n_ch=3, n_t=96, seed=6)
    fpr, fmeta = generate_mv_fpr(x, seed=1)
    iaaft, imeta = generate_mv_iaaft(x, seed=1, max_iter=15)
    assert fmeta["interchangeable_with_mv_iaaft"] is False
    assert imeta["interchangeable_with_mv_fpr"] is False
    # Different null constructions → different time series in general.
    assert not np.allclose(fpr, iaaft)
