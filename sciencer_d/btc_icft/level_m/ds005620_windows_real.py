"""Real Level-M windows from actual EEG samples (replaces the filename-hash proxy path).

The legacy `extract_level_m_window_features` derived features from a hash of the file NAME
(`_signal_from_seed`), so its numbers were independent of the recording's contents. This module
reads the REAL samples for each window via `data.bids_ingest.read_window_signal` and feeds them
to the same `extract_level_m_features`, so features reflect signal, not filename.

Two real bugs, only visible under real-signal execution, are fixed here:
  * `entropy_proxy` / `lzc_proxy` were written for ~[0,1]-range synthetic values and collapse to
    zero on volt-scale EEG (~1e-5). Fixed with per-window z-normalization.
  * z-normalizing also flattens `spectral_power_proxy` to a near-constant, so that one is kept on
    the raw (unnormalized) scale.

Label mapping is deliberately conservative and reuses the dataset contract: task label
`awake`/`sedated` -> state label; behaviour/report left None unless present in sidecars.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from sciencer_d.btc_icft.level_m.features import extract_level_m_features
from sciencer_d.btc_icft.level_m.ds005620_windows import LevelMWindowRow

# reuse repo path so `from data...` resolves when run as a module
import sys
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.bids_ingest import discover_bids_eeg, read_window_signal  # noqa: E402

_TASK_TO_STATE = {"awake": "awake", "sedated": "sedated"}


def build_and_extract_real_windows(
    bids_root: str,
    window_seconds: float = 10.0,
    max_windows_per_file: int = 2,
    max_channels: int | None = 16,
) -> list[LevelMWindowRow]:
    """Discover -> window -> extract REAL features. Every row is marked real-EEG-derived."""
    records = discover_bids_eeg(bids_root)
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
                raw_power = float(np.mean(raw_sig ** 2))  # scale-sensitive band power proxy
                std = raw_sig.std()
                norm = (raw_sig - raw_sig.mean()) / std if std > 0 else raw_sig
                feats = extract_level_m_features(list(norm))
                feats["spectral_power_proxy"] = raw_power  # keep raw-scale power, not normalized
            except ValueError as exc:
                warns.append(f"window skipped: {exc}")
                feats = {
                    "spectral_power_proxy": None,
                    "entropy_proxy": None,
                    "lzc_proxy": None,
                    "artifact_score": None,
                }
            row = LevelMWindowRow(
                row_id=f"{subject}_{rec.run_id or 'norun'}_{task or 'unknown'}_win-{idx}",
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
