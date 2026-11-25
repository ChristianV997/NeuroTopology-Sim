"""Fail-closed: extract_mne_signal_windows must never coerce non-finite → 0.0."""

from __future__ import annotations

import importlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

from sciencer_d.btc_icft.io import eeg_mne_adapter as a
from sciencer_d.btc_icft.io.mne_signal_block_conversion import (
    convert_mne_windows_to_canonical_blocks,
)


def _install_fake_mne(monkeypatch, raw_factory):
    class IO:
        @staticmethod
        def read_raw_edf(*args, **kwargs):
            return raw_factory()

    class M:
        __version__ = "1.0"
        io = IO()

    monkeypatch.setattr(importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(importlib, "import_module", lambda _name: M)


def test_non_finite_window_skipped_not_zero_filled(monkeypatch, tmp_path):
    class Raw:
        def __init__(self):
            self.info = {"sfreq": 100.0}
            self.ch_names = ["C3", "C4"]
            self.n_times = 200

        def get_data(self, picks=None, start=0, stop=1):
            rows = len(picks) if picks is not None else 2
            data = np.ones((rows, stop - start), dtype=float)
            # Inject non-finite into first window samples only.
            if start == 0:
                data[0, 0] = math.nan
            return data

    _install_fake_mne(monkeypatch, Raw)
    p = tmp_path / "a.edf"
    p.write_text("x", encoding="utf-8")
    r = a.extract_mne_signal_windows(str(p), "DS", window_seconds=1.0, max_windows=2)

    assert r.n_windows == 2
    bad, good = r.windows[0], r.windows[1]

    assert bad["extraction_status"] == "skipped_non_finite"
    assert bad["scientific_pass"] is False
    assert bad["is_valid"] is False
    assert bad["non_finite_samples"] is True
    assert bad["signal_values"] is None
    assert "non_finite_replaced" not in bad["warnings"]
    assert "non_finite_values_detected" in bad["warnings"]

    assert good["extraction_status"] == "extracted"
    assert good["is_valid"] is True
    assert good["signal_values"] is not None
    assert all(math.isfinite(v) for ch in good["signal_values"] for v in ch)

    assert r.scientific_pass is False
    assert "non_finite_windows_skipped" in r.warnings

    # No observed zero charge/metric fabricated from NaN replacement.
    flat = json.dumps(r.windows, allow_nan=False)
    assert "non_finite_replaced" not in flat


def test_all_non_finite_windows_block_scientific_pass(monkeypatch, tmp_path):
    class Raw:
        def __init__(self):
            self.info = {"sfreq": 50.0}
            self.ch_names = ["Cz"]
            self.n_times = 100

        def get_data(self, picks=None, start=0, stop=1):
            rows = len(picks) if picks is not None else 1
            data = np.full((rows, stop - start), math.inf, dtype=float)
            return data

    _install_fake_mne(monkeypatch, Raw)
    p = tmp_path / "b.edf"
    p.write_text("x", encoding="utf-8")
    r = a.extract_mne_signal_windows(str(p), "DS", window_seconds=1.0, max_windows=1)

    assert r.n_windows == 1
    w = r.windows[0]
    assert w["signal_values"] is None
    assert w["scientific_pass"] is False
    assert w["is_valid"] is False
    assert "all_windows_non_finite" in r.extraction_blockers
    assert r.scientific_pass is False

    outs = a.write_mne_signal_outputs(r, str(tmp_path / "out"))
    vals = json.loads(Path(outs["mne_signal_window_values.json"]).read_text())
    assert vals["windows"][0]["signal_values"] is None
    rep = json.loads(Path(outs["mne_extraction_report.json"]).read_text())
    assert rep["ready_for_signal_block_conversion"] is False
    assert rep["scientific_pass"] is False
    assert rep["n_ready_windows"] == 0


def test_non_finite_never_becomes_observed_zero_in_conversion(monkeypatch, tmp_path):
    class Raw:
        def __init__(self):
            self.info = {"sfreq": 100.0}
            self.ch_names = ["C3"]
            self.n_times = 100

        def get_data(self, picks=None, start=0, stop=1):
            data = np.zeros((1, stop - start), dtype=float)
            data[0, 5] = math.nan
            return data

    _install_fake_mne(monkeypatch, Raw)
    p = tmp_path / "c.edf"
    p.write_text("x", encoding="utf-8")
    r = a.extract_mne_signal_windows(str(p), "DS", window_seconds=1.0, max_windows=1)
    w = r.windows[0]
    assert w["signal_values"] is None

    # If we had replaced NaN with 0.0, conversion would accept an all-zero window.
    # Fail-closed path must reject instead.
    meta = {
        "dataset_id": "DS",
        "source_file": str(p),
        "extraction_status": r.extraction_status,
    }
    values = {
        "dataset_id": "DS",
        "source_file": str(p),
        "windows": [
            {
                "row_id": w["row_id"],
                "window_id": w["window_id"],
                "channel_names": w["channel_names"],
                "signal_values": w["signal_values"],
            }
        ],
    }
    conv = convert_mne_windows_to_canonical_blocks(meta, r.windows, values, "DS")
    assert conv.n_converted_windows == 0
    assert conv.n_rejected_windows == 1
    assert conv.rejected_windows[0]["reason"] == "skipped_non_finite"
    assert not conv.ready_for_level_t_signal


def test_finite_windows_still_extract(monkeypatch, tmp_path):
    class Raw:
        def __init__(self):
            self.info = {"sfreq": 100.0}
            self.ch_names = ["C3"]
            self.n_times = 200

        def get_data(self, picks=None, start=0, stop=1):
            return np.linspace(0.1, 0.9, stop - start, dtype=float).reshape(1, -1)

    _install_fake_mne(monkeypatch, Raw)
    p = tmp_path / "d.edf"
    p.write_text("x", encoding="utf-8")
    r = a.extract_mne_signal_windows(str(p), "DS", window_seconds=1.0, max_windows=2)
    assert r.scientific_pass is True
    assert all(w["is_valid"] and w["signal_values"] is not None for w in r.windows)
    src = Path(a.__file__).read_text(encoding="utf-8")
    assert "non_finite_replaced" not in src
    extract_body = src.split("def extract_mne_signal_windows")[1].split("def build_mne_adapter_omega_event")[0]
    assert "v = 0.0" not in extract_body
    assert "nan_to_num" not in extract_body
