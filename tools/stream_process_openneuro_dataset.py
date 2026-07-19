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

Currently wired for DS005620 only -- the sole dataset in this repo with a
working real-signal Level M + Level T extraction path as of this commit (see
docs/overnight_run_status.md for the bug history). The download/process/delete
loop itself is dataset-agnostic; DATASET_PROCESSORS is where a real per-subject
processor for another registered dataset (DS002094, ds001787, ...) gets plugged
in once one exists -- until then this exits with a clear "not wired yet" error
rather than silently doing nothing useful for other dataset ids.

Usage:
    python tools/stream_process_openneuro_dataset.py --dataset-id ds005620 \\
        --out outputs/btc_icft/ds005620/stream --work-root data/ds005620

    # Bound how much a single invocation does (e.g. for an overnight run with a
    # hard stop time) -- resuming later just re-runs the same command:
    python tools/stream_process_openneuro_dataset.py --limit 5
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def list_s3_subjects(openneuro_id: str) -> list[str]:
    """List subject prefixes for a dataset via unsigned S3 listing."""
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    paginator = s3.get_paginator("list_objects_v2")
    subjects: set[str] = set()
    for page in paginator.paginate(Bucket="openneuro.org", Prefix=f"{openneuro_id}/", Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            name = prefix["Prefix"].rstrip("/").split("/")[-1]
            if name.startswith("sub-"):
                subjects.add(name)
    return sorted(subjects)


def sync_subject(openneuro_id: str, subject: str, dest_root: Path) -> Path:
    dest = dest_root / subject
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        "aws", "s3", "sync", "--no-sign-request", "--only-show-errors",
        f"s3://openneuro.org/{openneuro_id}/{subject}", str(dest),
    ]
    subprocess.run(cmd, check=True)
    return dest


def sync_dataset_metadata(openneuro_id: str, dest_root: Path) -> None:
    """Top-level BIDS files needed for inspection (participants.tsv etc), synced once."""
    cmd = [
        "aws", "s3", "sync", "--no-sign-request", "--only-show-errors",
        f"s3://openneuro.org/{openneuro_id}", str(dest_root),
        "--exclude", "*", "--include", "*.json", "--include", "*.tsv",
        "--include", "CHANGES", "--include", "README*", "--exclude", "sub-*/*",
    ]
    subprocess.run(cmd, check=True)


def _write_rows_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            row = dict(row)
            if isinstance(row.get("warnings"), list):
                row["warnings"] = "; ".join(row["warnings"])
            w.writerow(row)


def process_ds005620_subject(
    subject_root: Path, subject: str, out_dir: Path,
    window_seconds: float, max_windows_per_file: int, max_channels: int,
) -> dict:
    """Run real Level M + Level T for one subject's files; write per-subject CSVs.

    `subject_root` is `<dataset_root>/<subject>` (where sync_subject placed this
    subject's files); `build_and_extract_real_windows` needs the DATASET root
    (mne_bids misparses a root that looks like a subject directory itself), so we
    pass its parent and filter to this subject via `subject_filter`.
    """
    from sciencer_d.btc_icft.level_m.ds005620_windows_real import build_and_extract_real_windows
    from sciencer_d.btc_icft.level_t.ds005620_real_topology import compute_real_topology_for_window

    m_rows = build_and_extract_real_windows(
        str(subject_root.parent), window_seconds=window_seconds,
        max_windows_per_file=max_windows_per_file, max_channels=max_channels,
        subject_filter=subject,
    )
    m_dicts = [asdict(r) for r in m_rows]
    _write_rows_csv(out_dir / f"{subject}_features_m.csv", m_dicts)

    t_rows = [compute_real_topology_for_window(row, max_channels=max_channels) for row in m_dicts]
    t_dicts = [asdict(r) for r in t_rows]
    _write_rows_csv(out_dir / f"{subject}_features_t.csv", t_dicts)

    return {"n_m_rows": len(m_dicts), "n_t_rows": len(t_dicts)}


def process_ds003969_subject(
    subject_root: Path, subject: str, out_dir: Path,
    window_seconds: float, max_windows_per_file: int, max_channels: int,
) -> dict:
    """Run real Level M + Level T for one ds003969 subject; write per-subject CSVs.

    Same subject_root.parent + subject_filter pattern as `process_ds005620_subject`
    (mne_bids misparses a root that looks like a subject directory itself).
    """
    from sciencer_d.btc_icft.level_m.ds003969_windows_real import build_and_extract_real_windows
    from sciencer_d.btc_icft.level_t.ds003969_real_topology import compute_real_topology_for_window

    m_rows = build_and_extract_real_windows(
        str(subject_root.parent), window_seconds=window_seconds,
        max_windows_per_file=max_windows_per_file, max_channels=max_channels,
        subject_filter=subject,
    )
    m_dicts = [asdict(r) for r in m_rows]
    _write_rows_csv(out_dir / f"{subject}_features_m.csv", m_dicts)

    t_rows = [compute_real_topology_for_window(row, max_channels=max_channels) for row in m_dicts]
    t_dicts = [asdict(r) for r in t_rows]
    _write_rows_csv(out_dir / f"{subject}_features_t.csv", t_dicts)

    return {"n_m_rows": len(m_dicts), "n_t_rows": len(t_dicts)}


DATASET_PROCESSORS = {
    "ds005620": process_ds005620_subject,
    "ds003969": process_ds003969_subject,
}


def load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"processed_subjects": {}, "failed_subjects": {}}


def save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


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
            f"No real-signal processor wired for {openneuro_id!r} yet. "
            f"Available: {sorted(DATASET_PROCESSORS)}",
            file=sys.stderr,
        )
        return 2

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / "manifest.json"
    manifest = load_manifest(manifest_path)

    work_path = Path(work_root)
    work_path.mkdir(parents=True, exist_ok=True)

    if not any(work_path.glob("*.tsv")):
        print("Syncing dataset-level metadata...")
        sync_dataset_metadata(openneuro_id, work_path)

    all_subjects = subjects if subjects is not None else list_s3_subjects(openneuro_id)
    todo = [s for s in all_subjects if s not in manifest["processed_subjects"]]
    if limit:
        todo = todo[:limit]

    print(f"{len(all_subjects)} subjects total, {len(todo)} to process this run.")

    processor = DATASET_PROCESSORS[openneuro_id]
    for subject in todo:
        print(f"--- {subject} ---")
        try:
            subject_root = sync_subject(openneuro_id, subject, work_path)
            stats = processor(
                subject_root, subject, out_path, window_seconds, max_windows_per_file, max_channels
            )
            manifest["processed_subjects"][subject] = stats
            print(f"  done: {stats}")
        except Exception as e:  # keep going: one bad subject shouldn't kill the run
            print(f"  FAILED: {e}", file=sys.stderr)
            manifest["failed_subjects"][subject] = str(e)
        finally:
            if not keep_raw:
                shutil.rmtree(work_path / subject, ignore_errors=True)
            save_manifest(manifest_path, manifest)  # checkpoint after every subject

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
