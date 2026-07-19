"""Real Level-M windows from actual EEG samples for ds003969 (meditation vs thinking).

Direct port of `ds005620_windows_real.py`'s real-signal extraction pattern:
reads REAL samples per window via `data.bids_ingest.read_window_signal` and feeds
them to `extract_level_m_features`, so features reflect signal, not filename/hash.
Same two fixes carried over (both apply identically here, same feature formulas):
  * per-window z-normalization for entropy_proxy/lzc_proxy (raw EEG is ~1e-5 scale,
    those proxies were written for ~[0,1]-range values and collapse to zero otherwise).
  * spectral_power_proxy kept on the raw (unnormalized) scale since z-normalizing
    flattens it to a near-constant.

Task label mapping is dataset-specific and was CONFIRMED via direct S3 listing of
ds003969 (sub-001/002/009 eeg/ dirs), not assumed: real BIDS task entities are
`med1breath`, `med2` (meditation blocks), `think1`, `think2` (thinking blocks).
No `acq` BIDS entity exists in this dataset (unlike ds005620's acq-EC/acq-EO), but
the row_id path-hash suffix is kept as the same hard uniqueness guarantee regardless.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from sciencer_d.btc_icft.level_m.features import extract_level_m_features
from sciencer_d.btc_icft.level_m.ds003969_windows import LevelMWindowRow

import sys
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.bids_ingest import discover_bids_eeg, read_window_signal  # noqa: E402

_TASK_TO_STATE = {
    "med1breath": "meditation",
    "med2": "meditation",
    "think1": "thinking",
    "think2": "thinking",
}


def build_and_extract_real_windows(
    bids_root: str,
    window_seconds: float = 10.0,
    max_windows_per_file: int = 2,
    max_channels: int | None = 16,
    subject_filter: str | None = None,
) -> list[LevelMWindowRow]:
    """Discover -> window -> extract REAL features for ds003969. Every row is
    marked real-EEG-derived.

    `bids_root` must be the dataset root (containing participants.tsv/sub-*/ dirs),
    not a single subject's directory -- mne_bids misparses a root whose own path
    component looks like a `sub-XXXX` entity, producing doubled/broken paths. To
    process one subject at a time (streaming/disk-bounded processing), pass the
    full dataset root and use `subject_filter` (matches `BIDSEEGRecord.subject_id`,
    e.g. "sub-001") instead of pointing bids_root at that subject's own directory.
    """
    records = discover_bids_eeg(bids_root)
    if subject_filter is not None:
        records = [r for r in records if r.subject_id == subject_filter]
    rows: list[LevelMWindowRow] = []
    for rec in records:
        if not rec.is_eeg_candidate:
            continue
        subject = rec.subject_id or "unknown_subject"
        task = rec.task_label
        state = _TASK_TO_STATE.get((task or "").lower())
        for idx in range(max_windows_per_file):
            w_start = idx * window_seconds
            w_end = (idx + 1) * window_seconds
            warns: list[str] = [
                "real-EEG-derived Level M features (provenance=real_bids); per-window z-normalized"
            ]
            try:
                signal = read_window_signal(
                    rec.path, w_start, w_end, pick="mean", max_channels=max_channels
                )
                raw_sig = np.asarray(signal, dtype=float)
                raw_power = float(np.mean(raw_sig ** 2))
                std = raw_sig.std()
                norm = (raw_sig - raw_sig.mean()) / std if std > 0 else raw_sig
                # cast to native Python float (see ds005620_windows_real.py for why:
                # list(ndarray) keeps np.float64 elements, silently tainting
                # artifact_dominance with a non-JSON-serializable numpy bool
                # whenever mean_artifact_score > 0.5)
                feats = extract_level_m_features([float(v) for v in norm])
                feats["spectral_power_proxy"] = raw_power
            except ValueError as exc:
                warns.append(f"window skipped: {exc}")
                feats = {
                    "spectral_power_proxy": None,
                    "entropy_proxy": None,
                    "lzc_proxy": None,
                    "artifact_score": None,
                }
            path_hash = hashlib.sha256(rec.relative_path.encode("utf-8")).hexdigest()[:8]
            row = LevelMWindowRow(
                row_id=(
                    f"{subject}_{rec.session_id or 'nosess'}_{rec.run_id or 'norun'}_"
                    f"{rec.acq_label or 'noacq'}_{task or 'unknown'}_win-{idx}_{path_hash}"
                ),
                subject_id=subject,
                session_id=rec.session_id,
                run_id=rec.run_id,
                window_id=f"win-{idx}",
                task_label=task,
                state_label=state,
                behavior_label=None,
                report_label=None,
                y=None,
                source_file=rec.path,
                window_start_s=w_start,
                window_end_s=w_end,
                warnings=warns,
                **feats,
            )
            rows.append(row)
    return rows
