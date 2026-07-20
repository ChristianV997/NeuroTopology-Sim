"""Shared streaming skeleton for per-subject OpenNeuro dataset processing.

Used by both `tools/stream_process_openneuro_dataset.py` (ds005620/ds003969,
generic `DATASET_PROCESSORS` dispatch) and `tools/stream_process_ds001787.py`
(dedicated script -- different per-subject processor shape: a shared
dataset-level behavioral file parsed once, two window-building modes per
subject; see that module's own docstring for why it isn't folded into the
generic dispatch). Both scripts confirmed >80% identical download/checkpoint/
delete logic before this consolidation.

`run_streaming_loop` takes `sync_subject_fn`/`process_fn` as explicit
parameters rather than importing and calling its own copies -- this mirrors
the dependency-injection pattern in
`sciencer_d/btc_icft/level_m/base_windows_real.py` (Phase 2c): each caller
module keeps its own module-level `sync_subject`/`sync_dataset_metadata`
names (imported here only as the *default* implementation via
`sync_s3_subject`/`sync_s3_dataset_metadata`), so existing tests can keep
monkeypatching those names directly on the caller's own module
(`monkeypatch.setattr(mod, "sync_subject", ...)`) without this shared loop
silently bypassing the patch.
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable


def list_s3_subjects(bucket: str, prefix: str) -> list[str]:
    """List `sub-*` prefixes under `prefix` in `bucket` via unsigned S3 listing."""
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    paginator = s3.get_paginator("list_objects_v2")
    subjects: set[str] = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for p in page.get("CommonPrefixes", []):
            name = p["Prefix"].rstrip("/").split("/")[-1]
            if name.startswith("sub-"):
                subjects.add(name)
    return sorted(subjects)


def list_s3_task_labels(bucket: str, dataset_id: str, max_subjects: int = 3) -> list[str]:
    """Structurally discover the distinct BIDS `task-<label>` entities in a dataset
    by scanning object keys under its first few subjects, via unsigned S3 listing.

    This is STRUCTURAL discovery only (which task entities physically exist) --
    it never assigns semantic state labels. The task->state mapping for the
    onboarding registry must still be authored by a human (no_label_inference).
    Scanning a few subjects (default 3) is enough: BIDS task entities are shared
    across subjects, and this keeps discovery fast without listing the whole bucket.
    """
    import re

    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    subjects = list_s3_subjects(bucket, f"{dataset_id}/")[:max_subjects]
    task_re = re.compile(r"task-([A-Za-z0-9]+)")
    tasks: set[str] = set()
    paginator = s3.get_paginator("list_objects_v2")
    for subject in subjects:
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{dataset_id}/{subject}/"):
            for obj in page.get("Contents", []):
                m = task_re.search(obj["Key"])
                if m:
                    tasks.add(m.group(1))
    return sorted(tasks)


def sync_s3_subject(bucket: str, dataset_id: str, subject: str, dest_root: Path) -> Path:
    dest = dest_root / subject
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        "aws", "s3", "sync", "--no-sign-request", "--only-show-errors",
        f"s3://{bucket}/{dataset_id}/{subject}", str(dest),
    ]
    subprocess.run(cmd, check=True)
    return dest


def sync_s3_dataset_metadata(
    bucket: str, dataset_id: str, dest_root: Path, extra_includes: list[str] | None = None
) -> None:
    """Top-level BIDS files needed for inspection (participants.tsv etc), synced once.

    `extra_includes` lets a caller pull additional dataset-level files (e.g.
    ds001787's behavioral zip) into the same single sync call.
    """
    cmd = [
        "aws", "s3", "sync", "--no-sign-request", "--only-show-errors",
        f"s3://{bucket}/{dataset_id}", str(dest_root),
        "--exclude", "*", "--include", "*.json", "--include", "*.tsv",
        "--include", "CHANGES", "--include", "README*",
    ]
    for inc in extra_includes or []:
        cmd += ["--include", inc]
    cmd += ["--exclude", "sub-*/*"]
    subprocess.run(cmd, check=True)


def write_rows_csv(path: Path, rows: list[dict], write_empty_marker: bool = False) -> None:
    """Write `rows` to `path` as CSV, joining list-valued `warnings` into a string.

    `write_empty_marker`: ds001787's probe_locked mode can legitimately produce
    zero rows for a subject; writing an empty marker file (rather than nothing)
    distinguishes "ran, found nothing" from "never ran" when inspecting output.
    """
    if not rows:
        if write_empty_marker:
            path.write_text("", encoding="utf-8")
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


def load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"processed_subjects": {}, "failed_subjects": {}}


def save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def run_streaming_loop(
    all_subjects: list[str],
    out_path: Path,
    work_path: Path,
    sync_subject_fn: Callable[[str, Path], Path],
    process_fn: Callable[[Path, str, Path], dict],
    limit: int | None = None,
    keep_raw: bool = False,
) -> dict:
    """Sync -> process -> delete -> checkpoint one subject at a time, resumable
    via a `manifest.json` in `out_path`.

    `sync_subject_fn(subject, work_path) -> subject_root` and
    `process_fn(subject_root, subject, out_path) -> stats dict` are injected
    by the caller (already bound to that dataset's id/window params/behavioral
    data/etc via a closure) -- this function only owns the resume/checkpoint/
    delete discipline, not any dataset-specific logic. One subject failing
    (network error, corrupt file, ...) logs to `failed_subjects` and the loop
    continues rather than aborting the whole run.
    """
    out_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / "manifest.json"
    manifest = load_manifest(manifest_path)

    todo = [s for s in all_subjects if s not in manifest["processed_subjects"]]
    if limit:
        todo = todo[:limit]

    print(f"{len(all_subjects)} subjects total, {len(todo)} to process this run.")

    for subject in todo:
        print(f"--- {subject} ---")
        try:
            subject_root = sync_subject_fn(subject, work_path)
            stats = process_fn(subject_root, subject, out_path)
            manifest["processed_subjects"][subject] = stats
            print(f"  done: {stats}")
        except Exception as e:  # keep going: one bad subject shouldn't kill the run
            print(f"  FAILED: {e}", file=sys.stderr)
            manifest["failed_subjects"][subject] = str(e)
        finally:
            if not keep_raw:
                shutil.rmtree(work_path / subject, ignore_errors=True)
            save_manifest(manifest_path, manifest)  # checkpoint after every subject

    return manifest
