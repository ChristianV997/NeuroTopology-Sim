"""ds003816 (loving-kindness meditation vs resting) Level M window scaffold.

Thin, registry-backed delegation to `generic_windows` (see that module and
ds003969_windows.py for the consolidation rationale). Public names preserved;
output byte-identical (proven in tests/btc_icft/test_onboarding_registry.py).

Real BIDS task labels (confirmed via S3, not guessed) live in the registry:
LKMSelf/LKMOther -> meditation, PreResting/PostResting -> resting;
VisualizeSelf/VisualizeOther intentionally unmapped.
"""
from __future__ import annotations

from sciencer_d.btc_icft.datasets.onboarding_registry import get_dataset_config
from sciencer_d.btc_icft.level_m.generic_windows import (  # noqa: F401  (re-exported public API)
    LevelMRealWindowResult,
    LevelMWindowRow,
    build_window_artifact_report,
    build_window_leakage_report,
)
from sciencer_d.btc_icft.level_m import generic_windows as _G

_CONFIG = get_dataset_config("ds003816")


def evaluate_level_m_windows(rows: list[LevelMWindowRow], task: str = "lkm_vs_resting") -> LevelMRealWindowResult:
    return _G.evaluate_level_m_windows(rows, _CONFIG, task=task)


def write_level_m_window_outputs(result: LevelMRealWindowResult, out_dir: str) -> dict[str, str]:
    return _G.write_level_m_window_outputs(result, out_dir, _CONFIG)
