from __future__ import annotations

from pathlib import Path

import numpy as np

import pipelines.run_eeg as run_eeg


class FakeRaw:
    def __init__(self, data, sfreq=128.0):
        self._data = data
        self.n_times = data.shape[1]
        self.ch_names = [f"EEG{i}" for i in range(data.shape[0])]
        self.info = {"sfreq": sfreq}

    def copy(self):
        return self

    def load_data(self):
        return self

    def pick_types(self, eeg=True, exclude=None):
        return self

    def filter(self, *args, **kwargs):
        return self

    def notch_filter(self, *args, **kwargs):
        return self

    def set_eeg_reference(self, *args, **kwargs):
        return self

    def get_data(self, start=0, stop=None):
        return self._data[:, start:stop]


def _run(monkeypatch, tmp_path, with_montage=True, compute_phase_grid_topology=False):
    rng = np.random.default_rng(0)
    data = rng.standard_normal((6, 512))
    fake = FakeRaw(data)
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    (in_dir / "sub-01_task-awake_eeg.edf").write_text("x")
    out_csv = tmp_path / "out.csv"

    monkeypatch.setattr(run_eeg, "_load_raw", lambda p: fake)
    if with_montage:
        monkeypatch.setattr(run_eeg, "get_channel_xy", lambda raw, montage=None: (raw.ch_names, np.c_[np.arange(6), np.arange(6)]))
        monkeypatch.setattr(run_eeg, "triangulate_xy", lambda xy: np.array([[0, 1, 2], [2, 3, 4], [1, 4, 5]]))
    else:
        monkeypatch.setattr(run_eeg, "get_channel_xy", lambda raw, montage=None: (_ for _ in ()).throw(ValueError("missing")))

    df = run_eeg.run(in_dir, out_csv, "ds", compute_phase_grid_topology=compute_phase_grid_topology)
    return df


def test_no_phase_grid_rows_when_disabled(monkeypatch, tmp_path):
    df = _run(monkeypatch, tmp_path, with_montage=True, compute_phase_grid_topology=False)
    assert not (df["metric_kind"] == "phase_grid_topology").any()


def test_phase_grid_rows_when_enabled(monkeypatch, tmp_path):
    df = _run(monkeypatch, tmp_path, with_montage=True, compute_phase_grid_topology=True)
    topo = df[df["metric_kind"] == "phase_grid_topology"]
    assert len(topo) > 0


def test_missing_montage_skips_without_crash(monkeypatch, tmp_path):
    df = _run(monkeypatch, tmp_path, with_montage=False, compute_phase_grid_topology=True)
    assert len(df) > 0
    assert not (df["metric_kind"] == "phase_grid_topology").any()


def test_phase_grid_rows_preserve_metadata(monkeypatch, tmp_path):
    df = _run(monkeypatch, tmp_path, with_montage=True, compute_phase_grid_topology=True)
    topo = df[df["metric_kind"] == "phase_grid_topology"]
    row = topo.iloc[0]
    assert row["band"]
    assert row["window_id"]
    assert row["dataset"] == "ds"


def test_phase_grid_rows_finite_metrics(monkeypatch, tmp_path):
    df = _run(monkeypatch, tmp_path, with_montage=True, compute_phase_grid_topology=True)
    topo = df[df["metric_kind"] == "phase_grid_topology"]
    for col in ["Q", "Qabs", "f_dress", "phase_grad"]:
        assert np.isfinite(topo[col].astype(float)).all()
