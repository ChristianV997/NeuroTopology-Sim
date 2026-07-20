"""ds005620 (propofol sedation) real signal-derived Level T topology.

Thin shim over `base_real_topology.py`, which holds the actual logic (this
module, `ds003969_real_topology.py`, and `ds001787_real_topology.py` were
confirmed function-for-function identical before consolidation). Wrapper
functions here preserve this module's exact external call signatures
(`load_level_m_window_features(m_windows_dir)`, `build_level_t_omega_event(rows)`,
`write_level_t_topology_outputs(result, out_dir)` -- no `dataset_id` argument
at this layer) so `pipelines/run_ds005620_t_real.py` and
`tests/btc_icft/test_ds005620_t_real_topology.py` need no changes.
"""
from __future__ import annotations

from sciencer_d.btc_icft.level_t import base_real_topology as _base
from sciencer_d.btc_icft.level_t.base_real_topology import (
    REQUIRED_M_COLUMNS,
    LevelTRealTopologyResult,
    LevelTRealTopologyRow,
    build_artifact_alignment_report,
    build_connectivity_report,
    build_group_significance_report,
    build_level_t_rows_from_m_windows,
    build_ml_decoding_report,
    build_null_gate_report,
    build_null_placeholder_report,
    build_phase_based_topology_report,
    build_topology_quality_report,
    compute_connectivity_for_window,
    compute_fixture_topology_for_window,
    compute_phase_based_topology_for_window,
    compute_real_topology_for_window,
)
from sciencer_d.btc_icft.level_t.microstates import build_microstate_report
from sciencer_d.btc_icft.level_t.spatial_topology import build_spatial_topology_report
from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES

DATASET_ID = "ds005620"


def load_level_m_window_features(m_windows_dir: str) -> list[dict]:
    return _base.load_level_m_window_features(m_windows_dir, DATASET_ID)


def build_level_t_omega_event(rows: list[LevelTRealTopologyRow]) -> dict:
    return _base.build_level_t_omega_event(rows, DATASET_ID)


def write_level_t_topology_outputs(
    result: LevelTRealTopologyResult, out_dir: str,
    null_gate_report: dict | None = None, group_significance_report: dict | None = None,
    phase_based_topology_report: dict | None = None, connectivity_report: dict | None = None,
    spatial_topology_report: dict | None = None, microstate_report: dict | None = None,
    ml_decoding_report: dict | None = None,
) -> dict[str, str]:
    return _base.write_level_t_topology_outputs(
        result, out_dir, result_rows_cache, DATASET_ID,
        null_gate_report=null_gate_report, group_significance_report=group_significance_report,
        phase_based_topology_report=phase_based_topology_report, connectivity_report=connectivity_report,
        spatial_topology_report=spatial_topology_report, microstate_report=microstate_report,
        ml_decoding_report=ml_decoding_report,
    )


result_rows_cache: list[LevelTRealTopologyRow] = []
