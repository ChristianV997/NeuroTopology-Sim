"""Tests for EEG null-control row export.

All tests use synthetic data via a FakeRaw stub — no real EEG files, no MNE
file I/O, no network.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


# ── FakeRaw ──────────────────────────────────────────────────────────────────

class FakeRaw:
    """Minimal MNE-like raw object for testing run_eeg.run()."""

    def __init__(self, data: np.ndarray, sfreq: float = 128.0):
        self.data = np.asarray(data, dtype=float)
        self.info = {"sfreq": sfreq}
        self.n_times = self.data.shape[1]

    def copy(self):
        return self

    def load_data(self):
        pass

    def pick_types(self, **kwargs):
        pass

    def filter(self, *args, **kwargs):
        pass

    def notch_filter(self, *args, **kwargs):
        pass

    def set_eeg_reference(self, *args, **kwargs):
        pass

    def get_data(self, start, stop):
        return self.data[:, start:stop]


# ── _stable_window_seed ──────────────────────────────────────────────────────

def test_stable_window_seed_deterministic():
    from pipelines.run_eeg import _stable_window_seed
    p = Path("/data/sub-01/eeg.edf")
    s1 = _stable_window_seed(p, 0, 512, 0)
    s2 = _stable_window_seed(p, 0, 512, 0)
    assert s1 == s2


def test_stable_window_seed_differs_across_windows():
    from pipelines.run_eeg import _stable_window_seed
    p = Path("/data/sub-01/eeg.edf")
    s1 = _stable_window_seed(p, 0, 512, 0)
    s2 = _stable_window_seed(p, 512, 1024, 0)
    assert s1 != s2


def test_stable_window_seed_uint32_range():
    from pipelines.run_eeg import _stable_window_seed
    p = Path("/data/sub-01/eeg.edf")
    seed = _stable_window_seed(p, 0, 512, 42)
    assert 0 <= seed <= 2**32 - 1


def test_stable_window_seed_varies_with_base_seed():
    from pipelines.run_eeg import _stable_window_seed
    p = Path("/data/sub-01/eeg.edf")
    s0 = _stable_window_seed(p, 0, 512, 0)
    s1 = _stable_window_seed(p, 0, 512, 1)
    assert s0 != s1


# ── _null_variants ───────────────────────────────────────────────────────────

def test_null_variants_returns_expected_keys():
    from pipelines.run_eeg import _null_variants
    rng = np.random.default_rng(0)
    seg = rng.standard_normal((6, 256))
    variants = _null_variants(seg, seed=42)
    assert set(variants.keys()) == {"channel_shuffle", "time_reverse", "phase_randomized"}


def test_null_variants_preserve_shape():
    from pipelines.run_eeg import _null_variants
    rng = np.random.default_rng(1)
    seg = rng.standard_normal((4, 128))
    variants = _null_variants(seg, seed=0)
    for name, arr in variants.items():
        assert arr.shape == seg.shape, f"{name} changed shape"


def test_null_variants_deterministic():
    from pipelines.run_eeg import _null_variants
    rng = np.random.default_rng(2)
    seg = rng.standard_normal((4, 128))
    a = _null_variants(seg, seed=7)
    b = _null_variants(seg, seed=7)
    for name in a:
        assert np.array_equal(a[name], b[name]), f"{name} not deterministic"


def test_null_variants_are_finite():
    from pipelines.run_eeg import _null_variants
    rng = np.random.default_rng(3)
    seg = rng.standard_normal((4, 128))
    for _, arr in _null_variants(seg, seed=0).items():
        assert np.all(np.isfinite(arr))


# ── efficiency: _null_variants called once per window ────────────────────────

def test_null_variants_called_once_per_window(tmp_path, monkeypatch):
    """_null_variants must be called once per window, not once per band."""
    from pipelines import run_eeg

    call_count = {"n": 0}
    original = run_eeg._null_variants

    def counting_variants(seg, seed):
        call_count["n"] += 1
        return original(seg, seed=seed)

    rng = np.random.default_rng(8)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)
    monkeypatch.setattr(run_eeg, "_null_variants", counting_variants)

    run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                compute_nulls=True, include_legacy_proxy=False)

    # sfreq=128, win=512, step=256 → windows at [0, 256, 512] = 3 windows
    n_windows = len(range(0, 1024 - 512 + 1, 256))
    assert call_count["n"] == n_windows, (
        f"_null_variants called {call_count['n']} times; expected {n_windows} "
        f"(once per window, not once per band)"
    )


# ── run() with compute_nulls=False (default) ─────────────────────────────────

def test_run_no_nulls_by_default(tmp_path, monkeypatch):
    """Default compute_nulls=False emits no null rows."""
    from pipelines import run_eeg

    rng = np.random.default_rng(42)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=False)

    null_rows = df[df["metric_kind"].str.startswith("null_")]
    assert len(null_rows) == 0


def test_run_no_nulls_still_has_null_columns(tmp_path, monkeypatch):
    """null_method, null_seed, window_null_seed columns present even when compute_nulls=False."""
    from pipelines import run_eeg

    rng = np.random.default_rng(0)
    data = rng.standard_normal((4, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test")
    assert "null_method" in df.columns
    assert "null_seed" in df.columns
    assert "window_null_seed" in df.columns


def test_run_analytic_rows_have_empty_null_fields(tmp_path, monkeypatch):
    """Observed analytic_phase_proxy rows have empty null_method/null_seed/window_null_seed."""
    from pipelines import run_eeg

    rng = np.random.default_rng(0)
    data = rng.standard_normal((4, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test")
    obs = df[df["metric_kind"] == "analytic_phase_proxy"]
    assert len(obs) > 0
    assert (obs["null_method"] == "").all()
    assert (obs["null_seed"] == "").all()
    assert (obs["window_null_seed"] == "").all()


# ── run() with compute_nulls=True ────────────────────────────────────────────

def test_run_with_nulls_emits_null_rows(tmp_path, monkeypatch):
    """compute_nulls=True emits null rows for each analytic band."""
    from pipelines import run_eeg

    rng = np.random.default_rng(0)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=True)

    null_rows = df[df["metric_kind"].str.startswith("null_")]
    assert len(null_rows) > 0


def test_run_null_count_equals_observed_times_3(tmp_path, monkeypatch):
    """For each analytic_phase_proxy row, exactly 3 null rows exist."""
    from pipelines import run_eeg

    rng = np.random.default_rng(1)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=True, include_legacy_proxy=False)

    obs = df[df["metric_kind"] == "analytic_phase_proxy"]
    null = df[df["metric_kind"].str.startswith("null_")]
    assert len(null) == len(obs) * 3


def test_run_null_metric_kinds(tmp_path, monkeypatch):
    """Null rows carry exactly the three expected metric_kind values."""
    from pipelines import run_eeg

    rng = np.random.default_rng(2)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=True, include_legacy_proxy=False)

    null_kinds = set(df[df["metric_kind"].str.startswith("null_")]["metric_kind"].unique())
    assert null_kinds == {"null_channel_shuffle", "null_time_reverse", "null_phase_randomized"}


def test_run_null_rows_have_null_method_and_seed(tmp_path, monkeypatch):
    """Null rows carry non-empty null_method, null_seed (base), and window_null_seed (derived)."""
    from pipelines import run_eeg

    rng = np.random.default_rng(3)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=True)
    null = df[df["metric_kind"].str.startswith("null_")]
    assert (null["null_method"] != "").all()
    assert (null["null_seed"] != "").all()
    assert (null["window_null_seed"] != "").all()


def test_run_null_seed_base_seed_in_column(tmp_path, monkeypatch):
    """null_seed column on null rows holds the base seed argument passed to run()."""
    from pipelines import run_eeg

    rng = np.random.default_rng(9)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    base_seed = 77
    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=True, null_seed=base_seed)
    null = df[df["metric_kind"].str.startswith("null_")]
    assert (null["null_seed"] == base_seed).all(), (
        "null_seed column must hold the base seed argument, not the derived window seed"
    )


def test_run_window_null_seed_differs_across_windows(tmp_path, monkeypatch):
    """Different windows produce different window_null_seed values."""
    from pipelines import run_eeg

    rng = np.random.default_rng(10)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=True, include_legacy_proxy=False)
    null = df[df["metric_kind"].str.startswith("null_")]
    # With 3 windows the derived seed must differ across windows
    unique_window_seeds = null["window_null_seed"].unique()
    assert len(unique_window_seeds) > 1, (
        "Expected different window_null_seed values for different windows"
    )


def test_run_null_rows_preserve_band_and_metadata(tmp_path, monkeypatch):
    """Null rows carry the same band and window metadata as their observed counterparts."""
    from pipelines import run_eeg

    rng = np.random.default_rng(4)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=True, include_legacy_proxy=False)

    obs_bands = set(df[df["metric_kind"] == "analytic_phase_proxy"]["band"].unique())
    null_bands = set(df[df["metric_kind"].str.startswith("null_")]["band"].unique())
    assert obs_bands == null_bands

    for col in ("dataset", "file", "window_id", "start_sample", "stop_sample"):
        obs_vals = set(df[df["metric_kind"] == "analytic_phase_proxy"][col].unique())
        null_vals = set(df[df["metric_kind"].str.startswith("null_")][col].unique())
        assert obs_vals == null_vals, f"metadata mismatch in '{col}'"


def test_run_null_metric_values_finite(tmp_path, monkeypatch):
    """Q, Qabs, phase_grad, f_dress are finite in all null rows."""
    from pipelines import run_eeg

    rng = np.random.default_rng(5)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=True, include_legacy_proxy=False)
    null = df[df["metric_kind"].str.startswith("null_")]
    for col in ("Q", "Qabs", "phase_grad", "f_dress"):
        assert null[col].notna().all(), f"NaN in null column '{col}'"
        assert np.isfinite(null[col].values).all(), f"non-finite in null column '{col}'"


def test_run_temporal_proxy_not_nulled(tmp_path, monkeypatch):
    """temporal_phase_proxy rows are not matched by null rows."""
    from pipelines import run_eeg

    rng = np.random.default_rng(6)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=True, include_legacy_proxy=True)

    legacy = df[df["metric_kind"] == "temporal_phase_proxy"]
    assert len(legacy) > 0
    # legacy rows should have empty null fields (not being null-controlled)
    assert (legacy["null_method"] == "").all()


def test_run_empty_dir_no_crash(tmp_path):
    """Empty directory with compute_nulls=True produces empty DataFrame."""
    from pipelines.run_eeg import run
    df = run(tmp_path, tmp_path / "out.csv", dataset="test", compute_nulls=True)
    assert len(df) == 0


def test_run_null_seed_reproducible(tmp_path, monkeypatch):
    """Same null_seed produces identical null row values across two runs."""
    from pipelines import run_eeg

    rng = np.random.default_rng(7)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)

    df1 = run_eeg.run(tmp_path, tmp_path / "out1.csv", dataset="test",
                      compute_nulls=True, null_seed=99)
    df2 = run_eeg.run(tmp_path, tmp_path / "out2.csv", dataset="test",
                      compute_nulls=True, null_seed=99)

    cols = ["metric_kind", "band", "Q", "Qabs", "window_null_seed"]
    null1 = df1[df1["metric_kind"].str.startswith("null_")][cols]
    null2 = df2[df2["metric_kind"].str.startswith("null_")][cols]
    assert null1.reset_index(drop=True).equals(null2.reset_index(drop=True))


# ── compute_pci=True with null rows uses null-segment pcist_proxy ─────────────

def test_run_null_pci_uses_null_segment(tmp_path, monkeypatch):
    """When compute_pci=True, null rows get pcist_proxy from their null segment.

    We monkeypatch pcist_proxy to return float(np.sum(x)) so values differ by
    segment content. We then verify null rows have non-null pcist_proxy and that
    pcist_proxy was called more than once per window (once for observed + once
    per null method).
    """
    from pipelines import run_eeg

    call_inputs: list[np.ndarray] = []

    def recording_pcist_proxy(x: np.ndarray) -> float:
        call_inputs.append(x)
        return float(np.sum(x))

    rng = np.random.default_rng(11)
    data = rng.standard_normal((8, 1024))
    fake = FakeRaw(data, sfreq=128.0)

    (tmp_path / "fake.edf").touch()
    monkeypatch.setattr(run_eeg, "_load_raw", lambda _: fake)
    monkeypatch.setattr(run_eeg, "_preprocess", lambda x: x)
    monkeypatch.setattr(run_eeg, "pcist_proxy", recording_pcist_proxy)

    df = run_eeg.run(tmp_path, tmp_path / "out.csv", dataset="test",
                     compute_nulls=True, compute_pci=True,
                     include_legacy_proxy=False)

    null = df[df["metric_kind"].str.startswith("null_")]
    assert "pcist_proxy" in null.columns
    assert null["pcist_proxy"].notna().all(), "null rows must have non-null pcist_proxy"

    # With 3 windows × (1 observed + 3 nulls) = 12 calls to pcist_proxy
    n_windows = len(range(0, 1024 - 512 + 1, 256))
    assert len(call_inputs) == n_windows * 4, (
        f"Expected {n_windows * 4} pcist_proxy calls (1 observed + 3 null per window), "
        f"got {len(call_inputs)}"
    )

    # Null rows should not all share the observed row's pcist_proxy value,
    # since recording_pcist_proxy(seg) != recording_pcist_proxy(null_seg)
    # for channel_shuffle and time_reverse (which change sum).
    obs = df[df["metric_kind"] == "analytic_phase_proxy"]
    obs_pci_values = set(obs["pcist_proxy"].unique())
    null_pci_values = set(null["pcist_proxy"].unique())
    # At least some null values must differ from all observed values
    assert len(null_pci_values - obs_pci_values) > 0, (
        "Expected at least some null pcist_proxy values to differ from observed values"
    )
