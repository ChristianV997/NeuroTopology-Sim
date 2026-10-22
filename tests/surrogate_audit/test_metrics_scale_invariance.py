"""Regression tests for scale-invariance of cross-spectral error and input contracts."""
from __future__ import annotations

import numpy as np
import pytest

from tests.surrogate_audit.fixtures import gaussian_linear
from tools.surrogate_audit.errors import SurrogateAuditError
from tools.surrogate_audit.metrics import (
    SPECTRAL_GATE_1E3,
    relative_autospectral_error,
    relative_cross_spectral_error,
    validate_array,
)
from tools.surrogate_audit.mv_fpr import generate_mv_fpr
from tools.surrogate_audit.mv_iaaft import generate_mv_iaaft
from tools.surrogate_audit.report import audit_surrogate


@pytest.mark.parametrize(
    "scale",
    [1e250, 1e160, 1e100, 1e50, 1e6, 1.0, 1e-3, 1e-6, 1e-8, 1e-10, 1e-12, 1e-15, 1e-20, 1e-50, 1e-100, 1e-160, 1e-250],
)
def test_cross_spectral_error_scale_invariance_under_relative_mismatch(scale: float):
    """A constant 10% amplitude mismatch (21% cross-spectral error) must not falsely pass or overflow/underflow at extreme scale."""
    x = gaussian_linear(n_ch=4, n_t=128, seed=42)
    x_scaled = scale * x
    # Surrogate has an exact 10% amplitude scaling: C_surr = 1.21 * C_orig, relative error = 0.21
    s_scaled = 1.1 * x_scaled

    err = relative_cross_spectral_error(x_scaled, s_scaled)
    # Must remain ~0.21 regardless of scale
    assert np.isclose(err, 0.21, rtol=1e-5), f"scale {scale:1.0e} gave relative error {err}, expected 0.21"
    assert err > SPECTRAL_GATE_1E3, f"scale {scale:1.0e} falsely passed the 1e-3 gate with err={err}"


@pytest.mark.parametrize(
    "scale",
    [1e250, 1e160, 1e100, 1e50, 1e6, 1.0, 1e-3, 1e-6, 1e-8, 1e-10, 1e-12, 1e-15, 1e-20, 1e-50, 1e-100, 1e-160, 1e-250],
)
def test_autospectral_error_scale_invariance(scale: float):
    """Autospectral relative error must also be strictly scale invariant across extreme dynamic ranges."""
    x = gaussian_linear(n_ch=4, n_t=128, seed=42)
    x_scaled = scale * x
    s_scaled = 1.1 * x_scaled

    err = relative_autospectral_error(x_scaled, s_scaled)
    assert np.isclose(err, 0.21, rtol=1e-5), f"scale {scale:1.0e} gave autospectral error {err}, expected 0.21"
    assert err > SPECTRAL_GATE_1E3


def test_cross_vs_auto_spectrum_mutation_detects_phase_decorrelation():
    """Independent channel phase rotation preserves auto-spectra but mutates cross-spectra.

    The multivariate gate must detect this mutation via relative_cross_spectral_error,
    while relative_autospectral_error alone would falsely report zero error.
    """
    x = gaussian_linear(n_ch=2, n_t=128, seed=77)
    F = np.fft.rfft(x, axis=1)

    # Mutate cross-spectrum by rotating channel 1 phases by pi/2 at all non-DC/Nyquist frequencies,
    # leaving channel 0 completely unchanged.
    F_mut = F.copy()
    F_mut[1, 1:-1] *= 1j  # 90-degree phase shift on channel 1 only

    s_mut = np.fft.irfft(F_mut, n=128, axis=1)

    # Auto-spectra are preserved to numerical precision
    auto_err = relative_autospectral_error(x, s_mut)
    assert auto_err < 1e-12, f"auto-spectrum was unexpectedly modified: {auto_err}"

    # Cross-spectrum is substantially corrupted
    cross_err = relative_cross_spectral_error(x, s_mut)
    assert cross_err > 0.5, f"cross-spectrum error failed to catch phase decorrelation: {cross_err}"


def test_zero_power_spectral_error_behavior():
    """Identically zero signals evaluate to 0.0 error; zero original with active surrogate evaluates to inf."""
    zeros = np.zeros((3, 64), dtype=np.float64)
    active = gaussian_linear(n_ch=3, n_t=64, seed=1)

    assert relative_cross_spectral_error(zeros, zeros) == 0.0
    assert relative_autospectral_error(zeros, zeros) == 0.0

    assert relative_cross_spectral_error(zeros, active) == float("inf")
    assert relative_autospectral_error(zeros, active) == float("inf")


def test_complex_input_rejected():
    """Complex-valued inputs must fail closed and not be silently cast to real."""
    complex_x = np.ones((2, 32), dtype=np.complex128) + 0.5j
    with pytest.raises(SurrogateAuditError, match="complex"):
        validate_array(complex_x)

    with pytest.raises(SurrogateAuditError, match="complex"):
        generate_mv_fpr(complex_x, seed=0)

    with pytest.raises(SurrogateAuditError, match="complex"):
        generate_mv_iaaft(complex_x, seed=0)


def test_nonfinite_and_invalid_spectral_gate():
    """Spectral gate and max_iter must be finite and positive."""
    x = gaussian_linear(n_ch=2, n_t=32, seed=0)
    for bad_gate in [0.0, -1.0, float("nan"), float("inf"), -float("inf")]:
        with pytest.raises(SurrogateAuditError, match="spectral_gate"):
            generate_mv_iaaft(x, spectral_gate=bad_gate)

    for bad_iter in [0, -5]:
        with pytest.raises(SurrogateAuditError, match="max_iter"):
            generate_mv_iaaft(x, max_iter=bad_iter)


def test_pre_fft_peak_norm_keeps_identical_extreme_float64_at_zero_error():
    """Regression: identical finite ~1e308 series must not report inf after rfft overflow.

    Prior metrics called ``rfft`` before any normalization; at the top of float64
    the transform overflows and the relative error falsely became ``inf``.
    """
    x = np.full((2, 64), 1e308, dtype=np.float64)
    assert relative_cross_spectral_error(x, x) == 0.0
    assert relative_autospectral_error(x, x) == 0.0
    # 21% cross-spectral mismatch must still fail the 1e-3 gate (no threshold weakening).
    err = relative_cross_spectral_error(x, 1.1 * x)
    assert np.isclose(err, 0.21, rtol=1e-5), err
    assert err > SPECTRAL_GATE_1E3


def test_production_csd_rel_error_not_scale_false_pass():
    """Bridge: production ``_csd_rel_error`` rejects tiny-scale 21% mismatch (EPS bug fixed).

    The historical ``||A-T||/(||T||+1e-12)`` formula false-passes at 1e-20; current
    ``tools/surrogate_nulls/nulls.py:_csd_rel_error`` must remain scale-invariant.
    """
    import math

    from tools.surrogate_nulls import nulls as prod
    from tools.surrogate_nulls import spectral as sp

    target = [[[1e-20 + 0j]]]
    actual = [[[1.21e-20 + 0j]]]
    # Document legacy helper still false-passes (owned by production spectral lane).
    legacy = math.sqrt(abs(1.21e-20 - 1e-20) ** 2) / (math.sqrt(abs(1e-20) ** 2) + sp.EPS)
    assert legacy < SPECTRAL_GATE_1E3
    # Production CSD gate used by null reports must NOT false-pass.
    prod_err = prod._csd_rel_error(actual, target)
    assert np.isclose(prod_err, 0.21, rtol=1e-9), prod_err
    assert prod_err > SPECTRAL_GATE_1E3
    assert np.isclose(prod_err, prod._csd_rel_error([[[1.21 + 0j]]], [[[1.0 + 0j]]]), rtol=1e-12)


def test_production_generators_bridge_hard_import():
    """Bridge: hard-import production nulls and score draws with audit metrics."""
    from pathlib import Path

    from tools.surrogate_nulls import nulls as prod

    path = Path(prod.__file__).resolve()
    assert path.name == "nulls.py"
    assert "surrogate_nulls" in path.parts

    x = gaussian_linear(n_ch=3, n_t=128, seed=7)
    s_fpr, rep_fpr = prod.common_phase_prichard_theiler(x, seed=11)
    s_fpr = np.asarray(s_fpr, dtype=np.float64)
    assert s_fpr.shape == x.shape
    # Shared-phase FPR: audit cross-spectral error must meet the tight algebraic bar.
    cs = relative_cross_spectral_error(x, s_fpr)
    assert cs <= 1e-10, cs
    assert rep_fpr.cross_spectrum_rel_error is not None
    assert float(rep_fpr.cross_spectrum_rel_error) <= 1e-3

    s_iaaft, rep_iaaft = prod.mv_iaaft_rank_adjusted(x, seed=13, max_iter=40)
    s_iaaft = np.asarray(s_iaaft, dtype=np.float64)
    # Exact marginal restoration after rank adjustment.
    from tools.surrogate_audit.metrics import marginal_sorted_error

    assert marginal_sorted_error(x, s_iaaft) <= 1e-12
    assert rep_iaaft.cross_spectrum_rel_error is not None
