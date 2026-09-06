"""Performance-refactor equivalence tests for sim/pitnn/kernels_fast.py.

Verify that the allocation-reducing NumPy fallback stays numerically identical,
that the optional Numba path is not mandatory, and that the public API and
shape validation are unchanged.
"""
from __future__ import annotations

import numpy as np
import pytest

import sim.pitnn.kernels_fast as kf
from sim.pitnn.kernels_fast import (
    LLGWorkspace,
    active_cell_indices,
    exchange_dmi_field,
    heun_step,
    resolve_backend,
)


def _spins(n=32, seed=1):
    rng = np.random.default_rng(seed)
    s = rng.standard_normal((n, 3))
    return s / np.linalg.norm(s, axis=1, keepdims=True)


def _reference_numpy_step(spins, noise_a, noise_b, *, dt, exchange, dmi, damping, ciss_torque):
    """Independent re-implementation of the original NumPy Heun step formula."""
    def deriv(values, noise):
        field = exchange_dmi_field(values, exchange, dmi)
        field = field + noise
        precession = np.cross(values, field)
        damping_term = np.cross(values, precession)
        torque = ciss_torque * np.cross(values, np.array([0.0, 0.0, 1.0]))
        return -precession - damping * damping_term + torque
    k1 = deriv(spins, noise_a)
    predictor = spins + dt * k1
    predictor = predictor / np.linalg.norm(predictor, axis=1, keepdims=True)
    k2 = deriv(predictor, noise_b)
    out = spins + 0.5 * dt * (k1 + k2)
    return out / np.linalg.norm(out, axis=1, keepdims=True)


def test_numpy_fallback_bit_identical_to_reference(monkeypatch):
    monkeypatch.setattr(kf, "NUMBA_AVAILABLE", False)
    rng = np.random.default_rng(3)
    s = _spins(48)
    params = dict(dt=1e-3, exchange=0.8, dmi=0.15, damping=0.05, ciss_torque=0.02)
    ws = LLGWorkspace.create(48)
    for _ in range(50):
        na = rng.standard_normal((48, 3)) * 0.01
        nb = rng.standard_normal((48, 3)) * 0.01
        expected = _reference_numpy_step(s, na, nb, **params)
        got = heun_step(s, na, nb, workspace=ws, **params)
        assert np.array_equal(got, expected)
        s = got


def test_numpy_fallback_is_deterministic(monkeypatch):
    monkeypatch.setattr(kf, "NUMBA_AVAILABLE", False)
    s = _spins(16)
    z = np.zeros((16, 3))
    p = dict(dt=1e-3, exchange=0.8, dmi=0.15, damping=0.05, ciss_torque=0.02)
    a = heun_step(s, z, z, **p)
    b = heun_step(s, z, z, **p)
    assert np.array_equal(a, b)


def test_optional_numba_unavailable_still_works(monkeypatch):
    monkeypatch.setattr(kf, "NUMBA_AVAILABLE", False)
    assert resolve_backend("auto") == "numpy"
    assert resolve_backend("numpy") == "numpy"
    s = _spins(16)
    z = np.zeros((16, 3))
    result = heun_step(s, z, z, dt=1e-5, exchange=0.8, dmi=0.1, damping=0.05, ciss_torque=0.02)
    assert result.shape == (16, 3)
    assert np.max(np.abs(np.linalg.norm(result, axis=1) - 1.0)) < 1e-12


def test_heun_step_does_not_mutate_input(monkeypatch):
    monkeypatch.setattr(kf, "NUMBA_AVAILABLE", False)
    s = _spins(20)
    before = s.copy()
    heun_step(s, np.zeros((20, 3)), np.zeros((20, 3)),
              dt=1e-3, exchange=0.8, dmi=0.15, damping=0.05, ciss_torque=0.02)
    assert np.array_equal(s, before)


def test_cross_helpers_match_numpy_cross():
    rng = np.random.default_rng(0)
    a = rng.standard_normal((25, 3)); b = rng.standard_normal((25, 3))
    out = np.empty_like(a)
    assert np.array_equal(kf._cross_into(a, b, out), np.cross(a, b))
    out2 = np.empty_like(a)
    assert np.array_equal(kf._cross_ciss_axis_into(a, out2), np.cross(a, kf._CISS_AXIS))


def test_workspace_has_all_buffers():
    ws = LLGWorkspace.create(8)
    for name in ("field", "predictor", "derivative", "k1", "precession", "damping", "torque"):
        buf = getattr(ws, name)
        assert buf.shape == (8, 3) and buf.dtype == np.float64
    with pytest.raises(ValueError):
        LLGWorkspace.create(2)


def test_kernel_shape_validation_unchanged():
    with pytest.raises(ValueError):
        exchange_dmi_field(np.zeros((2, 3)), 0.8, 0.1)          # N < 3
    with pytest.raises(ValueError):
        exchange_dmi_field(np.zeros((4, 2)), 0.8, 0.1)          # wrong width
    with pytest.raises(ValueError):
        heun_step(np.zeros((5, 3)), np.zeros((4, 3)), np.zeros((5, 3)),
                  dt=1e-3, exchange=0.8, dmi=0.1, damping=0.05, ciss_torque=0.02)
    with pytest.raises(ValueError):
        heun_step(np.zeros((5, 3)), np.zeros((5, 3)), np.zeros((5, 3)),
                  dt=0.0, exchange=0.8, dmi=0.1, damping=0.05, ciss_torque=0.02)


def test_exchange_dmi_field_out_buffer_and_active_cells():
    s = _spins(10)
    out = np.empty((10, 3))
    field = exchange_dmi_field(s, 0.8, 0.1, out)
    assert field is out and field.shape == (10, 3)
    idx = active_cell_indices(np.array([True, False, True, True]))
    assert np.array_equal(idx, np.array([0, 2, 3]))


def test_no_api_regression_resolve_backend_validates():
    with pytest.raises(ValueError):
        resolve_backend("gpu")
