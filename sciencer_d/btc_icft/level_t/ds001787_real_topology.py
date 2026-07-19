"""ds001787 (expert vs novice meditation) real signal-derived Level T topology.

Thin shim over `base_real_topology.py`, which holds the actual logic (this
module, `ds005620_real_topology.py`, and `ds003969_real_topology.py` were
confirmed function-for-function identical before consolidation). Wrapper
functions here preserve this module's exact external call signatures so
`pipelines/run_ds001787_t_real.py` and
`tests/btc_icft/test_ds001787_t_real_topology.py` need no changes.

ds001787 windows have HIGHLY VARIABLE length (fixed 10s windows for Analysis A
vs. probe_locked windows spanning 1s-165s+ for Analysis B) --
`compute_topology_from_channels` (in the shared module) operates on whatever
sample count it's given, so no dataset-specific override was needed here;
window-length is reported as an explicit confound in the report layer, not
handled specially in this shim.
"""
from __future__ import annotations

from sciencer_d.btc_icft.level_t import base_real_topology as _base
from sciencer_d.btc_icft.level_t.base_real_topology import (
    REQUIRED_M_COLUMNS,
    LevelTRealTopologyResult,
    LevelTRealTopologyRow,
    build_artifact_alignment_report,
    build_group_significance_report,
    build_level_t_rows_from_m_windows,
    build_null_gate_report,
    build_null_placeholder_report,
    build_topology_quality_report,
    compute_fixture_topology_for_window,
    compute_real_topology_for_window,
)
from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES

DATASET_ID = "ds001787"


def load_level_m_window_features(m_windows_dir: str) -> list[dict]:
    return _base.load_level_m_window_features(m_windows_dir, DATASET_ID)


def build_level_t_omega_event(rows: list[LevelTRealTopologyRow]) -> dict:
    return _base.build_level_t_omega_event(rows, DATASET_ID)


def write_level_t_topology_outputs(
    result: LevelTRealTopologyResult, out_dir: str,
    null_gate_report: dict | None = None, group_significance_report: dict | None = None,
) -> dict[str, str]:
    return _base.write_level_t_topology_outputs(
        result, out_dir, result_rows_cache, DATASET_ID,
        null_gate_report=null_gate_report, group_significance_report=group_significance_report,
    )


result_rows_cache: list[LevelTRealTopologyRow] = []
