from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Load the pipeline module by path (dual_engine is not an importable package here).
_MOD_PATH = Path(__file__).resolve().parents[1] / "dual_engine" / "anesthesia_signed_winding_pipeline.py"
_spec = importlib.util.spec_from_file_location("anesthesia_signed_winding_pipeline", _MOD_PATH)
anp = importlib.util.module_from_spec(_spec)
import sys as _sys
_sys.modules["anesthesia_signed_winding_pipeline"] = anp  # so @dataclass __module__ resolves
_spec.loader.exec_module(anp)


# ── 10-20 zone mapping ───────────────────────────────────────────────────────

def test_zone_of_lobes():
    assert anp.zone_of("Fz") == "frontal"
    assert anp.zone_of("Fp1") == "frontal"
    assert anp.zone_of("AF3") == "frontal"
    assert anp.zone_of("Cz") == "central"
    assert anp.zone_of("CP3") == "central"
    assert anp.zone_of("FC4") == "central"
    assert anp.zone_of("Pz") == "parietal"
    assert anp.zone_of("PO3") == "parietal"
    assert anp.zone_of("POz") == "parietal"
    assert anp.zone_of("Oz") == "occipital"
    assert anp.zone_of("O1") == "occipital"
    assert anp.zone_of("Iz") == "occipital"


def test_save_timeseries_writes_csd_array(tmp_path):
    # durable --save-timeseries capability: a minimal montage-carrying Raw should
    # persist its scalp channels + names to a loadable .npz (the raw material the
    # surrogate gate needs, which prior runs discarded).
    import numpy as np
    import mne
    mne.set_log_level("ERROR")
    chs = ["Fz", "Cz", "Pz", "Oz", "F3", "F4", "P3", "P4"]
    rng = np.random.default_rng(0)
    info = mne.create_info(chs, sfreq=256.0, ch_types="eeg")
    raw = mne.io.RawArray(rng.standard_normal((len(chs), 1000)), info)
    raw.set_montage(anp._MONTAGE, on_missing="ignore")
    path = anp.save_timeseries(raw, "sub-001", "awake", "EC", tmp_path)
    z = np.load(path, allow_pickle=True)
    assert z["data"].shape[0] == len(chs) and z["data"].shape[1] == 1000
    assert list(z["ch_names"]) == chs
    assert str(z["provenance"]) == "real_eeg" and float(z["sfreq"]) == 256.0


def test_zone_of_temporal_hemisphere_by_parity():
    assert anp.zone_of("T7") == "temporal_L"     # odd -> left
    assert anp.zone_of("T8") == "temporal_R"     # even -> right
    assert anp.zone_of("FT7") == "temporal_L"
    assert anp.zone_of("FT8") == "temporal_R"
    assert anp.zone_of("TP9") == "temporal_L"
    assert anp.zone_of("TP10") == "temporal_R"   # trailing digit 0 -> even -> right


def test_zone_of_unknown_returns_none():
    assert anp.zone_of("VEOG") is None
    assert anp.zone_of("EMG") is None
    assert anp.zone_of("XYZ") is None


def test_build_region_labels_covers_scalp_only():
    names = ["Fp1", "Cz", "Pz", "O2", "T7", "T8", "VEOG", "EMG"]
    labels = anp.build_region_labels(names)
    # non-scalp channels get no label (so they can't leak into region aggregation)
    assert "VEOG" not in labels and "EMG" not in labels
    assert labels["Fp1"] == "frontal"
    assert labels["T7"] == "temporal_L" and labels["T8"] == "temporal_R"
    assert set(labels.values()) <= {
        "frontal", "central", "parietal", "occipital", "temporal_L", "temporal_R", "temporal_M"
    }


# ── condition / run extraction ───────────────────────────────────────────────

def test_conditions_for_has_awake_and_graded_sedation():
    items = anp.conditions_for("sub-1010")
    conds = {c for c, _run, _stem in items}
    assert conds == {"awake", "sed", "sed2"}
    # awake is eyes-closed baseline
    awake = [it for it in items if it[0] == "awake"]
    assert awake[0][2] == "task-awake_acq-EC"
    # sed / sed2 enumerate runs (awakenings); every stem matches its condition+run
    for cond, run, stem in items:
        if cond in ("sed", "sed2"):
            assert stem.startswith(f"task-{cond}_acq-rest_run-")
            assert run.startswith("run-")


def test_recording_result_defaults_provenance_real_eeg():
    r = anp.RecordingResult(subject="sub-1010", condition="awake", run="EC", status="ok")
    assert r.provenance == "real_eeg"
    from dataclasses import asdict
    d = asdict(r)
    assert d["provenance"] == "real_eeg" and d["bands"] == {}
