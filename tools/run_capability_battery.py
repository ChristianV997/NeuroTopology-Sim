"""Full real-signal capability battery driver for a single onboarded dataset.

Wires together the already-built, already-tested Level-M/Level-T instruments
(`sciencer_d/btc_icft/level_t/base_real_topology.py` and friends) into one
run: topology quality, connectivity (PLV/PLI/wPLI), band-specific Hilbert
phase topology, montage-aware spatial (winding-number) topology, a
phase-randomization surrogate null gate, and a permutation-based group
significance test against `state_label`. No new statistical logic here --
this only orchestrates existing report builders and writes their output to
one JSON file per dataset.

Not run by default: pycrostates microstates (needs >=4 real-montage
channels and is dataset-shape-specific enough to call separately; see
`sciencer_d/btc_icft/level_t/microstates.py`) and the ML-decoding
cross-check (`build_ml_decoding_report`) -- both are additive and can be
added to a specific dataset's own report script if useful, but are not part
of this generic battery's default scope.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sciencer_d.btc_icft.level_t.base_real_topology import (  # noqa: E402
    build_connectivity_report,
    build_group_significance_report,
    build_level_t_rows_from_m_windows,
    build_null_gate_report,
    build_phase_based_topology_report,
    build_topology_quality_report,
)
from sciencer_d.btc_icft.level_t.spatial_topology import build_spatial_topology_report  # noqa: E402


def run_battery(
    dataset_id: str,
    m_rows: list,
    max_channels: int | None = 16,
    band: str = "alpha",
    group_col: str = "state_label",
    seed: int = 0,
) -> dict:
    m_dicts = [asdict(r) for r in m_rows]
    t_rows = build_level_t_rows_from_m_windows(m_dicts, real=True)

    return {
        "dataset_id": dataset_id,
        "n_m_windows": len(m_dicts),
        "n_t_rows": len(t_rows),
        "topology_quality": build_topology_quality_report(t_rows),
        "connectivity": build_connectivity_report(t_rows, m_dicts, max_channels=max_channels, seed=seed),
        "phase_based_topology": build_phase_based_topology_report(t_rows, m_dicts, band=band, max_channels=max_channels, seed=seed),
        "spatial_topology": build_spatial_topology_report(t_rows, m_dicts, band=band, max_channels=max_channels, seed=seed),
        "surrogate_null_gate": build_null_gate_report(t_rows, m_dicts, max_channels=max_channels, seed=seed),
        "group_significance": build_group_significance_report(t_rows, m_dicts, group_col=group_col, seed=seed),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--bids-root", required=True)
    ap.add_argument("--subject-filter", default=None)
    ap.add_argument("--max-channels", type=int, default=16)
    ap.add_argument("--band", default="alpha")
    ap.add_argument("--group-col", default="state_label")
    ap.add_argument("--output", required=True)
    ap.add_argument("--windower", choices=["generic", "ds005555"], default="generic")
    args = ap.parse_args()

    if args.windower == "ds005555":
        from sciencer_d.btc_icft.level_m.ds005555_windows_real import build_and_extract_real_windows
        m_rows = build_and_extract_real_windows(
            args.bids_root, max_channels=args.max_channels, subject_filter=args.subject_filter,
        )
    else:
        from sciencer_d.btc_icft.level_m.generic_windows_real import build_and_extract_real_windows
        m_rows = build_and_extract_real_windows(
            args.dataset_id, args.bids_root, max_channels=args.max_channels, subject_filter=args.subject_filter,
        )

    report = run_battery(
        args.dataset_id, m_rows, max_channels=args.max_channels, band=args.band, group_col=args.group_col,
    )
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out_path} ({len(m_rows)} M windows, {report['n_t_rows']} T rows)")


if __name__ == "__main__":
    main()
