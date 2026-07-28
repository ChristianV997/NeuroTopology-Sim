"""Real Level-M windows from actual EEG samples for ds005555 (Bitbrain Open
Access Sleep, BOAS) -- full-night PSG-scored sleep-stage EEG.

Unlike every other dataset in this repo's registry, ds005555's state comes
from a per-epoch AASM sleep-stage label in a companion events.tsv
(`stage_hum`, the 3-expert-scorer consensus -- see the BOAS README's
"Sleep staging labels" section), not from a BIDS task entity in the
filename (every recording's task entity is literally "Sleep"). This does
not fit `sciencer_d/btc_icft/level_m/generic_windows_real.py`'s
task-entity-driven `task_to_state` map, so it gets this dedicated module --
same category as ds001787's dual-mode module (see that module's docstring
for the parallel).

Stage codes (from ds005555/README, "Sleep staging labels"):
  0 = Wake, 1 = N1, 2 = N2, 3 = N3, 4 = REM,
  8 = PSG disconnection (human-scored only), -2 = artifact (AI-scored only).
Only the human-consensus `stage_hum` column is used (more authoritative than
the AI-scored `stage_ai`); codes 8 and any non-integer value are skipped
(not fabricated into a state).

Only the PSG acquisition (`acq-psg`) is used -- 6-channel clinical 10-20 EEG
(F3/F4/C3/C4/O1/O2), matching this dataset's authoritative human scoring.
The wearable headband acquisition (`acq-headband`, 2 forehead channels) is
intentionally excluded: too few channels for montage-aware Level-T topology.
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

_STAGE_NAMES = {"0": "wake", "1": "n1", "2": "n2", "3": "n3", "4": "rem"}


def _events_tsv_path(source_file: str) -> Path:
    p = Path(source_file)
    stem = p.name.replace("_eeg" + p.suffix, "")
    return p.parent / f"{stem}_events.tsv"


def _load_scored_epochs(events_path: Path) -> list[tuple[float, float, str]]:
    """(onset_s, duration_s, stage_name) per scored 30s epoch, disconnections/
    unrecognized codes skipped (not fabricated)."""
    if not events_path.exists():
        return []
    out: list[tuple[float, float, str]] = []
    with events_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            code = row.get("stage_hum")
            stage = _STAGE_NAMES.get(code)
            if stage is None:
                continue
            try:
                onset = float(row["onset"])
                duration = float(row["duration"])
            except (KeyError, ValueError):
                continue
            out.append((onset, duration, stage))
    return out


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
    max_windows_per_file: int = 40,
    max_channels: int | None = 6,
    subject_filter: str | None = None,
) -> list[LevelMWindowRow]:
    """Discover -> per-scored-epoch window -> extract REAL features for ds005555.

    One window per human-consensus-scored 30s epoch (dataset's own scoring
    resolution, not a configurable window_seconds), capped at
    `max_windows_per_file` per recording (evenly subsampled across the night,
    not just the first N, so short-latency stages like REM aren't
    systematically excluded on a truncated run).

    `bids_root` must be the dataset root -- same mne_bids constraint as every
    other real-signal module here. Only `acq-psg` recordings are windowed.
    """
    records = discover_bids_eeg(bids_root)
    if subject_filter is not None:
        records = [r for r in records if r.subject_id == subject_filter]

    rows: list[LevelMWindowRow] = []
    for rec in records:
        if not rec.is_eeg_candidate or rec.acq_label != "psg":
            continue
        subject = rec.subject_id or "unknown_subject"
        path_hash = hashlib.sha256(rec.relative_path.encode("utf-8")).hexdigest()[:8]

        epochs = _load_scored_epochs(_events_tsv_path(rec.path))
        if not epochs:
            continue
        if len(epochs) > max_windows_per_file:
            idxs = np.linspace(0, len(epochs) - 1, max_windows_per_file).round().astype(int)
            epochs = [epochs[i] for i in sorted(set(idxs.tolist()))]

        for idx, (onset, duration, stage) in enumerate(epochs):
            w_start, w_end = onset, onset + duration
            feats, warns = _feats_for_window(rec.path, w_start, w_end, max_channels)
            row = LevelMWindowRow(
                row_id=f"{subject}_{rec.session_id or 'nosess'}_{rec.run_id or 'norun'}_epoch-{idx}_{path_hash}",
                subject_id=subject, session_id=rec.session_id, run_id=rec.run_id,
                window_id=f"win-{idx}", task_label=rec.task_label, state_label=stage,
                behavior_label=None, report_label=None, y=None,
                source_file=rec.path, window_start_s=w_start, window_end_s=w_end,
                warnings=warns, **feats,
            )
            rows.append(row)
    return rows
