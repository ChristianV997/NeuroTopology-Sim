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
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable


def _aws_command() -> list[str]:
    """Resolve AWS CLI across POSIX shells and Windows subprocesses.

    Prefer the installed Python module: Windows/WSL interop can resolve a
    `.cmd` console launcher to a path that subprocess cannot reliably wait on
    with `shell=False`, especially for long S3 transfers. The executable path
    remains a fallback for environments that only install the standalone CLI.
    """
    if importlib.util.find_spec("awscli") is not None:
        return [sys.executable, "-m", "awscli"]
    for name in ("aws", "aws.cmd"):
        executable = shutil.which(name)
        if executable:
            return [executable]
    return ["aws"]


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


def sync_s3_subject(
    bucket: str,
    dataset_id: str,
    subject: str,
    dest_root: Path,
    required_duration_seconds: float | None = None,
) -> Path:
    """Download one subject with bounded concurrent, atomic object transfers.

    Using boto3 here avoids Windows/WSL console-launcher behavior from the AWS
    CLI and lets independent EEG objects transfer concurrently. Each object is
    written to a temporary sibling and atomically renamed only after the full
    object is present, so a resumed run never mistakes a partial file for raw
    data. Existing files with the expected size are reused.
    """
    dest = dest_root / subject
    dest.mkdir(parents=True, exist_ok=True)
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    from boto3.s3.transfer import TransferConfig

    client = boto3.client(
        "s3",
        config=Config(
            signature_version=UNSIGNED,
            max_pool_connections=32,
            connect_timeout=20,
            read_timeout=60,
            retries={"max_attempts": 5, "mode": "adaptive"},
        ),
    )
    prefix = f"{dataset_id}/{subject}/"
    objects = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        objects.extend(page.get("Contents", []))
    # BrainVision .eeg byte ranges depend on the accompanying .vhdr header.
    # Download metadata in a completed phase before scheduling any EEG bytes;
    # queue ordering alone does not establish that dependency with a pool.
    metadata_objects = [obj for obj in objects if not obj["Key"].lower().endswith(".eeg")]
    eeg_objects = [obj for obj in objects if obj["Key"].lower().endswith(".eeg")]
    transfer_config = TransferConfig(
        use_threads=True,
        max_concurrency=4,
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=64 * 1024 * 1024,
    )

    def _required_eeg_bytes(key: str, size: int) -> int | None:
        if required_duration_seconds is None or not key.lower().endswith(".eeg"):
            return None
        header = dest / Path(key[len(prefix):]).with_suffix(".vhdr")
        if not header.exists():
            return None
        try:
            text = header.read_text(encoding="utf-8", errors="replace")
            channels = int(re.search(r"^NumberOfChannels=(\d+)", text, re.MULTILINE).group(1))
            interval_us = float(re.search(r"^SamplingInterval=([0-9.]+)", text, re.MULTILINE).group(1))
            format_match = re.search(r"^BinaryFormat=(.+)$", text, re.MULTILINE)
            bytes_per_sample = 4 if "32" in (format_match.group(1) if format_match else "") else 2
            samples = int(required_duration_seconds * 1_000_000 / interval_us + 0.999999)
            return min(size, channels * samples * bytes_per_sample)
        except (AttributeError, ValueError):
            return None

    def download(obj: dict) -> None:
        key = obj["Key"]
        rel = key[len(prefix):]
        if not rel:
            return
        target = dest / Path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        required_bytes = _required_eeg_bytes(key, obj["Size"])
        if required_duration_seconds is not None and key.lower().endswith(".eeg") and required_bytes is None:
            raise ValueError(f"BrainVision header unavailable or invalid for ranged download: {key}")
        if target.exists() and (
            target.stat().st_size == obj["Size"]
            or (required_bytes is not None and target.stat().st_size >= required_bytes)
        ):
            return
        partial = target.with_name(target.name + ".part")
        if partial.exists():
            partial.unlink()
        for stale in target.parent.glob(target.name + ".part*"):
            stale.unlink(missing_ok=True)
        last_error = None
        for _attempt in range(3):
            try:
                if required_bytes is not None and required_bytes < obj["Size"]:
                    response = client.get_object(
                        Bucket=bucket,
                        Key=key,
                        Range=f"bytes=0-{required_bytes - 1}",
                    )
                    with partial.open("wb") as out:
                        while True:
                            chunk = response["Body"].read(8 * 1024 * 1024)
                            if not chunk:
                                break
                            out.write(chunk)
                else:
                    client.download_file(bucket, key, str(partial), Config=transfer_config)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                for stale in target.parent.glob(target.name + ".part*"):
                    stale.unlink(missing_ok=True)
        if last_error is not None:
            raise last_error
        expected_size = required_bytes if required_bytes is not None else obj["Size"]
        if partial.stat().st_size != expected_size:
            raise IOError(f"incomplete S3 object {key}: {partial.stat().st_size} != {expected_size}")
        os.replace(partial, target)

    def _download_batch(batch: list[dict]) -> None:
        with ThreadPoolExecutor(max_workers=12, thread_name_prefix="s3-subject") as pool:
            futures = [pool.submit(download, obj) for obj in batch]
            for future in as_completed(futures):
                future.result()

    _download_batch(metadata_objects)
    _download_batch(eeg_objects)
    return dest


def sync_s3_dataset_metadata(
    bucket: str, dataset_id: str, dest_root: Path, extra_includes: list[str] | None = None
) -> None:
    """Top-level BIDS files needed for inspection (participants.tsv etc), synced once.

    `extra_includes` lets a caller pull additional dataset-level files (e.g.
    ds001787's behavioral zip) into the same single sync call.
    """
    cmd = _aws_command() + [
        "s3", "sync", "--no-sign-request", "--only-show-errors",
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
    # Replace atomically so an interrupted write cannot leave a valid-looking
    # but truncated checkpoint and force the whole run to be repeated.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp.replace(path)


def run_manifest_loop(
    items: list,
    out_path: Path,
    key_fn: Callable[[object], str],
    process_fn: Callable[[object], dict],
    limit: int | None = None,
    label_fn: Callable[[object], str] | None = None,
) -> dict:
    """Resume/checkpoint loop for streamers that do NOT sync a per-subject
    directory to disk — either they download a single file per item (the fMRI
    streamers) or read remotely with no download at all (the DANDI/NWB
    streamer). Shared shape: a flat `{"processed": {key: result_dict}}`
    manifest in `out_path`, one entry per item, written after every item so an
    interrupted run resumes cleanly.

    `key_fn(item) -> stable str` identifies an item in the manifest (subject id,
    asset path, ...). `process_fn(item) -> result dict` does the real work and
    may raise; a raise is caught and recorded as `{"error": ...}` so one bad
    item never aborts the cohort. `label_fn(item)` is an optional pretty label
    for the progress line (defaults to the key). Returns the manifest.

    This is the download/lazy-read counterpart to `run_streaming_loop` (which
    owns the sync-to-disk-then-delete discipline for the OpenNeuro S3 EEG
    streamers); both keep the resume/checkpoint contract in one place instead
    of re-implemented per dataset.
    """
    out_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"processed": {}}
    manifest.setdefault("processed", {})

    todo = [it for it in items if key_fn(it) not in manifest["processed"]]
    if limit is not None:
        todo = todo[:limit]

    print(f"{len(items)} items total, {len(manifest['processed'])} done, {len(todo)} to process this run.")
    for item in todo:
        key = key_fn(item)
        print(f"--- {label_fn(item) if label_fn else key} ---")
        try:
            result = process_fn(item)
            print(f"  done: {result}")
        except Exception as exc:  # keep going: one bad item shouldn't kill the run
            result = {"error": str(exc)}
            print(f"  ERROR: {exc}", file=sys.stderr)
        manifest["processed"][key] = result
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest


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
            # Release MNE file handles and bounded window samples before the
            # subject directory is removed on disk, especially on Windows.
            try:
                from data.bids_ingest import clear_raw_cache
                clear_raw_cache()
            except ImportError:
                pass
            if not keep_raw:
                shutil.rmtree(work_path / subject, ignore_errors=True)
            save_manifest(manifest_path, manifest)  # checkpoint after every subject

    return manifest
