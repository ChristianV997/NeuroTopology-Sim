"""ds003816 (loving-kindness meditation vs resting) real-signal Level M
window extraction.

Thin shim over `base_windows_real.py`, which holds the actual extraction
logic (see `base_windows_real.py`'s docstring for the shared function this
module and the other "one window per fixed interval" dataset ports build
on). `discover_bids_eeg`/`read_window_signal` are imported here (not only
in the shared module) so tests can monkeypatch them directly on this
module.

Task label mapping was CONFIRMED via direct S3 listing of ds003816
(sub-01lt/ses-01, ses-02 eeg/ dirs), not assumed: real BIDS task entities
are `LKMSelf`, `LKMOther` (loving-kindness meditation), `PreResting`,
`PostResting` (resting baselines), `VisualizeSelf`, `VisualizeOther` (a
visualization control condition, intentionally unmapped -- see
`ds003816_windows.py`'s module docstring). No `acq` BIDS entity exists in
this dataset, but subjects have multiple `ses-NN` sessions (the row_id
path-hash suffix from the shared function is the hard uniqueness guarantee
regardless).
"""
from __future__ import annotations

import sys
from pathlib import Path

from sciencer_d.btc_icft.level_m.base_windows_real import build_and_extract_real_windows_from_task_map
from sciencer_d.btc_icft.level_m.ds003816_windows import LevelMWindowRow

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.bids_ingest import discover_bids_eeg, read_window_signal  # noqa: E402
from sciencer_d.btc_icft.datasets.onboarding_registry import get_dataset_config  # noqa: E402

# Single source of truth: the onboarding registry (was a duplicated literal).
_TASK_TO_STATE = get_dataset_config("ds003816").task_to_state


def build_and_extract_real_windows(
    bids_root: str,
    window_seconds: float = 10.0,
    max_windows_per_file: int = 2,
    max_channels: int | None = 16,
    subject_filter: str | None = None,
) -> list[LevelMWindowRow]:
    """Discover -> window -> extract REAL features for ds003816. Every row is
    marked real-EEG-derived.

    `bids_root` must be the dataset root (containing participants.tsv/sub-*/ dirs),
    not a single subject's directory -- mne_bids misparses a root whose own path
    component looks like a `sub-XXXX` entity, producing doubled/broken paths. To
    process one subject at a time (streaming/disk-bounded processing), pass the
    full dataset root and use `subject_filter` (matches `BIDSEEGRecord.subject_id`,
    e.g. "sub-01lt") instead of pointing bids_root at that subject's own directory.
    """
    return build_and_extract_real_windows_from_task_map(
        bids_root, LevelMWindowRow, _TASK_TO_STATE, discover_bids_eeg, read_window_signal,
        window_seconds=window_seconds, max_windows_per_file=max_windows_per_file,
        max_channels=max_channels, subject_filter=subject_filter,
    )
