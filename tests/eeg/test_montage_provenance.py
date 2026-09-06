"""Tests for montage resolution, coordinate binding, and provenance tracking.

Scientific guardrails:
- Sensor positions in SI units (meters).
- Explicit identification of unmatched channels.
- No geometric fabrication: unmatched electrodes remain explicitly unmatched.
"""
from __future__ import annotations

import numpy as np
import pytest

from sciencer_d.btc_icft.io.eeg_mne_adapter import (
    iter_mne_signal_chunks,
    resolve_montage_coordinates,
)


class MockRawWithChs:
    """Mock MNE Raw object for testing montage resolution."""

    def __init__(self, ch_names: list[str], locs: list[list[float]] | None = None):
        self.ch_names = list(ch_names)
        self.info = {"chs": []}
        for i, name in enumerate(ch_names):
            loc = locs[i] if locs is not None else [0.0] * 12
            self.info["chs"].append({"ch_name": name, "loc": np.array(loc)})


class TestMontageResolution:
    """Test 3D sensor coordinate resolution and fallback behavior."""

    def test_raw_with_existing_coordinates(self):
        # 3 channels with non-zero 3D positions in meters
        ch_names = ["E1", "E2", "E3"]
        locs = [
            [0.02, 0.08, 0.05] + [0.0] * 9,
            [-0.02, 0.08, 0.05] + [0.0] * 9,
            [0.0, 0.0, 0.09] + [0.0] * 9,
        ]
        mock_raw = MockRawWithChs(ch_names, locs)

        res = resolve_montage_coordinates(mock_raw)
        assert res["montage_source"] == "raw_montage"
        assert res["matched_channels"] == ch_names
        assert len(res["unmatched_channels"]) == 0
        assert res["coordinates"]["E1"] == pytest.approx([0.02, 0.08, 0.05])

    def test_standard_1020_fallback(self):
        mne = pytest.importorskip("mne")
        # Standard 10-20 channel names, but zero coordinates in raw
        ch_names = ["Fp1", "Fp2", "Fz", "Cz", "Pz", "Oz"]
        mock_raw = MockRawWithChs(ch_names)

        res = resolve_montage_coordinates(mock_raw)
        assert res["montage_source"] == "standard_1020"
        assert set(res["matched_channels"]) == set(ch_names)
        assert len(res["unmatched_channels"]) == 0

        # Check physical realism in SI meters (head radius ~8-10 cm -> ~0.08-0.10 m)
        cz_coord = res["coordinates"]["Cz"]
        radius = np.sqrt(cz_coord[0] ** 2 + cz_coord[1] ** 2 + cz_coord[2] ** 2)
        assert 0.05 < radius < 0.15

    def test_unmatched_channels_reported(self):
        mne = pytest.importorskip("mne")
        # Mixture of standard 10-20 channels and non-standard/auxiliary channels
        ch_names = ["Fz", "Cz", "CUSTOM_SENS_1", "HEOG"]
        mock_raw = MockRawWithChs(ch_names)

        res = resolve_montage_coordinates(mock_raw)
        assert res["montage_source"] == "standard_1020"
        assert "Fz" in res["matched_channels"]
        assert "Cz" in res["matched_channels"]
        assert "CUSTOM_SENS_1" in res["unmatched_channels"]
        assert "HEOG" in res["unmatched_channels"]
        assert any("CUSTOM_SENS_1" in w for w in res["warnings"])

    def test_completely_unmatched_raw(self):
        # Channels that match neither 10-20 nor 10-05
        ch_names = ["X1", "X2", "X3"]
        mock_raw = MockRawWithChs(ch_names)

        res = resolve_montage_coordinates(mock_raw)
        assert res["montage_source"] == "none"
        assert len(res["matched_channels"]) == 0
        assert res["unmatched_channels"] == ch_names
        assert any("No 3D sensor coordinates resolved" in w for w in res["warnings"])

    def test_montage_in_streaming_chunks(self, tmp_path):
        mne = pytest.importorskip("mne")
        ch_names = ["Fz", "Cz", "NON_STANDARD_AUX"]
        sfreq = 100.0
        data = np.ones((len(ch_names), 300))
        info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
        raw = mne.io.RawArray(data, info, verbose="ERROR")

        fif_path = tmp_path / "montage_test_raw.fif"
        raw.save(str(fif_path), overwrite=True, verbose="ERROR")

        chunks = list(iter_mne_signal_chunks(fif_path, chunk_seconds=1.0))
        assert len(chunks) == 3

        c0 = chunks[0]
        assert c0.montage_source == "standard_1020"
        assert "Fz" in c0.montage_coordinates
        assert "Cz" in c0.montage_coordinates
        assert "NON_STANDARD_AUX" not in c0.montage_coordinates
        assert "NON_STANDARD_AUX" in c0.unmatched_channels
        assert any("NON_STANDARD_AUX" in w for w in c0.warnings)
