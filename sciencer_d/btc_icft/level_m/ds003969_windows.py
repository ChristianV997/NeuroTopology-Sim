"""ds003969 (meditation vs thinking EEG) Level M window scaffold.

Thin, registry-backed delegation to `generic_windows` -- the Level-M row/result
dataclasses, metric helpers, contrast-evaluation, and output-writing that this
module used to duplicate now live in ONE place (see generic_windows.py) and are
driven by this dataset's registry config. Public names are preserved so existing
imports keep working; output is byte-identical (proven in
tests/btc_icft/test_onboarding_registry.py).
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

_CONFIG = get_dataset_config("ds003969")


def evaluate_level_m_windows(rows: list[LevelMWindowRow], task: str = "meditation_vs_thinking") -> LevelMRealWindowResult:
    return _G.evaluate_level_m_windows(rows, _CONFIG, task=task)


def write_level_m_window_outputs(result: LevelMRealWindowResult, out_dir: str) -> dict[str, str]:
    return _G.write_level_m_window_outputs(result, out_dir, _CONFIG)
