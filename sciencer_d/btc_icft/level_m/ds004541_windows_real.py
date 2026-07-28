"""Real Level-M windows for ds004541 (multimodal EEG-fNIRS under general
anesthesia) -- awake vs. anesthetized, labeled by real loss/recovery-of-
consciousness event markers.

ds004541's state does not come from a BIDS task entity (every recording is
`task-anesthesia`) nor from a per-epoch label column. It comes from two
discrete transition markers in the companion events.tsv: `loc` (loss of
consciousness) and `roc` (recovery of consciousness) -- the canonical
behavioral consciousness-transition timestamps of anesthesia research. This
module windows the continuous recording into:

  - `awake`        : from recording start up to the `loc` onset
  - `anesthetized` : from `loc` up to `roc` (or to the recording end if the
                     subject has no `roc` marker)

Only the EEG modality is used (the fNIRS `.snirf` is ignored here -- this
repo's real-signal path is EEG-only). Channel names are standard 10-20
(Fp1/Fpz/AF3/...), no device prefix, so montage resolution works unchanged.

HONEST label handling (no_label_inference): a subject with no `loc` marker
in its events.tsv (confirmed to occur for real -- e.g. sub-11) yields ZERO
windows, not a fabricated state. Only the dataset's own real markers define
state boundaries; nothing is inferred from the task name or filename.
"""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.bids_ingest import discover_bids_eeg, read_window_signal  # noqa: E402
from sciencer_d.btc_icft.level_m.features import extract_level_m_features  # noqa: E402
from sciencer_d.btc_icft.level_m.generic_windows import LevelMWindowRow  # noqa: E402

_LOC_MARKER = "loc"
_ROC_MARKER = "roc"


def _events_tsv_path(source_file: str) -> Path:
    p = Path(source_file)
    stem = p.name.replace("_eeg" + p.suffix, "")
    return p.parent / f"{stem}_events.tsv"


def _marker_onset(events_path: Path, marker: str) -> float | None:
    """Onset (s) of the first row whose `trial_type` equals `marker`, or None
    if the marker is absent (a real case -- some subjects never reached LOC)."""
    if not events_path.exists():
        return None
    with events_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if (row.get("trial_type") or "").strip() == marker:
                try:
                    return float(row["onset"])
                except (KeyError, ValueError):
                    return None
    return None


def _state_intervals(events_path: Path, rec_end_s: float) -> list[tuple[str, float, float]]:
    """(state, start_s, end_s) intervals from the real loc/roc markers.

    No `loc` -> no intervals (empty): the subject's consciousness transition
    was never marked, so no window is labeled (not fabricated)."""
    loc = _marker_onset(events_path, _LOC_MARKER)
    if loc is None or loc <= 0:
        return []
    roc = _marker_onset(events_path, _ROC_MARKER)
    intervals: list[tuple[str, float, float]] = [("awake", 0.0, loc)]
    anesth_end = roc if (roc is not None and roc > loc) else rec_end_s
    if anesth_end > loc:
        intervals.append(("anesthetized", loc, anesth_end))
    return intervals


def _feats_for_window(source_file: str, w_start: float, w_end: float, max_channels: int | None) -> tuple[dict, list[str]]:
    warns: list[str] = ["real-EEG-derived Level M features (provenance=real_bids); per-window z-normalized"]
    try:
        signal = read_window_signal(source_file, w_start, w_end, pick="mean", max_channels=max_channels)
        raw_sig = np.asarray(signal, dtype=float)
        raw_power = float(np.mean(raw_sig ** 2))
        std = raw_sig.std()
        norm = (raw_sig - raw_sig.mean()) / std if std > 0 else raw_sig
        feats = extract_level_m_features([float(v) for v in norm])
        feats["spectral_power_proxy"] = raw_power
    except (ValueError, OSError) as exc:
        warns.append(f"window skipped: {exc}")
        feats = {"spectral_power_proxy": None, "entropy_proxy": None, "lzc_proxy": None, "artifact_score": None}
    return feats, warns


def build_and_extract_real_windows(
    bids_root: str,
    window_seconds: float = 10.0,
    max_windows_per_state: int = 10,
    max_channels: int | None = 16,
    subject_filter: str | None = None,
) -> list[LevelMWindowRow]:
    """Discover -> loc/roc-interval window -> extract REAL features for ds004541.

    Up to `max_windows_per_state` evenly-spaced `window_seconds` windows are
    taken from each of the awake and anesthetized intervals (evenly spaced, not
    just the first N, so the sampled windows aren't clustered at one edge of a
    long anesthesia maintenance period).

    `bids_root` must be the dataset root. Subjects without a `loc` marker yield
    no rows.
    """
    records = discover_bids_eeg(bids_root)
    if subject_filter is not None:
        records = [r for r in records if r.subject_id == subject_filter]

    rows: list[LevelMWindowRow] = []
    for rec in records:
        if not rec.is_eeg_candidate or rec.task_label != "anesthesia":
            continue
        subject = rec.subject_id or "unknown_subject"
        path_hash = hashlib.sha256(rec.relative_path.encode("utf-8")).hexdigest()[:8]

        try:
            rec_end_s = _recording_duration_s(rec.path)
        except (ValueError, OSError):
            continue

        intervals = _state_intervals(_events_tsv_path(rec.path), rec_end_s)
        if not intervals:
            continue

        for state, seg_start, seg_end in intervals:
            starts = _even_window_starts(seg_start, seg_end, window_seconds, max_windows_per_state)
            for idx, w_start in enumerate(starts):
                w_end = w_start + window_seconds
                feats, warns = _feats_for_window(rec.path, w_start, w_end, max_channels)
                row = LevelMWindowRow(
                    row_id=f"{subject}_{rec.session_id or 'nosess'}_{rec.run_id or 'norun'}_{state}-{idx}_{path_hash}",
                    subject_id=subject, session_id=rec.session_id, run_id=rec.run_id,
                    window_id=f"{state}-win-{idx}", task_label=rec.task_label, state_label=state,
                    behavior_label=None, report_label=None, y=None,
                    source_file=rec.path, window_start_s=w_start, window_end_s=w_end,
                    warnings=warns, **feats,
                )
                rows.append(row)
    return rows


def _recording_duration_s(source_file: str) -> float:
    """Total recording duration (s) via mne's header, without loading data."""
    import mne

    p = Path(source_file)
    ext = p.suffix.lower()
    reader = {
        ".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf,
        ".vhdr": mne.io.read_raw_brainvision, ".set": mne.io.read_raw_eeglab,
        ".fif": mne.io.read_raw_fif,
    }.get(ext)
    if reader is None:
        raise ValueError(f"Unsupported EEG extension: {ext}")
    raw = reader(str(p), preload=False, verbose="ERROR")
    return raw.n_times / float(raw.info["sfreq"])


def _even_window_starts(seg_start: float, seg_end: float, window_seconds: float, n_max: int) -> list[float]:
    """Up to `n_max` evenly-spaced window start times fitting fully inside
    [seg_start, seg_end)."""
    latest = seg_end - window_seconds
    if latest <= seg_start:
        return [seg_start] if seg_end - seg_start >= window_seconds * 0.5 else []
    n = min(n_max, max(1, int((seg_end - seg_start) // window_seconds)))
    return list(np.linspace(seg_start, latest, n))
