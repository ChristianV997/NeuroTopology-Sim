#!/usr/bin/env python3
"""Stream-process ds005555 (BOAS full-night PSG sleep) one subject at a time.

Dedicated runner, not wired into `stream_process_openneuro_dataset.py`'s
generic `DATASET_PROCESSORS`: like ds001787 (and unlike ds005620/ds003969),
ds005555's state does not come from a BIDS task entity, so it can't use the
generic registry-driven `task_to_state` windower. Its state is a per-30s-epoch
AASM sleep-stage label in a companion events.tsv (`stage_hum`), windowed by
`sciencer_d/btc_icft/level_m/ds005555_windows_real.py`. This script wraps that
dedicated windower in the same download/process/delete/checkpoint discipline
as every other streaming tool (peak disk stays at ~1 subject's raw PSG EDF,
~150 MB, regardless of the dataset's full 74-subject size).

Cheap path only by default: per-epoch Level-M features + the dataset-agnostic
`compute_real_topology_for_window` (channel-mean topology). The expensive
connectivity/phase/spatial/surrogate-null battery
(`tools/run_capability_battery.py`) is intentionally NOT run per subject here
-- it stays a diagnostic spot-check on a handful of subjects, because the
subject-blocked permutation test that scaling exists to power only needs the
cheap per-window q_net/q_abs/f_dress/defect_density columns this produces.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.streaming import base_runner  # noqa: E402

_DATASET_ID = "ds005555"
_BUCKET = "openneuro.org"


def sync_dataset_metadata(dest_root: Path) -> None:
    base_runner.sync_s3_dataset_metadata(_BUCKET, _DATASET_ID, dest_root)


def sync_subject(subject: str, dest_root: Path) -> Path:
    return base_runner.sync_s3_subject(_BUCKET, _DATASET_ID, subject, dest_root)


def list_s3_subjects() -> list[str]:
    return base_runner.list_s3_subjects(_BUCKET, f"{_DATASET_ID}/")


def process_subject(
    subject_root: Path, subject: str, out_dir: Path,
    max_windows_per_file: int, max_channels: int,
) -> dict:
    from sciencer_d.btc_icft.level_m.ds005555_windows_real import build_and_extract_real_windows
    from sciencer_d.btc_icft.level_t.base_real_topology import compute_real_topology_for_window

    bids_root = str(subject_root.parent)
    m_rows = build_and_extract_real_windows(
        bids_root, max_windows_per_file=max_windows_per_file,
        max_channels=max_channels, subject_filter=subject,
    )
    m_dicts = [asdict(r) for r in m_rows]
    base_runner.write_rows_csv(out_dir / f"{subject}_features_m.csv", m_dicts, write_empty_marker=True)

    t_rows = [compute_real_topology_for_window(row, max_channels=max_channels) for row in m_dicts]
    base_runner.write_rows_csv(out_dir / f"{subject}_features_t.csv", [asdict(r) for r in t_rows], write_empty_marker=True)

    return {"n_m_rows": len(m_dicts), "n_t_rows": len(t_rows)}


def run(
    out_dir: str, work_root: str,
    max_windows_per_file: int = 40, max_channels: int = 6,
    limit: int | None = None, subjects: list[str] | None = None, keep_raw: bool = False,
) -> int:
    out_path = Path(out_dir)
    work_path = Path(work_root)
    work_path.mkdir(parents=True, exist_ok=True)

    if not (work_path / "participants.tsv").exists():
        print("Syncing dataset-level metadata...")
        sync_dataset_metadata(work_path)

    all_subjects = subjects if subjects is not None else list_s3_subjects()

    def _sync(subject: str, work_path: Path) -> Path:
        return sync_subject(subject, work_path)

    def _process(subject_root: Path, subject: str, out_path: Path) -> dict:
        return process_subject(subject_root, subject, out_path, max_windows_per_file, max_channels)

    base_runner.run_streaming_loop(all_subjects, out_path, work_path, _sync, _process, limit=limit, keep_raw=keep_raw)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="outputs/btc_icft/ds005555/stream")
    p.add_argument("--work-root", default="data/ds005555")
    p.add_argument("--max-windows-per-file", type=int, default=40)
    p.add_argument("--max-channels", type=int, default=6)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--subjects", nargs="*", default=None)
    p.add_argument("--keep-raw", action="store_true")
    a = p.parse_args()
    return run(
        a.out, a.work_root, a.max_windows_per_file, a.max_channels,
        a.limit, a.subjects, a.keep_raw,
    )


if __name__ == "__main__":
    raise SystemExit(main())
