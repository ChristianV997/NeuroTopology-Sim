#!/usr/bin/env python3
"""Stream-process ds001787 (expert vs novice meditation) one subject at a time.

Dedicated runner, not wired into `stream_process_openneuro_dataset.py`'s generic
`DATASET_PROCESSORS`: unlike ds005620/ds003969, this dataset needs (a) a
dataset-level behavioral file (code/MW_Current_TextFileBIDS.zip) parsed ONCE and
shared across all subjects, not per-subject state, and (b) TWO window-building
modes per subject (fixed for the trait/group analysis, probe_locked for the
depth-correlation analysis) with different output shapes. Forcing that into the
generic per-subject-processor(subject_root, subject, out_dir, ...) signature would
either need a global or a signature change touching the ds005620/ds003969 path
for no benefit to them -- a dedicated script is more honest about the difference.

Same download/process/delete/checkpoint discipline as the generic tool: peak
disk stays at ~1 subject's raw files regardless of the dataset's 6.1 GB total.
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

_DATASET_ID = "ds001787"


def sync_dataset_metadata(dest_root: Path) -> None:
    cmd = [
        "aws", "s3", "sync", "--no-sign-request", "--only-show-errors",
        f"s3://openneuro.org/{_DATASET_ID}", str(dest_root),
        "--exclude", "*", "--include", "*.json", "--include", "*.tsv",
        "--include", "CHANGES", "--include", "README*",
        "--include", "code/MW_Current_TextFileBIDS.zip",
        "--exclude", "sub-*/*",
    ]
    subprocess.run(cmd, check=True)


def sync_subject(subject: str, dest_root: Path) -> Path:
    dest = dest_root / subject
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        "aws", "s3", "sync", "--no-sign-request", "--only-show-errors",
        f"s3://openneuro.org/{_DATASET_ID}/{subject}", str(dest),
    ]
    subprocess.run(cmd, check=True)
    return dest


def list_s3_subjects() -> list[str]:
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    paginator = s3.get_paginator("list_objects_v2")
    subjects: set[str] = set()
    for page in paginator.paginate(Bucket="openneuro.org", Prefix=f"{_DATASET_ID}/", Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            name = prefix["Prefix"].rstrip("/").split("/")[-1]
            if name.startswith("sub-"):
                subjects.add(name)
    return sorted(subjects)


def _write_rows_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")  # empty marker, not "file missing"
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


def process_subject(
    subject_root: Path, subject: str, out_dir: Path,
    behavioral_data: dict, n_fixed_windows: int, fixed_window_seconds: float, max_channels: int,
) -> dict:
    from sciencer_d.btc_icft.level_m.ds001787_windows_real import build_and_extract_real_windows
    from sciencer_d.btc_icft.level_t.ds001787_real_topology import compute_real_topology_for_window

    bids_root = str(subject_root.parent)

    fixed_m = build_and_extract_real_windows(
        bids_root, mode="fixed", n_fixed_windows=n_fixed_windows,
        window_seconds=fixed_window_seconds, max_channels=max_channels, subject_filter=subject,
    )
    fixed_m_dicts = [asdict(r) for r in fixed_m]
    _write_rows_csv(out_dir / f"{subject}_features_m_fixed.csv", fixed_m_dicts)
    fixed_t = [compute_real_topology_for_window(row, max_channels=max_channels) for row in fixed_m_dicts]
    _write_rows_csv(out_dir / f"{subject}_features_t_fixed.csv", [asdict(r) for r in fixed_t])

    probe_m = build_and_extract_real_windows(
        bids_root, mode="probe_locked", max_channels=max_channels,
        subject_filter=subject, behavioral_data=behavioral_data,
    )
    probe_m_dicts = [asdict(r) for r in probe_m]
    _write_rows_csv(out_dir / f"{subject}_features_m_probe.csv", probe_m_dicts)
    probe_t = [compute_real_topology_for_window(row, max_channels=max_channels) for row in probe_m_dicts]
    _write_rows_csv(out_dir / f"{subject}_features_t_probe.csv", [asdict(r) for r in probe_t])

    return {
        "n_fixed_m_rows": len(fixed_m_dicts), "n_fixed_t_rows": len(fixed_t),
        "n_probe_m_rows": len(probe_m_dicts), "n_probe_t_rows": len(probe_t),
    }


def load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"processed_subjects": {}, "failed_subjects": {}}


def save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def run(
    out_dir: str, work_root: str,
    n_fixed_windows: int = 6, fixed_window_seconds: float = 10.0, max_channels: int = 8,
    limit: int | None = None, subjects: list[str] | None = None, keep_raw: bool = False,
) -> int:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / "manifest.json"
    manifest = load_manifest(manifest_path)

    work_path = Path(work_root)
    work_path.mkdir(parents=True, exist_ok=True)

    if not (work_path / "participants.tsv").exists() or not (work_path / "code" / "MW_Current_TextFileBIDS.zip").exists():
        print("Syncing dataset-level metadata + behavioral file...")
        sync_dataset_metadata(work_path)

    from sciencer_d.btc_icft.level_m.ds001787_behavioral import parse_behavioral_zip
    zip_bytes = (work_path / "code" / "MW_Current_TextFileBIDS.zip").read_bytes()
    behavioral_data = parse_behavioral_zip(zip_bytes)
    print(f"Parsed behavioral data for {len(behavioral_data)} subjects from MW_Current_TextFileBIDS.zip")

    all_subjects = subjects if subjects is not None else list_s3_subjects()
    todo = [s for s in all_subjects if s not in manifest["processed_subjects"]]
    if limit:
        todo = todo[:limit]

    print(f"{len(all_subjects)} subjects total, {len(todo)} to process this run.")

    for subject in todo:
        print(f"--- {subject} ---")
        try:
            subject_root = sync_subject(subject, work_path)
            stats = process_subject(
                subject_root, subject, out_path, behavioral_data,
                n_fixed_windows, fixed_window_seconds, max_channels,
            )
            manifest["processed_subjects"][subject] = stats
            print(f"  done: {stats}")
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            manifest["failed_subjects"][subject] = str(e)
        finally:
            if not keep_raw:
                shutil.rmtree(work_path / subject, ignore_errors=True)
            save_manifest(manifest_path, manifest)

    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="outputs/btc_icft/ds001787/stream")
    p.add_argument("--work-root", default="data/ds001787")
    p.add_argument("--n-fixed-windows", type=int, default=6)
    p.add_argument("--fixed-window-seconds", type=float, default=10.0)
    p.add_argument("--max-channels", type=int, default=8)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--subjects", nargs="*", default=None)
    p.add_argument("--keep-raw", action="store_true")
    a = p.parse_args()
    return run(
        a.out, a.work_root, a.n_fixed_windows, a.fixed_window_seconds,
        a.max_channels, a.limit, a.subjects, a.keep_raw,
    )


if __name__ == "__main__":
    raise SystemExit(main())
