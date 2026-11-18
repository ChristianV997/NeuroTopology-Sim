"""Channel / unit / sampling-rate QC on top of `adapters.mne_bids*`.

Synthetic data only: an 8-channel, 2 s, 256 Hz BIDS-EDF recording generated
at test time into tmp_path (well under 256 KiB). The `n/a`-units and the
250-vs-256 Hz sidecar cases are synthetic reproductions of metadata patterns
seen in a public dataset; no real data is used or vendored. No network.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from adapters.mne_bids_qc import (
    QC_SUMMARY_KEY,
    ChannelQCError,
    SamplingFrequencyMismatchError,
    build_channel_qc,
    check_sampling_frequency,
    check_unit,
    qc_bids_recording,
)

FIXTURE_CHANNELS = ["F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2"]
SFREQ = 256.0
DURATION_S = 2.0
HAS_EEG_EXTRA = all(importlib.util.find_spec(m) is not None for m in ("mne", "mne_bids", "edfio"))


def _rows(units="\u00b5V", types="EEG", names=FIXTURE_CHANNELS, status=None):
    units = [units] * len(names) if isinstance(units, str) or units is None else units
    types = [types] * len(names) if isinstance(types, str) else types
    status = status or ["good"] * len(names)
    return [{"name": n, "type": t, "units": u, "status": s} for n, t, u, s in zip(names, types, units, status)]


def _qc(**kw):
    base = dict(
        channel_rows=_rows(),
        header_channel_names=FIXTURE_CHANNELS,
        sidecar={"SamplingFrequency": SFREQ},
        header_sfreq_hz=SFREQ,
    )
    base.update(kw)
    return build_channel_qc(**base)


# ── units ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("unit,canon,scale", [
    ("V", "V", 1.0),
    ("mV", "mV", 1e-3),
    ("\u00b5V", "\u00b5V", 1e-6),  # micro sign
    ("uV", "\u00b5V", 1e-6),
    ("\u03bcV", "\u00b5V", 1e-6),  # greek mu
    ("microV", "\u00b5V", 1e-6),  # ds001787 spelling
    ("microv", "\u00b5V", 1e-6),
    ("MICROV", "\u00b5V", 1e-6),
    (" microV ", "\u00b5V", 1e-6),
    ("millivolt", "mV", 1e-3),
    ("Volt", "V", 1.0),
])
def test_unit_aliases_normalise_to_canonical_and_volts(unit, canon, scale):
    assert check_unit(unit, "EEG") == ("OK", canon, scale)


def test_microvolt_canonical_is_micro_sign():
    assert check_unit("\u03bcV", "EEG")[1] == "\u00b5V"
    assert check_unit("microV", "EEG")[1].encode("utf-8") == b"\xc2\xb5V"


@pytest.mark.parametrize("unit", ["n/a", "N/A", "", None, float("nan")])
def test_missing_units_are_flagged_not_assumed(unit):
    assert check_unit(unit, "EEG") == ("UNITS_MISSING", None, None)


@pytest.mark.parametrize("unit", ["microvolts", "nV", "mv", "uv", "volts", "furlongs", "\u00b5S"])
def test_unknown_units_flagged(unit):
    assert check_unit(unit, "EEG") == ("UNITS_UNKNOWN", None, None)


def test_raw_unit_recorded_next_to_normalised():
    units = ["microV", "uV", "\u03bcV", "\u00b5V", "mV", "V", "n/a", "bogus"]
    body = _qc(channel_rows=_rows(units=units)).to_qc_summary()[QC_SUMMARY_KEY]
    trace = body["unit_trace"]
    assert trace["F3"] == {"raw": "microV", "normalised": "\u00b5V", "flag": "OK"}
    assert trace["C3"] == {"raw": "\u03bcV", "normalised": "\u00b5V", "flag": "OK"}
    assert trace["O1"] == {"raw": "n/a", "normalised": None, "flag": "UNITS_MISSING"}
    assert trace["O2"] == {"raw": "bogus", "normalised": None, "flag": "UNITS_UNKNOWN"}


def test_alias_spellings_do_not_count_as_mixed_units():
    units = ["microV", "uV", "\u03bcV", "\u00b5V"] * 2
    rep = _qc(channel_rows=_rows(units=units))
    assert rep.status == "pass"
    assert set(rep.units_canonical.values()) == {"\u00b5V"}


def test_empty_and_unknown_units_raise_distinct_flags():
    units = ["", "n/a", "bogus"] + ["\u00b5V"] * 5
    rep = _qc(channel_rows=_rows(units=units))
    codes = {f.channel: f.code for f in rep.flags if f.code.startswith("UNITS_")}
    assert codes == {"F3": "UNITS_MISSING", "F4": "UNITS_MISSING", "C3": "UNITS_UNKNOWN"}


def test_non_voltage_channel_units_not_checked():
    assert check_unit("n/a", "TRIG") == ("NOT_VOLTAGE_TYPE", None, None)


def test_all_na_units_produce_explicit_flags():
    rep = _qc(channel_rows=_rows(units="n/a"))
    assert set(rep.unit_qc_flags.values()) == {"UNITS_MISSING"}
    assert all(v is None for v in rep.scale_to_volts.values())
    assert sum(f.code == "UNITS_MISSING" for f in rep.flags) == len(FIXTURE_CHANNELS)
    assert rep.status == "flagged"


def test_mixed_eeg_units_flagged():
    units = ["\u00b5V"] * 7 + ["V"]
    rep = _qc(channel_rows=_rows(units=units))
    assert any(f.code == "MIXED_EEG_UNITS" for f in rep.flags)
    assert rep.scale_to_volts["O2"] == 1.0 and rep.scale_to_volts["F3"] == 1e-6


# ── channel types / metadata ─────────────────────────────────────────────


def test_clean_metadata_passes():
    rep = _qc()
    assert rep.status == "pass"
    assert rep.flags == []
    assert rep.channel_names == FIXTURE_CHANNELS
    assert set(rep.channel_types.values()) == {"EEG"}


def test_unknown_channel_type_flagged():
    types = ["EEG"] * 7 + ["BRAINWAVE"]
    rep = _qc(channel_rows=_rows(types=types))
    assert [f.channel for f in rep.flags if f.code == "UNKNOWN_CHANNEL_TYPE"] == ["O2"]


def test_lowercase_bids_type_accepted_and_eog_checked_as_voltage():
    types = ["eeg"] * 7 + ["eog"]
    rep = _qc(channel_rows=_rows(types=types))
    assert rep.channel_types["O2"] == "EOG"
    assert rep.unit_qc_flags["O2"] == "OK"
    assert rep.status == "pass"


def test_declared_bad_channels_carried_not_inferred():
    status = ["good"] * 7 + ["bad"]
    rep = _qc(channel_rows=_rows(status=status))
    assert rep.bad_channels == ["O2"]


@pytest.mark.parametrize("rows", [[], [{"name": "", "type": "EEG", "units": "V"}], _rows(names=["F3", "F3"])])
def test_structurally_invalid_channels_tsv_rejected(rows):
    with pytest.raises(ChannelQCError):
        _qc(channel_rows=rows)


# ── missing / expected channels ──────────────────────────────────────────


def test_missing_expected_channels_mask():
    rep = _qc(expected_channels=["F3", "Fz", "Cz", "O2"])
    assert rep.missing_channel_mask == {"F3": False, "Fz": True, "Cz": True, "O2": False}
    assert rep.missing_channels == ["Fz", "Cz"]
    assert [f.channel for f in rep.flags if f.code == "MISSING_EXPECTED_CHANNEL"] == ["Fz", "Cz"]


def test_channel_in_tsv_but_not_header_counts_as_missing():
    header = FIXTURE_CHANNELS[:-1]
    rep = _qc(header_channel_names=header, expected_channels=["O2"])
    assert rep.missing_channel_mask == {"O2": True}
    assert any(f.code == "TSV_CHANNEL_NOT_IN_HEADER" and f.channel == "O2" for f in rep.flags)


def test_header_channel_not_in_tsv_flagged():
    rep = _qc(header_channel_names=FIXTURE_CHANNELS + ["Status"])
    assert any(f.code == "HEADER_CHANNEL_NOT_IN_TSV" and f.channel == "Status" for f in rep.flags)


# ── sampling rate ────────────────────────────────────────────────────────


def test_sampling_frequency_mismatch_raises_by_default():
    with pytest.raises(SamplingFrequencyMismatchError):
        _qc(sidecar={"SamplingFrequency": 250.0}, header_sfreq_hz=256.0)


def test_sampling_frequency_mismatch_flag_mode():
    rep = _qc(sidecar={"SamplingFrequency": 250.0}, header_sfreq_hz=256.0, on_sfreq_mismatch="flag")
    assert rep.sampling_frequency_mismatch is True
    assert any(f.code == "SAMPLING_FREQUENCY_MISMATCH" for f in rep.flags)


@pytest.mark.parametrize("value", [None, "n/a", 0, -1])
def test_missing_sidecar_sampling_frequency_flagged(value):
    side, mismatch, flags = check_sampling_frequency(value, 256.0)
    assert side is None and mismatch is False
    assert [f.code for f in flags] == ["SIDECAR_SFREQ_MISSING"]


# ── existing manifest alignment + reproducibility ────────────────────────


def test_summary_fits_existing_manifest_qc_summary():
    from adapters.mne_bids_feature_recipe_schema import DerivedFeatureRecipeManifestV1

    summary = _qc(channel_rows=_rows(units="n/a"), expected_channels=["Fz"]).to_qc_summary()
    manifest = DerivedFeatureRecipeManifestV1.make(
        recipe_id="r" * 16,
        dataset_id="synthetic-qc",
        qc_summary=summary,
        limitations=["synthetic fixture; channel/unit/sampling QC only"],
        provenance="adapters.mne_bids_qc synthetic test",
    )
    assert manifest.validate() == []
    round_trip = DerivedFeatureRecipeManifestV1.from_json(manifest.to_json())
    body = round_trip.qc_summary[QC_SUMMARY_KEY]
    assert body["missing_channel_mask"] == {"Fz": True}
    assert set(body["unit_qc_flags"].values()) == {"UNITS_MISSING"}
    assert body["sampling_frequency_mismatch"] is False


def test_qc_hash_is_reproducible_and_sensitive():
    a = _qc(expected_channels=["Fz"]).to_qc_summary()[QC_SUMMARY_KEY]
    b = _qc(expected_channels=["Fz"]).to_qc_summary()[QC_SUMMARY_KEY]
    c = _qc(expected_channels=["Cz"]).to_qc_summary()[QC_SUMMARY_KEY]
    assert a["qc_hash"] == b["qc_hash"] != c["qc_hash"]


def test_summary_has_no_score_or_detector_fields():
    text = json.dumps(_qc().to_qc_summary()).lower()
    for term in ("score", "detector", "diagnos", "awaken", "jhana", "liberation"):
        assert term not in text


# ── end to end through existing readers (optional EEG profile) ───────────


@pytest.fixture
def synthetic_bids_recording(tmp_path):
    import mne
    from mne_bids import BIDSPath, write_raw_bids

    rng = np.random.default_rng(20261117)
    n = int(SFREQ * DURATION_S)
    t = np.arange(n) / SFREQ
    data = 10e-6 * np.sin(2 * np.pi * 10.0 * t)[None, :] + rng.normal(0.0, 2e-6, (len(FIXTURE_CHANNELS), n))
    info = mne.create_info(FIXTURE_CHANNELS, SFREQ, "eeg")
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    root = tmp_path / "bids"
    bp = BIDSPath(subject="01", task="synthetic", root=root, datatype="eeg")
    write_raw_bids(raw, bp, format="EDF", allow_preload=True, overwrite=True, verbose="ERROR")
    rec = Path(bp.copy().update(suffix="eeg", extension=".edf").fpath)
    total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    assert total < 256 * 1024
    return root, rec, bp


def _rewrite_channels_units(bp, unit):
    from mne_bids.tsv_handler import _from_tsv, _to_tsv

    path = Path(bp.copy().update(suffix="channels", extension=".tsv").fpath)
    tsv = _from_tsv(str(path))
    tsv["units"] = [unit] * len(tsv["name"])
    _to_tsv(tsv, str(path))


def _rewrite_sidecar_sfreq(bp, sfreq):
    path = Path(bp.copy().update(suffix="eeg", extension=".json").fpath)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["SamplingFrequency"] = sfreq
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.requires_mne
@pytest.mark.skipif(not HAS_EEG_EXTRA, reason="requires mne, mne-bids and edfio (requirements-eeg.txt)")
def test_end_to_end_clean_recording(synthetic_bids_recording):
    from data.bids_ingest import clear_raw_cache

    root, rec, _ = synthetic_bids_recording
    clear_raw_cache()
    rep = qc_bids_recording(rec, bids_root=root, expected_channels=FIXTURE_CHANNELS + ["Cz"])
    assert rep.sampling_frequency_header_hz == SFREQ == rep.sampling_frequency_sidecar_hz
    assert rep.missing_channels == ["Cz"]
    assert set(rep.unit_qc_flags.values()) == {"OK"}
    assert [f.code for f in rep.flags] == ["MISSING_EXPECTED_CHANNEL"]
    assert all(len(f["sha256"]) == 64 for f in rep.input_files)
    again = qc_bids_recording(rec, bids_root=root, expected_channels=FIXTURE_CHANNELS + ["Cz"])
    assert rep.to_qc_summary() == again.to_qc_summary()


@pytest.mark.requires_mne
@pytest.mark.skipif(not HAS_EEG_EXTRA, reason="requires mne, mne-bids and edfio (requirements-eeg.txt)")
def test_end_to_end_na_units(synthetic_bids_recording):
    from data.bids_ingest import clear_raw_cache

    root, rec, bp = synthetic_bids_recording
    _rewrite_channels_units(bp, "n/a")
    clear_raw_cache()
    rep = qc_bids_recording(rec, bids_root=root)
    assert set(rep.unit_qc_flags.values()) == {"UNITS_MISSING"}
    assert rep.status == "flagged"


@pytest.mark.requires_mne
@pytest.mark.skipif(not HAS_EEG_EXTRA, reason="requires mne, mne-bids and edfio (requirements-eeg.txt)")
def test_end_to_end_sidecar_250_vs_header_256_fails_loudly(synthetic_bids_recording):
    from data.bids_ingest import clear_raw_cache

    root, rec, bp = synthetic_bids_recording
    _rewrite_sidecar_sfreq(bp, 250.0)
    clear_raw_cache()
    with pytest.raises(SamplingFrequencyMismatchError, match="sidecar=250.0 header=256.0"):
        qc_bids_recording(rec, bids_root=root)
    rep = qc_bids_recording(rec, bids_root=root, on_sfreq_mismatch="flag")
    assert rep.sampling_frequency_mismatch is True
