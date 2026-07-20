"""Real Level-M windows from actual EEG samples for ds001787 (expert vs novice
meditation, with continuous depth-of-meditation probes).

Two window-building modes (see ds001787_windows.py's module docstring for why
they're kept separate rather than mixed into one uniform scheme):

  mode="fixed": N windows evenly spaced across each recording, labeled with the
  subject's expert/novice trait group (from participants.tsv). Used for
  Analysis A. Independent of probe-timing alignment.

  mode="probe_locked": one window per successfully cross-clock-aligned probe
  (see ds001787_behavioral.py), spanning from the previous aligned probe (or
  recording start) to this probe's events.tsv-relative onset, labeled with
  that probe's depth-of-meditation/mind-wandering/tiredness ratings. Used for
  Analysis B. Requires `behavioral_data` (parsed via
  `ds001787_behavioral.parse_behavioral_zip`) and per-session events.tsv;
  subject/sessions whose alignment fails the quality gate emit zero
  probe_locked windows (not fabricated ones) plus a warning.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from sciencer_d.btc_icft.level_m.features import extract_level_m_features
from sciencer_d.btc_icft.level_m.ds001787_windows import LevelMWindowRow
from sciencer_d.btc_icft.level_m.ds001787_behavioral import (
    align_probes_to_stim_onsets,
)

import sys
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.bids_ingest import discover_bids_eeg, read_window_signal  # noqa: E402


def load_participant_groups(bids_root: str) -> dict[str, str]:
    """subject_id ("sub-001") -> "expert" | "novice", from participants.tsv."""
    p = Path(bids_root) / "participants.tsv"
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    with p.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            pid = row.get("participant_id")
            group = row.get("group")
            if pid and group:
                out[pid] = group
    return out


def _recording_duration_s(source_file: str) -> float | None:
    """Prefer the eeg.json sidecar's RecordingDuration (cheap); fall back to
    opening the raw file with mne (preload=False) if the sidecar is missing."""
    json_path = Path(source_file).with_suffix(".json")
    if json_path.exists():
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
            dur = meta.get("RecordingDuration")
            if dur:
                return float(dur)
        except Exception:
            pass
    try:
        import mne

        raw = mne.io.read_raw(source_file, preload=False, verbose="ERROR")
        return float(raw.n_times) / float(raw.info["sfreq"])
    except Exception:
        return None


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
        # OSError: a companion file for a multi-file format can be genuinely
        # missing even though the main file exists -- see
        # level_m/base_windows_real.py's docstring for the real case this
        # was found on (ds003816).
        warns.append(f"window skipped: {exc}")
        feats = {"spectral_power_proxy": None, "entropy_proxy": None, "lzc_proxy": None, "artifact_score": None}
    return feats, warns


def _events_tsv_path(source_file: str) -> Path:
    p = Path(source_file)
    stem = p.name.replace("_eeg" + p.suffix, "")
    return p.parent / f"{stem}_events.tsv"


def _load_stim_onsets(events_path: Path) -> list[float]:
    if not events_path.exists():
        return []
    onsets = []
    with events_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("trial_type") == "stimulus":
                try:
                    onsets.append(float(row["onset"]))
                except (ValueError, KeyError):
                    continue
    return onsets


def build_and_extract_real_windows(
    bids_root: str,
    mode: str = "fixed",
    n_fixed_windows: int = 6,
    window_seconds: float = 10.0,
    max_channels: int | None = 16,
    subject_filter: str | None = None,
    behavioral_data: dict | None = None,
) -> list[LevelMWindowRow]:
    """Discover -> window -> extract REAL features for ds001787.

    `bids_root` must be the dataset root (mne_bids misparses a root whose own
    path looks like a sub-XXXX entity -- same constraint as ds005620/ds003969).
    `behavioral_data` (required for mode="probe_locked") is the dict returned by
    `ds001787_behavioral.parse_behavioral_zip`.
    """
    if mode not in ("fixed", "probe_locked"):
        raise ValueError(f"Unknown mode: {mode!r}")
    if mode == "probe_locked" and behavioral_data is None:
        raise ValueError("mode='probe_locked' requires behavioral_data")

    groups = load_participant_groups(bids_root)
    records = discover_bids_eeg(bids_root)
    if subject_filter is not None:
        records = [r for r in records if r.subject_id == subject_filter]

    rows: list[LevelMWindowRow] = []
    for rec in records:
        if not rec.is_eeg_candidate:
            continue
        subject = rec.subject_id or "unknown_subject"
        group = groups.get(subject)
        path_hash = hashlib.sha256(rec.relative_path.encode("utf-8")).hexdigest()[:8]

        if mode == "fixed":
            duration = _recording_duration_s(rec.path)
            if not duration or duration <= window_seconds:
                continue
            # evenly spaced window START times across [0, duration - window_seconds]
            usable_span = duration - window_seconds
            for idx in range(n_fixed_windows):
                w_start = 0.0 if n_fixed_windows <= 1 else (idx / (n_fixed_windows - 1)) * usable_span
                w_end = w_start + window_seconds
                feats, warns = _feats_for_window(rec.path, w_start, w_end, max_channels)
                row = LevelMWindowRow(
                    row_id=f"{subject}_{rec.session_id or 'nosess'}_{rec.run_id or 'norun'}_fixed_win-{idx}_{path_hash}",
                    subject_id=subject, session_id=rec.session_id, run_id=rec.run_id,
                    window_id=f"win-{idx}", task_label=rec.task_label, state_label=group,
                    behavior_label=None, report_label=None, y=None,
                    source_file=rec.path, window_start_s=w_start, window_end_s=w_end,
                    warnings=warns, window_mode="fixed", **feats,
                )
                rows.append(row)

        else:  # probe_locked
            # behavioral_data's subject keys are the 2-digit zero-padded numeric
            # strings the zip's own filenames use (e.g. "01" from sub01_info.txt),
            # NOT the BIDS subject_id's own zero-padding width (which happens to
            # also be 3 digits here, e.g. "sub-001" -> naive "001" doesn't match).
            subject_int = int(subject.replace("sub-", ""))
            subnum_2digit = f"{subject_int:02d}"
            ses_num = (rec.session_id or "ses-01").replace("ses-", "").lstrip("0") or "1"
            beh_for_sub = behavioral_data.get(subnum_2digit)
            if not beh_for_sub or ses_num not in beh_for_sub:
                continue
            probes = beh_for_sub[ses_num]
            events_path = _events_tsv_path(rec.path)
            stim_onsets = _load_stim_onsets(events_path)
            if not stim_onsets:
                continue
            aligned, diag = align_probes_to_stim_onsets(stim_onsets, probes)
            if not diag["usable"]:
                continue
            aligned.sort(key=lambda a: a.stim_onset_s)
            prev_end = 0.0
            for idx, probe in enumerate(aligned):
                w_start, w_end = prev_end, probe.stim_onset_s
                prev_end = probe.stim_onset_s
                if w_end - w_start < 1.0:  # degenerate/zero-length epoch, skip
                    continue
                feats, warns = _feats_for_window(rec.path, w_start, w_end, max_channels)
                warns.append(
                    f"probe_locked window; alignment match_rate={diag['match_rate']:.2f}, offset={diag['offset_s']:.1f}s"
                )
                row = LevelMWindowRow(
                    row_id=f"{subject}_{rec.session_id or 'nosess'}_{rec.run_id or 'norun'}_probe_win-{idx}_{path_hash}",
                    subject_id=subject, session_id=rec.session_id, run_id=rec.run_id,
                    window_id=f"win-{idx}", task_label=rec.task_label, state_label=group,
                    behavior_label=None, report_label=None, y=None,
                    source_file=rec.path, window_start_s=w_start, window_end_s=w_end,
                    warnings=warns, window_mode="probe_locked",
                    depth_of_meditation=probe.depth_of_meditation,
                    depth_of_mind_wandering=probe.depth_of_mind_wandering,
                    tiredness=probe.tiredness,
                    **feats,
                )
                rows.append(row)
    return rows
