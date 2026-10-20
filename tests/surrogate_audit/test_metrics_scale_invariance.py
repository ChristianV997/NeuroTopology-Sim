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


@pytest.mark.parametrize("scale", [1e100, 1e50, 1e6, 1.0, 1e-3, 1e-6, 1e-8, 1e-10, 1e-12, 1e-15, 1e-20, 1e-50, 1e-100])
def test_cross_spectral_error_scale_invariance_under_relative_mismatch(scale: float):
    """A constant 10% amplitude mismatch (21% cross-spectral error) must not falsely pass at small scale."""
    x = gaussian_linear(n_ch=4, n_t=128, seed=42)
    x_scaled = scale * x
    # Surrogate has an exact 10% amplitude scaling: C_surr = 1.21 * C_orig, relative error = 0.21
    s_scaled = 1.1 * x_scaled

    err = relative_cross_spectral_error(x_scaled, s_scaled)
    # Must remain ~0.21 regardless of scale
    assert np.isclose(err, 0.21, rtol=1e-5), f"scale {scale:1.0e} gave relative error {err}, expected 0.21"
    assert err > SPECTRAL_GATE_1E3, f"scale {scale:1.0e} falsely passed the 1e-3 gate with err={err}"


@pytest.mark.parametrize("scale", [1e100, 1e50, 1e6, 1.0, 1e-3, 1e-6, 1e-8, 1e-10, 1e-12, 1e-15, 1e-20, 1e-50, 1e-100])
def test_autospectral_error_scale_invariance(scale: float):
    """Autospectral relative error must also be strictly scale invariant."""
    x = gaussian_linear(n_ch=4, n_t=128, seed=42)
    x_scaled = scale * x
    s_scaled = 1.1 * x_scaled

    err = relative_autospectral_error(x_scaled, s_scaled)
    assert np.isclose(err, 0.21, rtol=1e-5), f"scale {scale:1.0e} gave autospectral error {err}, expected 0.21"
    assert err > SPECTRAL_GATE_1E3


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
