"""Shared real-signal Level M window extraction, for datasets whose real path
is a simple "one window per fixed interval, task label maps directly to a
2-value state" scheme.

Extracted from `ds005620_windows_real.py` and `ds003969_windows_real.py`,
which were confirmed near-identical (same extraction logic, same two bug
fixes -- per-window z-normalization for entropy_proxy/lzc_proxy, raw-scale
spectral_power_proxy, and the native-float JSON-serializability cast --
differing only in their `_TASK_TO_STATE` mapping and which dataset-specific
`LevelMWindowRow` class they construct).

`ds001787_windows_real.py` is deliberately NOT built on this shared function:
it has two genuinely different window-building modes (fixed-interval AND
probe-locked-to-behavioral-rating) and a dataset-level behavioral file to
parse, none of which fit this "one window per fixed interval" shape -- forcing
it in would distort the abstraction for no benefit to the one dataset that
doesn't need it, per this project's own established consolidation boundary
(see level_t/base_real_topology.py's docstring for the analogous decision
made there).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Callable

import numpy as np

from sciencer_d.btc_icft.level_m.features import extract_level_m_features

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def build_and_extract_real_windows_from_task_map(
    bids_root: str,
    row_cls: Callable,
    task_to_state: dict[str, str],
    discover_fn: Callable,
    read_fn: Callable,
    window_seconds: float = 10.0,
    max_windows_per_file: int = 2,
    max_channels: int | None = 16,
    subject_filter: str | None = None,
) -> list:
    """Discover -> window -> extract REAL features. Every row is marked
    real-EEG-derived.

    `bids_root` must be the dataset root (containing participants.tsv/sub-*/
    dirs), not a single subject's directory -- mne_bids misparses a root whose
    own path component looks like a `sub-XXXX` entity, producing
    doubled/broken paths. To process one subject at a time (e.g. for
    streaming/disk-bounded processing), pass the full dataset root and use
    `subject_filter` (matches `BIDSEEGRecord.subject_id`) instead of pointing
    bids_root at that subject's own directory.

    `row_cls` is the dataset-specific `LevelMWindowRow` dataclass to
    construct (each dataset owns its own copy, even though the field set is
    currently identical, so callers aren't forced to share a type across
    dataset module boundaries). `task_to_state` maps the dataset's real BIDS
    task label (lowercased) to a 2-value state label. `discover_fn`/`read_fn`
    are passed in (rather than imported directly here) specifically so each
    per-dataset shim module keeps its own module-level `discover_bids_eeg`/
    `read_window_signal` names -- existing tests monkeypatch those names
    directly on the shim module (`monkeypatch.setattr(mod, "discover_bids_eeg", ...)`),
    which would silently have no effect if this shared function imported and
    called its own separate copy instead of the one the caller passes in.
    """
    records = discover_fn(bids_root)
    if subject_filter is not None:
        records = [r for r in records if r.subject_id == subject_filter]
    rows = []
    for rec in records:
        if not rec.is_eeg_candidate:
            continue
        subject = rec.subject_id or "unknown_subject"
        task = rec.task_label
        state = task_to_state.get((task or "").lower())
        for idx in range(max_windows_per_file):
            w_start = idx * window_seconds
            w_end = (idx + 1) * window_seconds
            warns: list[str] = [
                "real-EEG-derived Level M features (provenance=real_bids); per-window z-normalized"
            ]
            try:
                signal = read_fn(
                    rec.path, w_start, w_end, pick="mean", max_channels=max_channels
                )
                raw_sig = np.asarray(signal, dtype=float)
                raw_power = float(np.mean(raw_sig ** 2))  # scale-sensitive band power proxy
                std = raw_sig.std()
                norm = (raw_sig - raw_sig.mean()) / std if std > 0 else raw_sig
                # cast each sample to a native Python float: list(ndarray) keeps
                # np.float64 elements, which silently taints every downstream
                # feature (and, worse, artifact_dominance's bool) with numpy
                # scalar types -- non-JSON-serializable regardless of value,
                # and only invisible when mean_artifact_score stays under the
                # 0.5 dominance threshold.
                feats = extract_level_m_features([float(v) for v in norm])
                feats["spectral_power_proxy"] = raw_power  # keep raw-scale power, not normalized
            except (ValueError, OSError) as exc:
                # ValueError: window out of range for this recording's duration
                # (data.bids_ingest.read_window_signal's own bounds check).
                # OSError (e.g. FileNotFoundError): a real, messy-real-data
                # failure mode found while porting ds003816 -- a BrainVision
                # .vhdr's companion .eeg/.vmrk file was genuinely absent from
                # the dataset's own S3 bucket for one task/session (confirmed
                # via direct listing, not a sync bug), and mne's lazy raw
                # reader raises FileNotFoundError while parsing the header.
                # One incomplete recording among many must not crash the
                # entire per-subject extraction and discard every other
                # window that WAS readable -- skip-and-report, matching this
                # function's existing out-of-range handling exactly.
                warns.append(f"window skipped: {exc}")
                feats = {
                    "spectral_power_proxy": None,
                    "entropy_proxy": None,
                    "lzc_proxy": None,
                    "artifact_score": None,
                }
            # Include every distinguishing BIDS entity (acq was previously dropped, which
            # collided distinct recordings such as acq-EC/acq-EO for the same
            # subject+task+run into one row_id and tripped the leakage-detection check
            # on real DS005620 data). A short hash of the source file's relative path is
            # appended as a hard uniqueness guarantee against any entity we don't know
            # to look for yet.
            path_hash = hashlib.sha256(rec.relative_path.encode("utf-8")).hexdigest()[:8]
            row = row_cls(
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
