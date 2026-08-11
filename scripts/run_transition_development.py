"""Stream ds003969 subjects and persist the frozen transition feature panel."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_runtime.feature_adapter import enrich_transition_window
from tools.stream_process_openneuro_dataset import list_s3_subjects, sync_dataset_metadata, sync_subject
from sciencer_d.btc_icft.level_m.generic_windows_real import build_and_extract_real_windows
from sciencer_d.btc_icft.level_t.base_real_topology import compute_real_topology_for_window


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(rows[0]) if rows else ["row_id"])
        writer.writeheader()
        writer.writerows(rows)


def _checkpoint(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _event(path: Path, event: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def run(subjects: list[str], output_dir: Path, work_root: Path, *, window_seconds: float = 10.0, max_windows_per_file: int = 10, max_channels: int = 16, spectral_frequency_bins: int = 16, spectral_max_frequencies: int = 16) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)
    if not any(work_root.glob("*.tsv")):
        sync_dataset_metadata("ds003969", work_root)
    manifest_path = output_dir / "manifest.json"
    events_path = output_dir / "events.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"processed_subjects": {}, "failed_subjects": {}}
    manifest.setdefault("processed_subjects", {})
    manifest.setdefault("failed_subjects", {})
    _checkpoint(manifest_path, manifest)
    for subject in subjects:
        if subject in manifest["processed_subjects"]:
            _event(events_path, {"event": "skip_processed", "subject_id": subject, "time": time.time()})
            continue
        subject_root = None
        started = time.time()
        _event(events_path, {"event": "subject_started", "subject_id": subject, "time": started})
        try:
            subject_root = sync_subject("ds003969", subject, work_root)
            m_rows = build_and_extract_real_windows("ds003969", str(subject_root.parent), window_seconds=window_seconds, max_windows_per_file=max_windows_per_file, max_channels=max_channels, subject_filter=subject)
            m_dicts = [asdict(row) for row in m_rows]
            t_dicts = [asdict(compute_real_topology_for_window(row, max_channels=max_channels)) for row in m_dicts]
            t_by_id = {row["row_id"]: row for row in t_dicts}
            features = [enrich_transition_window(m_row, t_by_id[m_row["row_id"]], max_channels=max_channels, spectral_frequency_bins=spectral_frequency_bins, spectral_max_frequencies=spectral_max_frequencies) for m_row in m_dicts]
            _write_rows(output_dir / f"{subject}_transition_features.csv", features)
            manifest["processed_subjects"][subject] = {"n_windows": len(features), "feature_names": sorted(features[0]) if features else [], "seconds": time.time() - started}
            manifest["failed_subjects"].pop(subject, None)
            _event(events_path, {"event": "subject_completed", "subject_id": subject, "n_windows": len(features), "seconds": time.time() - started, "time": time.time()})
        except Exception as exc:
            manifest["failed_subjects"][subject] = f"{type(exc).__name__}: {exc}"
            _event(events_path, {"event": "subject_failed", "subject_id": subject, "error": manifest["failed_subjects"][subject], "seconds": time.time() - started, "time": time.time()})
        finally:
            if subject_root is not None and subject_root.exists():
                shutil.rmtree(subject_root)
            _checkpoint(manifest_path, manifest)
    manifest["finished_at"] = time.time()
    _checkpoint(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--window-seconds", type=float, default=10.0)
    parser.add_argument("--max-windows-per-file", type=int, default=10)
    parser.add_argument("--max-channels", type=int, default=16)
    parser.add_argument("--spectral-frequency-bins", type=int, default=16)
    parser.add_argument("--spectral-max-frequencies", type=int, default=16)
    args = parser.parse_args()
    result = run(args.subjects, args.out, args.work_root, window_seconds=args.window_seconds, max_windows_per_file=args.max_windows_per_file, max_channels=args.max_channels, spectral_frequency_bins=args.spectral_frequency_bins, spectral_max_frequencies=args.spectral_max_frequencies)
    print(json.dumps({"processed": len(result["processed_subjects"]), "failed": len(result["failed_subjects"])}, sort_keys=True))
    return 0 if not result["failed_subjects"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
