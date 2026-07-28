#!/usr/bin/env python3
"""Stream-process ds004541 (EEG-fNIRS general anesthesia) one subject at a time.

Dedicated runner (like ds005555/ds001787): ds004541's state comes from the
real loss/recovery-of-consciousness (loc/roc) event markers in each
recording's events.tsv, windowed by
`sciencer_d/btc_icft/level_m/ds004541_windows_real.py` -- not from a BIDS task
entity, so it can't use the generic registry-driven windower. EEG modality
only (the fNIRS .snirf is ignored -- this repo's real-signal path is EEG).

Subject IDs are non-contiguous (sub-02,03,04,07,08,09,10,11 -- no 01/05/06);
`list_s3_subjects` discovers whatever actually exists, so no assumption of
sequential numbering is baked in. Subjects with no `loc` marker (e.g. sub-11)
process cleanly to zero windows rather than failing.
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

_DATASET_ID = "ds004541"
_BUCKET = "openneuro.org"


def sync_dataset_metadata(dest_root: Path) -> None:
    base_runner.sync_s3_dataset_metadata(_BUCKET, _DATASET_ID, dest_root)


def sync_subject(subject: str, dest_root: Path) -> Path:
    return base_runner.sync_s3_subject(_BUCKET, _DATASET_ID, subject, dest_root)


def list_s3_subjects() -> list[str]:
    return base_runner.list_s3_subjects(_BUCKET, f"{_DATASET_ID}/")


def process_subject(
    subject_root: Path, subject: str, out_dir: Path,
    window_seconds: float, max_windows_per_state: int, max_channels: int,
) -> dict:
    from sciencer_d.btc_icft.level_m.ds004541_windows_real import build_and_extract_real_windows
    from sciencer_d.btc_icft.level_t.base_real_topology import compute_real_topology_for_window

    bids_root = str(subject_root.parent)
    m_rows = build_and_extract_real_windows(
        bids_root, window_seconds=window_seconds, max_windows_per_state=max_windows_per_state,
        max_channels=max_channels, subject_filter=subject,
    )
    m_dicts = [asdict(r) for r in m_rows]
    base_runner.write_rows_csv(out_dir / f"{subject}_features_m.csv", m_dicts, write_empty_marker=True)

    t_rows = [compute_real_topology_for_window(row, max_channels=max_channels) for row in m_dicts]
    base_runner.write_rows_csv(out_dir / f"{subject}_features_t.csv", [asdict(r) for r in t_rows], write_empty_marker=True)

    return {"n_m_rows": len(m_dicts), "n_t_rows": len(t_rows)}


def run(
    out_dir: str, work_root: str,
    window_seconds: float = 10.0, max_windows_per_state: int = 10, max_channels: int = 16,
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
        return process_subject(subject_root, subject, out_path, window_seconds, max_windows_per_state, max_channels)

    base_runner.run_streaming_loop(all_subjects, out_path, work_path, _sync, _process, limit=limit, keep_raw=keep_raw)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="outputs/btc_icft/ds004541/stream")
    p.add_argument("--work-root", default="data/ds004541")
    p.add_argument("--window-seconds", type=float, default=10.0)
    p.add_argument("--max-windows-per-state", type=int, default=10)
    p.add_argument("--max-channels", type=int, default=16)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--subjects", nargs="*", default=None)
    p.add_argument("--keep-raw", action="store_true")
    a = p.parse_args()
    return run(
        a.out, a.work_root, a.window_seconds, a.max_windows_per_state,
        a.max_channels, a.limit, a.subjects, a.keep_raw,
    )


if __name__ == "__main__":
    raise SystemExit(main())
