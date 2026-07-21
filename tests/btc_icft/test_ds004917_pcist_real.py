"""Synthetic ground-truth test for the ds004917 TMS-EEG event-locked module,
run BEFORE any real-data verification (per this repo's established
discipline for new real-signal capability wiring).

Builds a synthetic BIDS EEG recording with a real companion events.tsv using
ds004917's actual (structurally-confirmed via S3) column layout
(onset/duration/value/TMSips/TMSppc/TMSvertex), embeds a genuine structured
evoked response after "vertex" pulses and pure noise after "ips" pulses, and
checks the whole pipeline -- event parsing -> trial-averaging -> real
PCIst -- recovers the expected ordering (structured > noise), mirroring
tests/test_pci_validation.py's own ground-truth pattern for `pcist()`
itself.
"""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import numpy as np
import pytest

_HAVE = all(importlib.util.find_spec(m) for m in ("mne", "mne_bids", "edfio"))
pytestmark = pytest.mark.skipif(not _HAVE, reason="requires mne, mne-bids, edfio")

from sciencer_d.btc_icft.level_m.ds004917_pcist_real import (
    load_tms_pulse_onsets_by_site,
    build_evoked_response,
    compute_pcist_by_site,
)


def _build_synth_tms_bids(root, n_pulses_per_site=12, sfreq=1000.0, n_ch=6, seed=0):
    import mne
    from mne_bids import BIDSPath, write_raw_bids

    rng = np.random.default_rng(seed)
    total_s = 200.0
    n = int(sfreq * total_s)
    sig = rng.standard_normal((n_ch, n)) * 1.0

    # Pulse onsets, evenly spaced, starting well after t=0 so every trial has
    # a full pre-stimulus baseline available.
    ips_onsets = [10.0 + i * 3.0 for i in range(n_pulses_per_site)]
    vertex_onsets = [11.5 + i * 3.0 for i in range(n_pulses_per_site)]

    # Embed a genuine, channel-differentiated evoked response ONLY after
    # vertex pulses (present in response window, absent from baseline) --
    # ips pulses get no embedded structure, i.e. stay pure noise.
    t_resp = np.arange(int(sfreq * 0.3)) / sfreq
    for onset in vertex_onsets:
        i0 = int(onset * sfreq)
        for ch in range(n_ch):
            freq = 8 + 3 * ch
            resp = 8.0 * np.sin(2 * np.pi * freq * t_resp)
            sig[ch, i0:i0 + len(resp)] += resp

    info = mne.create_info([f"EEG{i:02d}" for i in range(n_ch)], sfreq, ch_types="eeg")
    raw = mne.io.RawArray(sig * 1e-6, info, verbose="ERROR")
    raw.set_montage(mne.channels.make_standard_montage("standard_1020"), on_missing="ignore", verbose="ERROR")
    raw.info["line_freq"] = 60

    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    bp = BIDSPath(subject="01", task="pdm", datatype="eeg", root=root, suffix="eeg", extension=".edf")
    write_raw_bids(raw, bp, overwrite=True, allow_preload=True, format="EDF", verbose="ERROR")

    # Write the real ds004917 events.tsv column layout directly (custom
    # non-standard columns beyond onset/duration -- same approach the
    # dataset's own FieldTrip-based export uses).
    events_path = Path(str(bp.fpath).replace("_eeg.edf", "_events.tsv"))
    lines = ["onset\tduration\tvalue\tTMSips\tTMSppc\tTMSvertex"]
    for onset in ips_onsets:
        lines.append(f"{onset}\t1\t10\t1\t0\t0")
    for onset in vertex_onsets:
        lines.append(f"{onset}\t1\t10\t0\t0\t1")
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return str(root), str(bp.fpath), events_path


def test_load_tms_pulse_onsets_by_site_parses_real_column_layout(tmp_path):
    _, _, events_path = _build_synth_tms_bids(tmp_path / "bids", n_pulses_per_site=5)
    by_site = load_tms_pulse_onsets_by_site(events_path)
    assert len(by_site["ips"]) == 5
    assert len(by_site["ppc"]) == 0
    assert len(by_site["vertex"]) == 5
    assert by_site["ips"] != by_site["vertex"]


def test_build_evoked_response_trial_averages_and_interpolates_artifact(tmp_path):
    root, source_file, events_path = _build_synth_tms_bids(tmp_path / "bids", n_pulses_per_site=8)
    by_site = load_tms_pulse_onsets_by_site(events_path)
    signal_evk, times_ms, n_used, warns = build_evoked_response(source_file, by_site["vertex"], max_channels=6)
    assert n_used == 8
    assert signal_evk.shape[0] == 6
    assert times_ms.min() < -350 and times_ms.max() > 250
    assert any("artifact" in w for w in warns)
    # artifact window itself must be finite (interpolated, not left as raw spike)
    artifact_mask = (times_ms >= -2.0) & (times_ms <= 5.0)
    assert np.all(np.isfinite(signal_evk[:, artifact_mask]))


def test_pcist_by_site_recovers_structured_vs_noise_ordering(tmp_path):
    """The ground-truth guarantee: the site with a genuine embedded evoked
    response (vertex) must score higher real PCIst than the pure-noise site
    (ips) -- same ordering guarantee as tests/test_pci_validation.py's own
    pcist() ground-truth test, now proven through this module's full
    discover -> group -> trial-average -> pcist() pipeline."""
    root, _, _ = _build_synth_tms_bids(tmp_path / "bids", n_pulses_per_site=12, seed=3)
    rows = compute_pcist_by_site(root, max_channels=6, min_trials=5)

    by_site = {r["site"]: r for r in rows}
    assert by_site["ips"]["pcist"] is not None
    assert by_site["vertex"]["pcist"] is not None
    assert by_site["ppc"]["pcist"] is None  # zero real trials for this site in the fixture
    assert by_site["vertex"]["pcist"] > by_site["ips"]["pcist"]
    assert by_site["vertex"]["n_trials"] == 12
    assert by_site["ips"]["n_trials"] == 12
