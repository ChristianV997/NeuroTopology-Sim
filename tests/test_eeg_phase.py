"""Tests for analytic-phase EEG utilities and metadata helpers.

All tests use synthetic arrays — no real EEG files, no network.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from validation.analytic_phase import (
    DEFAULT_EEG_BANDS,
    analytic_phases_by_band,
    bandpass_hilbert_phase,
    channel_phase_gradient_metrics,
    phase_grid_topology_metrics,
    temporal_phase_proxy_metrics,
)


# ── bandpass_hilbert_phase ───────────────────────────────────────────────────

def test_bandpass_hilbert_phase_finite_on_sine():
    sfreq = 256.0
    t = np.arange(0, 4.0, 1.0 / sfreq)
    sig = np.sin(2 * np.pi * 10.0 * t)
    data = np.tile(sig, (4, 1))
    phase = bandpass_hilbert_phase(data, sfreq, 8.0, 13.0)
    assert phase.shape == data.shape
    assert np.all(np.isfinite(phase))
    assert np.all(phase >= -np.pi - 1e-9)
    assert np.all(phase <= np.pi + 1e-9)


def test_bandpass_hilbert_phase_invalid_low_raises():
    data = np.zeros((4, 1024))
    with pytest.raises(ValueError):
        bandpass_hilbert_phase(data, sfreq=256.0, low_hz=0.0, high_hz=10.0)


def test_bandpass_hilbert_phase_invalid_high_raises():
    data = np.zeros((4, 1024))
    with pytest.raises(ValueError):
        bandpass_hilbert_phase(data, sfreq=256.0, low_hz=10.0, high_hz=130.0)


def test_bandpass_hilbert_phase_low_ge_high_raises():
    data = np.zeros((4, 1024))
    with pytest.raises(ValueError):
        bandpass_hilbert_phase(data, sfreq=256.0, low_hz=20.0, high_hz=10.0)


def test_bandpass_hilbert_phase_requires_2d():
    data = np.zeros(1024)
    with pytest.raises(ValueError):
        bandpass_hilbert_phase(data, sfreq=256.0, low_hz=8.0, high_hz=13.0)


# ── analytic_phases_by_band ──────────────────────────────────────────────────

def test_analytic_phases_by_band_default_keys():
    sfreq = 256.0
    rng = np.random.default_rng(0)
    data = rng.standard_normal((6, int(sfreq * 4)))
    out = analytic_phases_by_band(data, sfreq)
    # All default bands fit comfortably under Nyquist=128 Hz
    assert set(out.keys()) == set(DEFAULT_EEG_BANDS.keys())
    for v in out.values():
        assert v.shape == data.shape
        assert np.all(np.isfinite(v))


def test_analytic_phases_by_band_skips_above_nyquist():
    # sfreq=64Hz -> Nyquist 32Hz; gamma_low (30-45) must be skipped
    sfreq = 64.0
    rng = np.random.default_rng(1)
    data = rng.standard_normal((4, int(sfreq * 4)))
    out = analytic_phases_by_band(data, sfreq)
    assert "gamma_low" not in out
    assert "alpha" in out


# ── channel_phase_gradient_metrics ───────────────────────────────────────────

def test_channel_phase_gradient_metrics_keys():
    rng = np.random.default_rng(42)
    phase = rng.uniform(-np.pi, np.pi, size=(8, 200))
    m = channel_phase_gradient_metrics(phase)
    assert {"Q", "Qabs", "phase_grad", "f_dress", "metric_kind"}.issubset(m)
    for k in ("Q", "Qabs", "phase_grad", "f_dress"):
        assert np.isfinite(m[k])
    assert m["metric_kind"] == "analytic_phase_proxy"


def test_channel_phase_gradient_metrics_deterministic():
    rng = np.random.default_rng(7)
    phase = rng.uniform(-np.pi, np.pi, size=(6, 128))
    m1 = channel_phase_gradient_metrics(phase)
    m2 = channel_phase_gradient_metrics(phase.copy())
    for k in ("Q", "Qabs", "phase_grad", "f_dress"):
        assert m1[k] == m2[k]


def test_channel_phase_gradient_metrics_requires_2d():
    with pytest.raises(ValueError):
        channel_phase_gradient_metrics(np.zeros(10))


# ── phase_grid_topology_metrics ──────────────────────────────────────────────

def test_phase_grid_topology_metrics_keys_finite():
    rng = np.random.default_rng(3)
    theta = rng.uniform(-np.pi, np.pi, size=(8, 8))
    m = phase_grid_topology_metrics(theta)
    assert {"Q", "Qabs", "f_dress", "metric_kind"}.issubset(m)
    assert m["metric_kind"] == "phase_grid_topology"
    for k in ("Q", "Qabs", "f_dress", "phase_grad"):
        assert np.isfinite(m[k])


def test_phase_grid_topology_metrics_invalid_shape():
    with pytest.raises(ValueError):
        phase_grid_topology_metrics(np.zeros(10))
    with pytest.raises(ValueError):
        phase_grid_topology_metrics(np.zeros((1, 5)))


# ── temporal_phase_proxy_metrics ─────────────────────────────────────────────

def test_temporal_phase_proxy_marked_as_proxy():
    rng = np.random.default_rng(0)
    data = rng.standard_normal((4, 256))
    m = temporal_phase_proxy_metrics(data)
    assert m["metric_kind"] == "temporal_phase_proxy"
    for k in ("Q", "Qabs", "phase_grad", "f_dress"):
        assert np.isfinite(m[k])


# ── _infer_metadata ──────────────────────────────────────────────────────────

def test_infer_metadata_bids_tokens():
    from pipelines.run_eeg import _infer_metadata
    p = Path("/data/raw/ds002094/sub-01/ses-02/eeg/sub-01_ses-02_task-awake_eeg.edf")
    meta = _infer_metadata(p, dataset="ds002094")
    assert meta["subject_id"] == "01"
    assert meta["session_id"] == "02"
    assert meta["condition"] == "awake"
    assert meta["state_label"] == "awake"
    assert meta["dataset"] == "ds002094"
    assert meta["dataset_id"] == "ds002094"


def test_infer_metadata_unknown_fallback():
    """Path with no BIDS tokens and a non-informative parent directory yields
    ``"unknown"`` in every field."""
    from pipelines.run_eeg import _infer_metadata
    # parent dir 'eeg' is in the exclusion set so condition stays unknown
    p = Path("/data/eeg/nameless.edf")
    meta = _infer_metadata(p, dataset="ds_test")
    assert meta["subject_id"] == "unknown"
    assert meta["session_id"] == "unknown"
    assert meta["condition"] == "unknown"
    assert meta["state_label"] == "unknown"


def test_infer_metadata_state_label_anesthesia():
    from pipelines.run_eeg import _infer_metadata
    p = Path("/data/raw/ds_x/sub-03/anesthesia/sub-03_run-1_eeg.edf")
    meta = _infer_metadata(p, dataset="ds_x")
    assert meta["subject_id"] == "03"
    assert meta["session_id"] == "run-1"
    assert meta["state_label"] == "anesthesia"
