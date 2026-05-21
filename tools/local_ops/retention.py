"""
Run output retention for the local continuous operations runner (P25).

Archives previous run outputs and keeps only the last N run directories.

stdlib only. Uses pathlib/shutil. Never deletes outside outputs/local_ops/runs/.
"""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path

_LOCAL_OPS_FILENAMES = [
    "local_ops_state.json",
    "local_ops_plan.json",
    "local_ops_results.json",
    "local_ops_next_action.json",
    "local_ops_report.md",
    "local_ops_events.jsonl",
    "local_ops_status.json",
    "local_ops_healthcheck.json",
]


def archive_current_run(output_root: str | Path) -> Path | None:
    """
    Copy current run outputs from output_root into output_root/runs/<timestamp>/.

    Returns the archive directory path, or None if nothing to archive.
    """
    out = Path(output_root)
    runs_dir = out / "runs"

    files_to_archive = [out / f for f in _LOCAL_OPS_FILENAMES if (out / f).exists()]
    if not files_to_archive:
        return None

    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    archive_dir = runs_dir / ts
    archive_dir.mkdir(parents=True, exist_ok=True)

    for src in files_to_archive:
        dst = archive_dir / src.name
        shutil.copy2(src, dst)

    return archive_dir


def rotate_run_outputs(output_root: str | Path, keep_last: int = 25) -> list[Path]:
    """
    Delete oldest run directories until at most keep_last remain.

    Never deletes outside output_root/runs/.
    Returns list of deleted directories.
    """
    runs_dir = Path(output_root) / "runs"
    if not runs_dir.exists():
        return []

    run_dirs = sorted(
        [d for d in runs_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )

    to_delete = run_dirs[: max(0, len(run_dirs) - keep_last)]
    deleted = []
    for d in to_delete:
        # Safety: only delete if inside runs_dir
        try:
            if runs_dir in d.parents or d.parent == runs_dir:
                shutil.rmtree(d)
                deleted.append(d)
        except Exception:
            pass

    return deleted
