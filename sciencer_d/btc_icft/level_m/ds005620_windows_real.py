"""ds005620 (propofol sedation) real-signal Level M window extraction.

Thin shim over `base_windows_real.py`, which holds the actual extraction
logic (this module and `ds003969_windows_real.py` were confirmed near-identical
before consolidation -- same extraction logic and bug fixes, differing only in
`_TASK_TO_STATE` and which dataset's `LevelMWindowRow` class to construct).
`ds001787_windows_real.py` is NOT built on this shared function -- it has two
genuinely different window-building modes and a dataset-level behavioral file
to parse (see base_windows_real.py's docstring for that boundary decision).

`discover_bids_eeg`/`read_window_signal` are imported here (not only in the
shared module) so existing tests can keep monkeypatching them directly on
this module (`monkeypatch.setattr(mod, "discover_bids_eeg", ...)`) -- see
base_windows_real.py's docstring for why.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sciencer_d.btc_icft.level_m.base_windows_real import build_and_extract_real_windows_from_task_map
from sciencer_d.btc_icft.level_m.ds005620_windows import LevelMWindowRow

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.bids_ingest import discover_bids_eeg, read_window_signal  # noqa: E402
from sciencer_d.btc_icft.datasets.onboarding_registry import get_dataset_config  # noqa: E402

# Single source of truth: the onboarding registry (was a duplicated literal).
_TASK_TO_STATE = get_dataset_config("ds005620").task_to_state


def build_and_extract_real_windows(
    bids_root: str,
    window_seconds: float = 10.0,
    max_windows_per_file: int = 2,
    max_channels: int | None = 16,
    subject_filter: str | None = None,
) -> list[LevelMWindowRow]:
    """Discover -> window -> extract REAL features. Every row is marked real-EEG-derived.

    `bids_root` must be the dataset root (containing participants.tsv/sub-*/ dirs), not
    a single subject's directory -- mne_bids misparses a root whose own path component
    looks like a `sub-XXXX` entity, producing doubled/broken paths. To process one
    subject at a time (e.g. for streaming/disk-bounded processing), pass the full
    dataset root and use `subject_filter` (matches `BIDSEEGRecord.subject_id`, e.g.
    "sub-1010") instead of pointing bids_root at that subject's own directory.
    """
    return build_and_extract_real_windows_from_task_map(
        bids_root, LevelMWindowRow, _TASK_TO_STATE, discover_bids_eeg, read_window_signal,
        window_seconds=window_seconds, max_windows_per_file=max_windows_per_file,
        max_channels=max_channels, subject_filter=subject_filter,
    )
