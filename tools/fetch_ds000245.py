#!/usr/bin/env python3
"""Fetch ds000245 (Parkinson's resting-state fMRI, 45 subjects, ~1.66 GB) from
OpenNeuro S3 in full -- unlike ds005620 this dataset is small enough that the
ranged-download machinery in tools/streaming/base_runner.py is unnecessary; a
plain concurrent full-object download covers all 45 `_bold.nii.gz` files.

This closes the deferred half of REPORT_gate_ds000245_ds005620.md: the ds005620
alpha-anteriorization headline was gated in that report; ds000245's
global_efficiency (claimed eta^2=0.41) was deferred because no raw BOLD or ROI
timeseries survived a prior run. This script performs the re-fetch that report
scoped as step 1 of gating it for real.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_BUCKET = "openneuro.org"
_DATASET = "ds000245"


def _s3_client():
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    return boto3.client(
        "s3",
        config=Config(
            signature_version=UNSIGNED,
            max_pool_connections=16,
            connect_timeout=20,
            read_timeout=120,
            retries={"max_attempts": 5, "mode": "adaptive"},
        ),
    )


def fetch(dest_root: Path, limit: int | None = None) -> dict:
    client = _s3_client()
    objects = []
    for page in client.get_paginator("list_objects_v2").paginate(
        Bucket=_BUCKET, Prefix=f"{_DATASET}/sub-"
    ):
        objects.extend(
            obj for obj in page.get("Contents", []) if obj["Key"].endswith("_bold.nii.gz")
        )
    objects.sort(key=lambda o: o["Key"])
    if limit is not None:
        objects = objects[:limit]

    def download(obj: dict) -> str:
        key = obj["Key"]
        rel = key[len(f"{_DATASET}/") :]
        target = dest_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size == obj["Size"]:
            return f"skip (already present): {rel}"
        partial = target.with_suffix(target.suffix + ".part")
        client.download_file(_BUCKET, key, str(partial))
        if partial.stat().st_size != obj["Size"]:
            partial.unlink(missing_ok=True)
            raise IOError(f"incomplete download for {key}")
        partial.replace(target)
        return f"downloaded: {rel} ({obj['Size'] / 1e6:.1f} MB)"

    results = {"downloaded": [], "skipped": [], "failed": []}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(download, obj): obj["Key"] for obj in objects}
        for future in as_completed(futures):
            key = futures[future]
            try:
                msg = future.result()
                print(f"  {msg}")
                (results["skipped"] if msg.startswith("skip") else results["downloaded"]).append(key)
            except Exception as exc:
                print(f"  FAILED: {key}: {exc}")
                results["failed"].append({"key": key, "error": str(exc)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path("data/ds000245"))
    parser.add_argument("--limit", type=int, default=None, help="fetch only the first N subjects (testing)")
    args = parser.parse_args()

    results = fetch(args.dest, args.limit)
    print(
        f"\n{len(results['downloaded'])} downloaded, {len(results['skipped'])} already present, "
        f"{len(results['failed'])} failed"
    )
    return 1 if results["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
