"""Generic, registry-driven real-signal Level-M window extraction.

Collapses the per-dataset `{ds}_windows_real.py` shims (which differed only in
`_TASK_TO_STATE` and which dataset's `LevelMWindowRow` they constructed) into ONE
config-driven entry point. A new dataset needs no `{ds}_windows_real.py` module --
`build_and_extract_real_windows(dataset_id, bids_root, ...)` resolves everything from
the onboarding registry.

Output is byte-identical to the old per-dataset shims: `LevelMWindowRow` here is
field-identical to each dataset's own row class, and `task_to_state` comes from the
registry (verified equal to each shim's `_TASK_TO_STATE`), so `asdict()` produces the
same dicts and therefore the same CSVs.

ds001787 is deliberately not served here (dual-mode/behavioral-file shape).
"""
from __future__ import annotations

import sys
from pathlib import Path

from sciencer_d.btc_icft.datasets.onboarding_registry import get_dataset_config
from sciencer_d.btc_icft.level_m.base_windows_real import build_and_extract_real_windows_from_task_map
from sciencer_d.btc_icft.level_m.generic_windows import LevelMWindowRow

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.bids_ingest import discover_bids_eeg, read_window_signal  # noqa: E402


def build_and_extract_real_windows(
    dataset_id: str,
    bids_root: str,
    window_seconds: float | None = None,
    max_windows_per_file: int | None = None,
    max_channels: int | None = None,
    subject_filter: str | None = None,
) -> list[LevelMWindowRow]:
    """Discover -> window -> extract REAL features for any registered dataset.

    `bids_root` must be the dataset root (not a single subject's directory) --
    mne_bids misparses a root that looks like a `sub-XXXX` entity. To process one
    subject at a time (streaming), pass the dataset root and use `subject_filter`.

    Window params default to the dataset's registry values when not overridden.
    """
    cfg = get_dataset_config(dataset_id)
    return build_and_extract_real_windows_from_task_map(
        bids_root,
        LevelMWindowRow,
        cfg.task_to_state,
        discover_bids_eeg,
        read_window_signal,
        window_seconds=cfg.window_seconds if window_seconds is None else window_seconds,
        max_windows_per_file=cfg.max_windows_per_file if max_windows_per_file is None else max_windows_per_file,
        max_channels=cfg.max_channels if max_channels is None else max_channels,
        subject_filter=subject_filter,
    )
