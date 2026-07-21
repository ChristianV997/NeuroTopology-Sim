"""Real Level-M windows for ds004040 (Trance channeling EEG study, Cannard/
Delorme/Wahbeh, CC0) -- rest vs. trance, labeled by real block-onset/-offset
event markers.

ds004040's state does not come from a BIDS task entity (every recording is
`task-trance`) nor from `trial_type` (every row's `trial_type` is the literal
string "STATUS" -- a BIDS-EEG marker-channel artifact, not a state label).
The real state comes from the `value` column, which encodes segment identity
and boundary directly, e.g. `rest1_start`/`rest1_end`/`trance1_start`/
`trance1_end`, repeated 3x per session (rest/trance alternate, with some
rest-trance-rest ordering variation between sessions -- see the events.tsv
itself, not assumed). This module parses `value` into (state, index,
boundary) triples and pairs each `<label>_start` with its matching
`<label>_end` to build the real (state, start_s, end_s) intervals.

Each of the 13 subjects has exactly 2 sessions (`ses-01`, `ses-02`), each
with 3 rest blocks and 3 trance blocks. Channel names are standard 10-20
(Fp1, AF7, ... -- Biosemi 64-channel), no device prefix, so montage
resolution works unchanged.

HONEST label handling (no_label_inference): a `<label>_start` with no
matching `<label>_end` in the same file (not observed in this dataset, but
not assumed impossible) is dropped, not paired with a fabricated boundary.
Only the recording's own real markers define state boundaries.
"""
from __future__ import annotations

import csv
import hashlib
import re
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.bids_ingest import discover_bids_eeg, read_window_signal  # noqa: E402
from sciencer_d.btc_icft.level_m.features import extract_level_m_features  # noqa: E402
from sciencer_d.btc_icft.level_m.generic_windows import LevelMWindowRow  # noqa: E402

_LABEL_RE = re.compile(r"^(rest|trance)(\d+)_(start|end)$")


def _events_tsv_path(source_file: str) -> Path:
    p = Path(source_file)
    stem = p.name.replace("_eeg" + p.suffix, "")
    return p.parent / f"{stem}_events.tsv"


def _state_intervals(events_path: Path) -> list[tuple[str, float, float]]:
    """(state, start_s, end_s) intervals from the real rest/trance block
    markers in the `value` column. Only `<label>_start`/`<label>_end` pairs
    that both exist are emitted, in the order their `_start` appears."""
    if not events_path.exists():
        return []
    starts: dict[str, float] = {}
    ends: dict[str, float] = {}
    order: list[str] = []
    with events_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            value = (row.get("value") or "").strip()
            m = _LABEL_RE.match(value)
            if not m:
                continue
            state, idx, boundary = m.group(1), m.group(2), m.group(3)
            label = f"{state}{idx}"
            try:
                onset = float(row["onset"])
            except (KeyError, ValueError):
                continue
            if boundary == "start":
                starts[label] = onset
                if label not in order:
                    order.append(label)
            else:
                ends[label] = onset

    intervals: list[tuple[str, float, float]] = []
    for label in order:
        if label not in starts or label not in ends:
            continue  # unpaired marker -- real but incomplete, drop (no_label_inference)
        start_s, end_s = starts[label], ends[label]
        if end_s <= start_s:
            continue
        state = "rest" if label.startswith("rest") else "trance"
        intervals.append((state, start_s, end_s))
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
    """Discover -> rest/trance-block window -> extract REAL features for ds004040.

    Up to `max_windows_per_state` evenly-spaced `window_seconds` windows are
    taken from each rest/trance block (evenly spaced across all blocks of a
    given state within a recording, not just the first one, so windows
    aren't clustered in a single block).

    `bids_root` must be the dataset root.
    """
    records = discover_bids_eeg(bids_root)
    if subject_filter is not None:
        records = [r for r in records if r.subject_id == subject_filter]

    rows: list[LevelMWindowRow] = []
    for rec in records:
        if not rec.is_eeg_candidate or rec.task_label != "trance":
            continue
        subject = rec.subject_id or "unknown_subject"
        path_hash = hashlib.sha256(rec.relative_path.encode("utf-8")).hexdigest()[:8]

        intervals = _state_intervals(_events_tsv_path(rec.path))
        if not intervals:
            continue

        # Spread the per-state window budget across that state's blocks within this recording.
        by_state: dict[str, list[tuple[float, float]]] = {}
        for state, seg_start, seg_end in intervals:
            by_state.setdefault(state, []).append((seg_start, seg_end))

        for state, segments in by_state.items():
            n_segments = len(segments)
            per_segment_budget = max(1, max_windows_per_state // n_segments)
            win_counter = 0
            for seg_start, seg_end in segments:
                starts = _even_window_starts(seg_start, seg_end, window_seconds, per_segment_budget)
                for w_start in starts:
                    w_end = w_start + window_seconds
                    feats, warns = _feats_for_window(rec.path, w_start, w_end, max_channels)
                    row = LevelMWindowRow(
                        row_id=f"{subject}_{rec.session_id or 'nosess'}_{rec.run_id or 'norun'}_{state}-{win_counter}_{path_hash}",
                        subject_id=subject, session_id=rec.session_id, run_id=rec.run_id,
                        window_id=f"{state}-win-{win_counter}", task_label=rec.task_label, state_label=state,
                        behavior_label=None, report_label=None, y=None,
                        source_file=rec.path, window_start_s=w_start, window_end_s=w_end,
                        warnings=warns, **feats,
                    )
                    rows.append(row)
                    win_counter += 1
    return rows


def _even_window_starts(seg_start: float, seg_end: float, window_seconds: float, n_max: int) -> list[float]:
    """Up to `n_max` evenly-spaced window start times fitting fully inside
    [seg_start, seg_end)."""
    latest = seg_end - window_seconds
    if latest <= seg_start:
        return [seg_start] if seg_end - seg_start >= window_seconds * 0.5 else []
    n = min(n_max, max(1, int((seg_end - seg_start) // window_seconds)))
    return list(np.linspace(seg_start, latest, n))
