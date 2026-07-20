"""Synthetic ground-truth tests for real_features.py's DFA/MF-DFA additions
(Phase 12 of the "beyond topology" pass) -- genuine EEG long-range-temporal-
correlation/criticality instruments, entirely absent from this pipeline
before this pass. Ground truth uses `fbm`-generated fractional Gaussian
noise of known Hurst exponent, the same technique `antropy`'s own docstring
uses (via a different, numpy-2.x-compatible package -- see requirements.txt
for why `stochastic` specifically was avoided).
"""
from __future__ import annotations

import numpy as np
import pytest

from sciencer_d.btc_icft.level_m.real_features import (
    DFA_MIN_SAMPLES,
    MFDFA_MIN_SAMPLES,
    build_mfdfa_report,
    compute_dfa_features,
    compute_mfdfa_features,
    compute_mfdfa_for_recording,
    extract_real_level_m_features,
)


def _fgn(hurst: float, n: int, seed: int = 0) -> np.ndarray:
    """Fractional Gaussian noise of known Hurst exponent, via `fbm`.

    `fbm.FBM.fgn()` draws from numpy's global RNG (no per-instance seed
    parameter), so this seeds that global state explicitly for deterministic,
    reproducible test fixtures -- consistent with this repo's testing
    convention elsewhere (explicit `np.random.default_rng(seed)` almost
    everywhere else; the global-seed call here is `fbm`'s own API shape, not
    a stylistic choice).
    """
    from fbm import FBM

    np.random.seed(seed)
    f = FBM(n=n, hurst=hurst, length=1, method="daviesharte")
    return f.fgn()


# ---------------------------------------------------------------------------
# compute_dfa_features
# ---------------------------------------------------------------------------

def test_dfa_recovers_known_low_hurst():
    """Anti-persistent fGn (H=0.1) must give a DFA alpha well below 0.5."""
    x = _fgn(0.1, 10000)
    result = compute_dfa_features(x)
    assert result["dfa_alpha"] < 0.35


def test_dfa_recovers_known_mid_hurst():
    """H=0.5 (uncorrelated) must give a DFA alpha near 0.5."""
    x = _fgn(0.5, 10000)
    result = compute_dfa_features(x)
    assert 0.35 < result["dfa_alpha"] < 0.65


def test_dfa_recovers_known_high_hurst():
    """Persistent fGn (H=0.9) must give a DFA alpha well above 0.5."""
    x = _fgn(0.9, 10000)
    result = compute_dfa_features(x)
    assert result["dfa_alpha"] > 0.7


def test_dfa_ordering_across_hurst_values():
    """The DFA alpha ordering must track the true Hurst ordering (the most
    robust ground-truth check -- doesn't depend on tight absolute-value
    tolerances, just that low/mid/high H are correctly ranked)."""
    low = compute_dfa_features(_fgn(0.1, 10000))["dfa_alpha"]
    mid = compute_dfa_features(_fgn(0.5, 10000))["dfa_alpha"]
    high = compute_dfa_features(_fgn(0.9, 10000))["dfa_alpha"]
    assert low < mid < high


def test_dfa_nan_below_min_samples():
    result = compute_dfa_features(np.random.default_rng(0).standard_normal(DFA_MIN_SAMPLES - 1))
    assert np.isnan(result["dfa_alpha"])


def test_dfa_computed_at_min_samples():
    result = compute_dfa_features(np.random.default_rng(0).standard_normal(DFA_MIN_SAMPLES * 3))
    assert np.isfinite(result["dfa_alpha"])


# ---------------------------------------------------------------------------
# compute_mfdfa_features
# ---------------------------------------------------------------------------

def test_mfdfa_nan_below_min_samples():
    result = compute_mfdfa_features(np.random.default_rng(0).standard_normal(MFDFA_MIN_SAMPLES - 1))
    assert np.isnan(result["mfdfa_delta_alpha"])
    assert np.isnan(result["mfdfa_alpha_min"])
    assert np.isnan(result["mfdfa_alpha_max"])


def test_mfdfa_monofractal_fgn_has_narrow_spectrum():
    """Monofractal fGn (single true Hurst exponent everywhere) must show a
    narrow multifractal spectrum width Delta-alpha -- the defining property
    MFDFA's width metric is built to detect (a genuinely multifractal signal
    would show a much wider spectrum)."""
    x = _fgn(0.7, 8000)
    result = compute_mfdfa_features(x)
    assert np.isfinite(result["mfdfa_delta_alpha"])
    assert result["mfdfa_delta_alpha"] < 0.3
    assert result["mfdfa_alpha_min"] <= result["mfdfa_alpha_max"]


def test_mfdfa_alpha_centered_near_true_hurst():
    x = _fgn(0.7, 8000)
    result = compute_mfdfa_features(x)
    center = (result["mfdfa_alpha_min"] + result["mfdfa_alpha_max"]) / 2
    assert 0.5 < center < 0.9


def test_mfdfa_multiplicative_cascade_has_wider_spectrum_than_monofractal():
    """A synthetic binomial multiplicative cascade (textbook multifractal
    construction) must show a measurably wider Delta-alpha than monofractal
    fGn of comparable length -- proves the instrument actually distinguishes
    multifractal from monofractal input, not just returning a fixed number."""
    rng = np.random.default_rng(1)
    n = 8192  # power of 2, convenient for a cascade construction
    p = 0.3
    levels = int(np.log2(n))
    measure = np.ones(1)
    for _ in range(levels):
        left_mass = rng.choice([p, 1 - p], size=len(measure))
        measure = np.concatenate([measure * left_mass, measure * (1 - left_mass)])
    cascade_increments = np.diff(np.log(measure + 1e-300))

    mono = _fgn(0.5, n)

    cascade_result = compute_mfdfa_features(cascade_increments[:n])
    mono_result = compute_mfdfa_features(mono)

    assert np.isfinite(cascade_result["mfdfa_delta_alpha"])
    assert np.isfinite(mono_result["mfdfa_delta_alpha"])
    assert cascade_result["mfdfa_delta_alpha"] > mono_result["mfdfa_delta_alpha"]


# ---------------------------------------------------------------------------
# extract_real_level_m_features integration
# ---------------------------------------------------------------------------

def test_extract_real_level_m_features_includes_dfa_not_mfdfa():
    sfreq = 250.0
    t = np.arange(0, 8, 1 / sfreq)
    signal = np.sin(2 * np.pi * 10 * t) + 0.1 * np.random.default_rng(2).standard_normal(t.size)

    result = extract_real_level_m_features(signal, sfreq)
    assert "dfa_alpha" in result
    assert "mfdfa_delta_alpha" not in result  # deliberately excluded, see module docstring


# ---------------------------------------------------------------------------
# compute_mfdfa_for_recording / build_mfdfa_report
# ---------------------------------------------------------------------------

def test_mfdfa_for_recording_skips_missing_source_file():
    result = compute_mfdfa_for_recording("/does/not/exist.edf")
    assert result["status"] == "skipped"
    assert "not found" in result["reason"]


def test_mfdfa_for_recording_skips_too_short(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    monkeypatch.setattr("data.bids_ingest.get_recording_duration", lambda path: 2.0)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: np.random.default_rng(0).standard_normal(500))

    result = compute_mfdfa_for_recording(str(f))
    assert result["status"] == "skipped"
    assert "too few samples" in result["reason"]


def test_mfdfa_for_recording_computes_on_long_enough_signal(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    np.random.seed(3)
    from fbm import FBM

    long_signal = FBM(n=8000, hurst=0.6, length=1, method="daviesharte").fgn()
    monkeypatch.setattr("data.bids_ingest.get_recording_duration", lambda path: 60.0)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: long_signal)

    result = compute_mfdfa_for_recording(str(f), max_duration_s=None)
    assert result["status"] == "computed"
    assert result["duration_used_s"] == 60.0
    assert np.isfinite(result["mfdfa_delta_alpha"])


def test_mfdfa_for_recording_max_duration_truncates(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    captured = {}

    def fake_read(path, start, end, pick="mean", max_channels=None):
        captured["end"] = end
        np.random.seed(4)
        return FBM(n=int(4000 * (end - start)), hurst=0.6, length=1, method="daviesharte").fgn()

    from fbm import FBM

    monkeypatch.setattr("data.bids_ingest.get_recording_duration", lambda path: 200.0)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", fake_read)

    result = compute_mfdfa_for_recording(str(f), max_duration_s=30.0)
    assert captured["end"] == 30.0
    assert result["status"] == "computed"


def test_build_mfdfa_report_dedupes_by_source_file(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    np.random.seed(5)
    from fbm import FBM

    long_signal = FBM(n=8000, hurst=0.6, length=1, method="daviesharte").fgn()
    monkeypatch.setattr("data.bids_ingest.get_recording_duration", lambda path: 60.0)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: long_signal)

    m_rows = [{"row_id": f"r{i}", "source_file": str(f), "window_start_s": "0", "window_end_s": "4"} for i in range(10)]
    report = build_mfdfa_report(m_rows, sample_size=5, max_duration_s=None)
    assert report["status"] == "mfdfa_computed"
    assert report["n_recordings_total_candidates"] == 1
    assert report["n_recordings_computed"] == 1
