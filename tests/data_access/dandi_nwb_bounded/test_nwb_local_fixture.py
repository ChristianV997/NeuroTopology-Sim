"""Local HDF5 fixture coverage for NWB metadata preservation and full-read reject.

Uses only synthetic local files. Never contacts DANDI or AWS.
"""
from __future__ import annotations

import importlib.util

import numpy as np
import pytest

_HAVE_H5PY = importlib.util.find_spec("h5py") is not None
pytestmark = pytest.mark.skipif(not _HAVE_H5PY, reason="requires h5py")


def _make_fake_nwb(tmp_path, rate=100.0, n_samples=1000, n_ch=4):
    import h5py

    path = tmp_path / "fake.nwb"
    with h5py.File(path, "w") as handle:
        acq = handle.create_group("acquisition")
        es = acq.create_group("ElectricalSeriesEEG")
        data = np.zeros((n_samples, n_ch), dtype="float32")
        dset = es.create_dataset("data", data=data)
        dset.attrs["unit"] = "volts"
        ts = np.arange(n_samples) / rate
        tset = es.create_dataset("timestamps", data=ts)
        tset.attrs["unit"] = "seconds"
        es.attrs["montage"] = "standard_1020"
        dt = h5py.special_dtype(vlen=str)
        es.create_dataset("channel_names", data=np.array([f"ch{i}" for i in range(n_ch)], dtype=object), dtype=dt)
    return path


def test_nwb_info_preserves_metadata_fields(tmp_path):
    from data.dandi_nwb_ingest import open_nwb_lazy, nwb_eeg_info

    path = _make_fake_nwb(tmp_path)
    handle = open_nwb_lazy(str(path), network_permission=False)
    try:
        with handle as nwb:
            info = nwb_eeg_info(nwb)
            assert abs(info["sampling_rate_hz"] - 100.0) < 1.0
            assert info["timestamps_present"] is True
            assert info["timestamp_unit"] == "seconds"
            assert info["units"] == "volts"
            assert info["channel_identity"] == ["ch0", "ch1", "ch2", "ch3"]
            assert info["montage"] == "standard_1020"
            assert info["source_series"] == "ElectricalSeriesEEG"
    finally:
        handle.close()
        assert handle.closed is True


def test_full_recording_window_rejected(tmp_path):
    from data.dandi_nwb_ingest import IngestionContractError, open_nwb_lazy, nwb_eeg_info, read_nwb_eeg_window

    path = _make_fake_nwb(tmp_path, n_samples=500)
    with open_nwb_lazy(str(path)) as nwb:
        info = nwb_eeg_info(nwb)
        with pytest.raises(IngestionContractError, match="full-recording"):
            read_nwb_eeg_window(nwb, info["t_start_s"], info["t_end_s"], max_channels=2, info=info)


def test_bounded_window_still_reads(tmp_path):
    from data.dandi_nwb_ingest import open_nwb_lazy, read_nwb_eeg_window

    path = _make_fake_nwb(tmp_path, n_samples=1000)
    with open_nwb_lazy(str(path)) as nwb:
        block = read_nwb_eeg_window(nwb, 0.0, 1.0, pick="all", max_channels=2)
        assert block.shape == (2, 100)
