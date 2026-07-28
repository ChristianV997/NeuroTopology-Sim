"""Real event-locked TMS-EEG evoked responses + PCIst for ds004917 (inhibitory
TMS at intraparietal sulcus / posterior parietal cortex + a vertex control
site, decision-making-under-ambiguity task).

Unlike every generic-registry dataset in this repo, the object of interest
here is not a fixed-interval Level-M feature window but the TMS-evoked
response itself: `validation/pci_validation.py::pcist()` (Comolatti et al.
2019's state-transition Perturbational Complexity Index) needs a genuine
perturbation-evoked recording with a real pre-stimulus baseline, which no
other dataset onboarded in this repo provides -- PCIst is the flagship
capability this dataset activates.

Real per-event TMS-site markers were confirmed via direct S3 inspection of
`sub-*_task-pdm_events.tsv`: `TMSips`/`TMSppc`/`TMSvertex` columns are
populated (0 or 1) only on `value==10` rows (the TMS pulse-delivery
marker) -- exactly one of the three is 1, identifying which site that
pulse targeted. This module groups pulses by site, extracts a peri-pulse
epoch per pulse, and trial-averages within (subject, site) to build one
evoked response per site -- the standard TMS-EEG unit `pcist()` expects.

Minimal, HONEST TMS-artifact handling: the TMS pulse itself saturates/rings
the amplifier for a few ms; this module linearly interpolates across
`artifact_window_ms` (default [-2, +5] ms around the pulse) before
averaging. This is NOT full clinical-grade TMS-EEG preprocessing (no
SOUND/ICA-based decay-artifact removal, no bad-channel/bad-trial
rejection) -- every output row's warnings say so explicitly. Treat PCIst
values from this module as a first-pass real-data activation of the
capability, not a publication-grade replication of the source study.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.bids_ingest import discover_bids_eeg  # noqa: E402
from data.preprocessing import preprocess_raw  # noqa: E402
from validation.pci_validation import pcist  # noqa: E402

_DEFAULT_PREPROCESS = dict(l_freq=1.0, h_freq=45.0, reference="average")

_SITE_COLUMNS = {"ips": "TMSips", "ppc": "TMSppc", "vertex": "TMSvertex"}
_TMS_PULSE_VALUE = "10"


def _events_tsv_path(source_file: str) -> Path:
    p = Path(source_file)
    stem = p.name.replace("_eeg" + p.suffix, "")
    return p.parent / f"{stem}_events.tsv"


def load_tms_pulse_onsets_by_site(events_path: Path) -> dict[str, list[float]]:
    """{"ips": [...], "ppc": [...], "vertex": [...]} pulse onset times (s),
    read structurally from the real TMSips/TMSppc/TMSvertex event columns --
    no site inferred, only what the dataset itself marks."""
    out: dict[str, list[float]] = {site: [] for site in _SITE_COLUMNS}
    if not events_path.exists():
        return out
    with events_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("value") != _TMS_PULSE_VALUE:
                continue
            try:
                onset = float(row["onset"])
            except (KeyError, ValueError):
                continue
            for site, col in _SITE_COLUMNS.items():
                if row.get(col) == "1":
                    out[site].append(onset)
    return out


def _interpolate_artifact(times_ms: np.ndarray, epoch: np.ndarray, artifact_window_ms: tuple[float, float]) -> np.ndarray:
    """Linear interpolation across the TMS-pulse artifact window, per channel."""
    lo, hi = artifact_window_ms
    mask = (times_ms >= lo) & (times_ms <= hi)
    if not mask.any() or mask.all():
        return epoch
    good_idx = np.where(~mask)[0]
    bad_idx = np.where(mask)[0]
    out = epoch.copy()
    for ch in range(epoch.shape[0]):
        out[ch, bad_idx] = np.interp(bad_idx, good_idx, epoch[ch, good_idx])
    return out


def _read_raw_any(path: str):
    """Format-dispatching raw reader matching data/bids_ingest.py::_read_raw's
    own extension handling (kept local rather than importing that
    underscore-prefixed helper across modules)."""
    import mne

    p = Path(path)
    ext = p.suffix.lower()
    common = dict(preload=False, verbose="ERROR")
    if ext == ".edf":
        return mne.io.read_raw_edf(str(p), **common)
    if ext == ".bdf":
        return mne.io.read_raw_bdf(str(p), **common)
    if ext == ".vhdr":
        return mne.io.read_raw_brainvision(str(p), **common)
    if ext == ".set":
        return mne.io.read_raw_eeglab(str(p), **common)
    if ext == ".fif":
        return mne.io.read_raw_fif(str(p), **common)
    raise ValueError(f"Unsupported EEG extension for {path}: {ext}")


def build_evoked_response(
    source_file: str,
    pulse_onsets_s: list[float],
    pre_s: float = 0.4,
    post_s: float = 0.3,
    artifact_window_ms: tuple[float, float] = (-2.0, 5.0),
    max_channels: int | None = None,
    preprocess: dict | None = None,
) -> tuple[np.ndarray, np.ndarray, int, list[str]]:
    """Trial-average peri-pulse epochs into one evoked response.

    Bandpass-filters + re-references the FULL recording ONCE (real PCIst
    needs filtered data -- raw unfiltered voltage is dominated by slow
    drift that swamps the SNR-component filter and drove every trial's
    output to a degenerate 0.0 in first-pass testing against real ds004917
    data), then slices every trial's epoch from that single filtered raw --
    NOT one filter-per-trial (would be ~80x slower for no benefit, since
    filtering the full recording once and slicing windows out avoids the
    edge-transient problem per-window filtering has, same rationale as
    `data/preprocessing.py::preprocess_raw`'s own docstring).

    Returns (signal_evk (n_channels, n_times), times_ms (n_times,),
    n_trials_used, warnings). Trials whose epoch would extend before
    recording start are skipped (not zero-padded).
    """
    import mne

    warnings: list[str] = [
        f"minimal TMS-artifact handling: linear interpolation across "
        f"{artifact_window_ms} ms around each pulse, not full clinical-grade "
        f"TMS-EEG artifact removal (no SOUND/ICA decay correction)"
    ]
    raw = _read_raw_any(source_file)
    # Pick the EEG channels we'll actually use BEFORE filtering, not after:
    # `preprocess_raw` bandpass-filters every channel it's given, so filtering
    # all ~66 channels then discarding all but `max_channels` wastes ~4x the
    # filter compute on data that is thrown away. Disclosed side effect: the
    # average reference inside `preprocess_raw` is then computed over the
    # `max_channels` picked channels rather than all EEG channels -- acceptable
    # and consistent with how `max_channels` truncation already narrows the
    # montage everywhere else in this repo's real-signal path.
    eeg_picks = mne.pick_types(raw.info, eeg=True)
    if max_channels:
        eeg_picks = eeg_picks[:max_channels]
    raw.pick([raw.ch_names[i] for i in eeg_picks])
    preprocess_raw(raw, **(preprocess if preprocess is not None else _DEFAULT_PREPROCESS))
    sfreq = float(raw.info["sfreq"])
    n_total = raw.n_times

    epochs: list[np.ndarray] = []
    times_ms: np.ndarray | None = None
    for onset in pulse_onsets_s:
        w_start, w_end = onset - pre_s, onset + post_s
        start_samp = int(round(w_start * sfreq))
        stop_samp = int(round(w_end * sfreq))
        if start_samp < 0 or stop_samp > n_total or stop_samp <= start_samp:
            warnings.append(f"trial at onset={onset:.3f}s skipped: window out of recording range")
            continue
        data = raw.get_data(start=start_samp, stop=stop_samp)
        n_samples = data.shape[1]
        t_ms = (np.arange(n_samples) / n_samples) * (pre_s + post_s) * 1000.0 - pre_s * 1000.0
        data = _interpolate_artifact(t_ms, data, artifact_window_ms)
        if times_ms is None:
            times_ms = t_ms
        elif len(t_ms) != len(times_ms):
            # sample-count drift across trials (rounding); align to the
            # shortest to keep the average well-defined
            n = min(len(t_ms), len(times_ms))
            times_ms, data = times_ms[:n], data[:, :n]
            epochs = [e[:, :n] for e in epochs]
        epochs.append(data)

    if not epochs:
        return np.empty((0, 0)), np.empty((0,)), 0, warnings + ["no usable trials"]

    signal_evk = np.mean(np.stack(epochs, axis=0), axis=0)
    return signal_evk, times_ms, len(epochs), warnings


def compute_pcist_by_site(
    bids_root: str,
    subject_filter: str | None = None,
    max_channels: int | None = None,
    min_trials: int = 5,
) -> list[dict]:
    """Discover -> group TMS pulses by site -> trial-average -> real PCIst,
    one row per (subject, site) with >= min_trials usable pulses.
    """
    records = discover_bids_eeg(bids_root)
    if subject_filter is not None:
        records = [r for r in records if r.subject_id == subject_filter]

    rows: list[dict] = []
    for rec in records:
        if not rec.is_eeg_candidate or rec.task_label != "pdm":
            continue
        subject = rec.subject_id or "unknown_subject"
        onsets_by_site = load_tms_pulse_onsets_by_site(_events_tsv_path(rec.path))

        for site, onsets in onsets_by_site.items():
            if len(onsets) < min_trials:
                rows.append({
                    "subject_id": subject, "site": site, "n_trials": len(onsets),
                    "pcist": None, "warnings": [f"only {len(onsets)} trials, need >= {min_trials}"],
                    "source_file": rec.path,
                })
                continue
            signal_evk, times_ms, n_used, warns = build_evoked_response(
                rec.path, onsets, max_channels=max_channels,
            )
            if n_used < min_trials:
                rows.append({
                    "subject_id": subject, "site": site, "n_trials": n_used,
                    "pcist": None, "warnings": warns + [f"only {n_used} usable trials after filtering"],
                    "source_file": rec.path,
                })
                continue
            try:
                value = pcist(signal_evk, times_ms)
            except Exception as exc:  # pragma: no cover -- surfaced via warnings, not silently swallowed
                rows.append({
                    "subject_id": subject, "site": site, "n_trials": n_used,
                    "pcist": None, "warnings": warns + [f"pcist() failed: {exc}"],
                    "source_file": rec.path,
                })
                continue
            rows.append({
                "subject_id": subject, "site": site, "n_trials": n_used,
                "pcist": value, "warnings": warns, "source_file": rec.path,
            })
    return rows
