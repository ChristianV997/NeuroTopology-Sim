"""Tests for DANDI/NWB ingestion (data/dandi_nwb_ingest.py) and the 000458
awake/anesthetized windower. The remote-read paths are exercised against a
tiny in-memory HDF5 file so no network is required; the state-interval logic
is tested directly."""
from __future__ import annotations

import importlib.util

import numpy as np
import pytest

_HAVE_H5PY = importlib.util.find_spec("h5py") is not None
pytestmark = pytest.mark.skipif(not _HAVE_H5PY, reason="requires h5py")


def _make_fake_nwb(tmp_path, rate=100.0, n_samples=6000, n_ch=8,
                   induction_start=20.0, anesth=(30.0, 50.0)):
    """Write a minimal HDF5 file shaped like the 000458 NWB EEG + epochs subset
    that dandi_nwb_ingest reads (acquisition/ElectricalSeriesEEG + intervals/epochs)."""
    import h5py

    p = tmp_path / "fake.nwb"
    with h5py.File(p, "w") as f:
        acq = f.create_group("acquisition")
        es = acq.create_group("ElectricalSeriesEEG")
        rng = np.random.default_rng(0)
        data = rng.standard_normal((n_samples, n_ch)).astype("int16")
        es.create_dataset("data", data=data)
        ts = np.arange(n_samples) / rate
        es.create_dataset("timestamps", data=ts)
        iv = f.create_group("intervals")
        ep = iv.create_group("epochs")
        ep.create_dataset("start_time", data=np.array([induction_start, anesth[0]]))
        ep.create_dataset("stop_time", data=np.array([anesth[0], anesth[1]]))
        # ragged tags column (NWB DynamicTable convention): tags + tags_index
        dt = h5py.special_dtype(vlen=str)
        ep.create_dataset("tags", data=np.array(["isoflurane_induction", "isoflurane_anesthesia"], dtype=object), dtype=dt)
        ep.create_dataset("tags_index", data=np.array([1, 2]))
    return p


def test_nwb_eeg_info_and_window_read(tmp_path):
    import h5py
    from data.dandi_nwb_ingest import nwb_eeg_info, read_nwb_eeg_window

    p = _make_fake_nwb(tmp_path)
    with h5py.File(p, "r") as f:
        info = nwb_eeg_info(f)
        assert info["n_channels"] == 8
        assert abs(info["rate_hz"] - 100.0) < 1.0
        block = read_nwb_eeg_window(f, 0.0, 5.0, pick="all", max_channels=4)
        assert block.shape[0] == 4  # channels
        assert block.shape[1] == 500  # 5s * 100Hz
        mean = read_nwb_eeg_window(f, 0.0, 5.0, pick="mean")
        assert mean.ndim == 1


def test_nwb_window_out_of_range_raises(tmp_path):
    import h5py
    from data.dandi_nwb_ingest import read_nwb_eeg_window

    p = _make_fake_nwb(tmp_path)
    with h5py.File(p, "r") as f:
        with pytest.raises(ValueError):
            read_nwb_eeg_window(f, 0.0, 10_000.0)


def test_state_epochs_read_from_real_tags(tmp_path):
    import h5py
    from data.dandi_nwb_ingest import nwb_state_epochs

    p = _make_fake_nwb(tmp_path, induction_start=20.0, anesth=(30.0, 50.0))
    with h5py.File(p, "r") as f:
        epochs = nwb_state_epochs(f)
    tags = [t for t, _, _ in epochs]
    assert tags == ["isoflurane_induction", "isoflurane_anesthesia"]
    assert epochs[1] == ("isoflurane_anesthesia", 30.0, 50.0)


def test_state_interval_logic_awake_is_pre_induction():
    from sciencer_d.btc_icft.level_m.dandi000458_windows_real import _state_intervals

    epochs = [("isoflurane_induction", 20.0, 30.0), ("isoflurane_anesthesia", 30.0, 50.0)]
    intervals = _state_intervals(epochs, rec_t0=0.0)
    assert ("awake", 0.0, 20.0) in intervals
    assert ("anesthetized", 30.0, 50.0) in intervals
    # induction transition (20-30s) is excluded
    assert all(state != "induction" for state, _, _ in intervals)


def test_no_anesthesia_epoch_yields_no_anesthetized_state():
    from sciencer_d.btc_icft.level_m.dandi000458_windows_real import _state_intervals

    epochs = [("isoflurane_induction", 20.0, 30.0)]  # no anesthesia epoch
    intervals = _state_intervals(epochs, rec_t0=0.0)
    states = {s for s, _, _ in intervals}
    assert "anesthetized" not in states  # not fabricated
    assert "awake" in states
