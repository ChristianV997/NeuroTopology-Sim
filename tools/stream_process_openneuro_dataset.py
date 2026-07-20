#!/usr/bin/env python3
"""Stream-process an OpenNeuro BIDS dataset one subject at a time.

For each subject: sync its raw files from the OpenNeuro S3 bucket, run the real
signal-derived Level M + Level T extraction against it, append the resulting
per-window feature rows to a persistent per-subject CSV feature store, then
delete the subject's raw files before moving to the next subject.

This keeps peak local disk usage to ~1 subject's raw files (a few GB) regardless
of total dataset size -- DS005620 alone is 83GB across 21 subjects, well beyond
what fits alongside everything else on a constrained disk budget. A
`manifest.json` in the output directory tracks which subjects are already
processed (and which failed, with the error), so an interrupted run resumes
without re-downloading or re-processing anything already done.

Dataset-agnostic and registry-driven: every dataset listed in
configs/btc_icft/dataset_onboarding_registry.json is streamable with ZERO
per-dataset Python code here. A single generic per-subject processor
(`process_subject_generic`) resolves the dataset's task-to-state map and window
params from the registry; the topology step is already dataset-agnostic. To
onboard a new OpenNeuro EEG dataset of the "simple task-to-state map" shape, add
a registry entry (discover its real task labels with
`tools/discover_openneuro_tasks.py`) -- no new module needed. An unregistered
dataset id exits with a clear error listing the registered ids rather than
silently doing nothing. (ds001787 is intentionally NOT registered here: its
dual-mode/behavioral-file processing has its own dedicated streaming tool,
tools/stream_process_ds001787.py -- see tools/streaming/base_runner.py.)

Usage:
    python tools/stream_process_openneuro_dataset.py --dataset-id ds005620 \\
        --out outputs/btc_icft/ds005620/stream --work-root data/ds005620

    # Bound how much a single invocation does (e.g. for an overnight run with a
    # hard stop time) -- resuming later just re-runs the same command:
    python tools/stream_process_openneuro_dataset.py --limit 5
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.streaming import base_runner

_BUCKET = "openneuro.org"


def list_s3_subjects(openneuro_id: str) -> list[str]:
    """List subject prefixes for a dataset via unsigned S3 listing."""
    return base_runner.list_s3_subjects(_BUCKET, f"{openneuro_id}/")


def sync_subject(openneuro_id: str, subject: str, dest_root: Path) -> Path:
    return base_runner.sync_s3_subject(_BUCKET, openneuro_id, subject, dest_root)


def sync_dataset_metadata(openneuro_id: str, dest_root: Path) -> None:
    """Top-level BIDS files needed for inspection (participants.tsv etc), synced once."""
    base_runner.sync_s3_dataset_metadata(_BUCKET, openneuro_id, dest_root)


def _write_rows_csv(path: Path, rows: list[dict]) -> None:
    base_runner.write_rows_csv(path, rows)


def process_subject_generic(
    dataset_id: str,
    subject_root: Path, subject: str, out_dir: Path,
    window_seconds: float, max_windows_per_file: int, max_channels: int,
) -> dict:
    """Run real Level M + Level T for one subject of ANY registered dataset;
    write per-subject CSVs.

    This single generic processor replaced three byte-identical
    `process_ds{05620,03969,03816}_subject` functions that differed only in which
    dataset's `_windows_real`/`_real_topology` module they imported -- that
    coupling is now expressed as a `dataset_id` string resolved through the
    onboarding registry (`generic_windows_real.build_and_extract_real_windows`),
    and the topology step (`compute_real_topology_for_window`) was already
    dataset-agnostic. A newly registered dataset is streamable immediately with
    no new Python code here.

    `subject_root` is `<dataset_root>/<subject>` (where sync_subject placed this
    subject's files); `build_and_extract_real_windows` needs the DATASET root
    (mne_bids misparses a root that looks like a subject directory itself), so we
    pass its parent and filter to this subject via `subject_filter`.
    """
    from sciencer_d.btc_icft.level_m.generic_windows_real import build_and_extract_real_windows
    from sciencer_d.btc_icft.level_t.base_real_topology import compute_real_topology_for_window

    m_rows = build_and_extract_real_windows(
        dataset_id, str(subject_root.parent), window_seconds=window_seconds,
        max_windows_per_file=max_windows_per_file, max_channels=max_channels,
        subject_filter=subject,
    )
    m_dicts = [asdict(r) for r in m_rows]
    _write_rows_csv(out_dir / f"{subject}_features_m.csv", m_dicts)

    t_rows = [compute_real_topology_for_window(row, max_channels=max_channels) for row in m_dicts]
    t_dicts = [asdict(r) for r in t_rows]
    _write_rows_csv(out_dir / f"{subject}_features_t.csv", t_dicts)

    return {"n_m_rows": len(m_dicts), "n_t_rows": len(t_dicts)}


def _make_dataset_processors() -> dict:
    """Build the {dataset_id: processor} map from the onboarding registry.

    Every registered dataset gets the same generic processor with its dataset_id
    pre-bound. Still a plain mutable dict, so tests can inject a fake processor
    via `monkeypatch.setitem(DATASET_PROCESSORS, "fake_ds", ...)`.
    """
    from functools import partial

    from sciencer_d.btc_icft.datasets.onboarding_registry import registered_dataset_ids

    return {
        ds_id: partial(process_subject_generic, ds_id)
        for ds_id in registered_dataset_ids()
    }


DATASET_PROCESSORS = _make_dataset_processors()


def load_manifest(path: Path) -> dict:
    return base_runner.load_manifest(path)


def save_manifest(path: Path, manifest: dict) -> None:
    base_runner.save_manifest(path, manifest)


def run(
    openneuro_id: str,
    out_dir: str,
    work_root: str,
    window_seconds: float = 4.0,
    max_windows_per_file: int = 5,
    max_channels: int = 8,
    limit: int | None = None,
    subjects: list[str] | None = None,
    keep_raw: bool = False,
) -> int:
    if openneuro_id not in DATASET_PROCESSORS:
        print(
            f"Dataset {openneuro_id!r} is not registered for streaming. "
            f"Registered: {sorted(DATASET_PROCESSORS)}. Add an entry to "
            f"configs/btc_icft/dataset_onboarding_registry.json to onboard it "
            f"(discover its real task labels with tools/discover_openneuro_tasks.py).",
            file=sys.stderr,
        )
        return 2

    out_path = Path(out_dir)
    work_path = Path(work_root)
    work_path.mkdir(parents=True, exist_ok=True)

    if not any(work_path.glob("*.tsv")):
        print("Syncing dataset-level metadata...")
        sync_dataset_metadata(openneuro_id, work_path)

    all_subjects = subjects if subjects is not None else list_s3_subjects(openneuro_id)
    processor = DATASET_PROCESSORS[openneuro_id]

    def _sync(subject: str, work_path: Path) -> Path:
        return sync_subject(openneuro_id, subject, work_path)

    def _process(subject_root: Path, subject: str, out_path: Path) -> dict:
        return processor(subject_root, subject, out_path, window_seconds, max_windows_per_file, max_channels)

    base_runner.run_streaming_loop(all_subjects, out_path, work_path, _sync, _process, limit=limit, keep_raw=keep_raw)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset-id", default="ds005620", help="OpenNeuro accession, e.g. ds005620")
    p.add_argument("--out", default="outputs/btc_icft/ds005620/stream")
    p.add_argument("--work-root", default="data/ds005620")
    p.add_argument("--window-seconds", type=float, default=4.0)
    p.add_argument("--max-windows-per-file", type=int, default=5)
    p.add_argument("--max-channels", type=int, default=8)
    p.add_argument("--limit", type=int, default=None, help="Max subjects to process this run")
    p.add_argument("--subjects", nargs="*", default=None, help="Explicit subject list (else discover via S3)")
    p.add_argument("--keep-raw", action="store_true", help="Do not delete raw files after processing (debug only)")
    a = p.parse_args()
    return run(
        a.dataset_id, a.out, a.work_root, a.window_seconds,
        a.max_windows_per_file, a.max_channels, a.limit, a.subjects, a.keep_raw,
    )


if __name__ == "__main__":
    raise SystemExit(main())
