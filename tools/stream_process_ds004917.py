#!/usr/bin/env python3
"""Stream-process ds004917 (parietal-inhibition TMS-EEG) with bounded parallelism.

Dedicated runner: ds004917's unit of analysis is not a fixed-interval window
but a TMS-pulse-locked evoked response per stimulation site, computed by
`sciencer_d/btc_icft/level_m/ds004917_pcist_real.py::compute_pcist_by_site`
into real PCIst (Comolatti et al. 2019). No generic windower fits that shape,
and no existing tool wraps that library function -- this is that wrapper.

Why a bespoke pool instead of `tools/streaming/base_runner.run_streaming_loop`
(used by every other streamer): that loop is strictly sequential, and
ds004917 is the compute-heavy dataset (each subject: read a ~1.3 GB
BrainVision recording, bandpass-filter it, trial-average 80 pulses x 3 sites,
run PCIst). With 4 cores / ~15 GB RAM and one subject peaking ~5 GB, running
TWO subjects concurrently roughly halves the ~53-subject wall-clock at safe
memory headroom. The parent process owns the manifest and resume logic
entirely; each worker only syncs -> computes -> deletes its OWN subject's raw
files, so there is no cross-process manifest contention (workers return
results; the parent checkpoints). Peak disk stays at ~2 subjects' raw at once.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.streaming import base_runner  # noqa: E402

_DATASET_ID = "ds004917"
_BUCKET = "openneuro.org"


def _process_one_subject(subject: str, work_root: str, min_trials: int, max_channels: int, keep_raw: bool) -> dict:
    """Worker: sync one subject's raw, compute PCIst-by-site, delete raw.

    Runs in a separate process (ProcessPoolExecutor). Returns a plain-dict
    result the parent serializes into the manifest and per-subject JSON. Any
    exception propagates to the parent's future, which records it in
    `failed_subjects` without killing the pool.
    """
    from sciencer_d.btc_icft.level_m.ds004917_pcist_real import compute_pcist_by_site

    work_path = Path(work_root)
    subject_dir = work_path / subject
    try:
        base_runner.sync_s3_subject(_BUCKET, _DATASET_ID, subject, work_path)
        rows = compute_pcist_by_site(
            str(work_path), subject_filter=subject,
            max_channels=max_channels, min_trials=min_trials,
        )
        return {"subject": subject, "rows": rows}
    finally:
        if not keep_raw:
            shutil.rmtree(subject_dir, ignore_errors=True)


def run(
    out_dir: str, work_root: str,
    min_trials: int = 5, max_channels: int = 16, workers: int = 2,
    limit: int | None = None, subjects: list[str] | None = None, keep_raw: bool = False,
) -> int:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    work_path = Path(work_root)
    work_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / "manifest.json"
    manifest = base_runner.load_manifest(manifest_path)

    all_subjects = subjects if subjects is not None else base_runner.list_s3_subjects(_BUCKET, f"{_DATASET_ID}/")
    todo = [s for s in all_subjects if s not in manifest["processed_subjects"]]
    if limit:
        todo = todo[:limit]
    print(f"{len(all_subjects)} subjects total, {len(todo)} to process this run ({workers} workers).")

    all_rows: list[dict] = []
    # Preserve rows already written on a resumed run.
    rows_path = out_path / "pcist_by_site.jsonl"
    if rows_path.exists():
        all_rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(_process_one_subject, s, work_root, min_trials, max_channels, keep_raw): s
            for s in todo
        }
        for fut in as_completed(futures):
            subject = futures[fut]
            try:
                result = fut.result()
                rows = result["rows"]
                manifest["processed_subjects"][subject] = {"n_site_rows": len(rows)}
                all_rows.extend(rows)
                with rows_path.open("a", encoding="utf-8") as f:
                    for r in rows:
                        f.write(json.dumps(r, default=str) + "\n")
                print(f"  done: {subject} ({len(rows)} site rows)")
            except Exception as e:  # one bad subject shouldn't kill the pool
                print(f"  FAILED: {subject}: {e}", file=sys.stderr)
                manifest["failed_subjects"][subject] = str(e)
            finally:
                base_runner.save_manifest(manifest_path, manifest)

    (out_path / "pcist_by_site.json").write_text(json.dumps(all_rows, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {len(all_rows)} total site rows across "
          f"{len(manifest['processed_subjects'])} subjects "
          f"({len(manifest['failed_subjects'])} failed).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="outputs/btc_icft/ds004917/stream")
    p.add_argument("--work-root", default="data/ds004917")
    p.add_argument("--min-trials", type=int, default=5)
    p.add_argument("--max-channels", type=int, default=16)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--subjects", nargs="*", default=None)
    p.add_argument("--keep-raw", action="store_true")
    a = p.parse_args()
    return run(
        a.out, a.work_root, a.min_trials, a.max_channels, a.workers,
        a.limit, a.subjects, a.keep_raw,
    )


if __name__ == "__main__":
    raise SystemExit(main())
