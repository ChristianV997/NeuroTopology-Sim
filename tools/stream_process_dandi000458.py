#!/usr/bin/env python3
"""Stream-process DANDI dandiset 000458 (Claar/Rembado 2023) — awake vs.
isoflurane-anesthetized head-fixed mouse EEG — one subject (NWB blob) at a time.

First DANDI/NWB dataset in this repo. Unlike the OpenNeuro/PhysioNet EEG
streamers (which `aws s3 sync` a whole subject dir to disk then delete it),
this reads NWB EEG windows LAZILY over HTTP via `data/dandi_nwb_ingest.py`
(HDF5 partial reads through `remfile`), so nothing is downloaded — even the
27 GB raw-Neuropixels files are handled by reading only the ~1-2 MB of EEG
samples each window needs. Manifest-resumable like the fMRI streamers.

State labels come from each recording's own NWB epochs table
(`isoflurane_anesthesia`; awake = pre-induction baseline) — see
`sciencer_d/btc_icft/level_m/dandi000458_windows_real.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.streaming import base_runner  # noqa: E402
from data.dandi_nwb_ingest import resolve_asset_blobs  # noqa: E402

_DANDISET = "000458"
_VERSION = "0.230317.0039"


def process_asset(asset, out_dir: Path, window_seconds: float, max_windows_per_state: int, max_channels: int) -> dict:
    from sciencer_d.btc_icft.level_m.dandi000458_windows_real import build_and_extract_real_windows

    # Use subject+session-date as the CSV stem so multi-session subjects don't collide.
    stem = Path(asset.path).name.replace("_behavior+ecephys.nwb", "")
    m_rows, t_rows = build_and_extract_real_windows(
        asset.blob_url, asset.subject_id,
        window_seconds=window_seconds, max_windows_per_state=max_windows_per_state,
        max_channels=max_channels,
    )
    base_runner.write_rows_csv(out_dir / f"{stem}_features_m.csv", [asdict(r) for r in m_rows], write_empty_marker=True)
    base_runner.write_rows_csv(out_dir / f"{stem}_features_t.csv", [asdict(r) for r in t_rows], write_empty_marker=True)
    states = {}
    for r in m_rows:
        states[r.state_label] = states.get(r.state_label, 0) + 1
    return {"n_m_rows": len(m_rows), "n_t_rows": len(t_rows), "states": states}


def run(out_dir: str, window_seconds: float, max_windows_per_state: int, max_channels: int,
        limit: int | None, subjects: list[str] | None) -> int:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"processed": {}}

    assets = resolve_asset_blobs(_DANDISET, _VERSION)
    if subjects is not None:
        assets = [a for a in assets if a.subject_id in subjects]
    assets = sorted(assets, key=lambda a: a.content_size)  # smallest first (fastest to smoke-test)

    remaining = [a for a in assets if a.path not in manifest["processed"]]
    if limit is not None:
        remaining = remaining[:limit]

    print(f"{len(assets)} NWB assets total, {len(manifest['processed'])} done, {len(remaining)} to process this run.")
    for a in remaining:
        print(f"--- {a.path} ({a.content_size/1e6:.0f} MB, lazy-read) ---")
        try:
            info = process_asset(a, out_path, window_seconds, max_windows_per_state, max_channels)
            print(f"  done: {info}")
            manifest["processed"][a.path] = info
        except Exception as exc:  # never crash the cohort on one bad blob
            print(f"  ERROR: {exc}")
            manifest["processed"][a.path] = {"error": str(exc)}
        manifest_path.write_text(json.dumps(manifest, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="outputs/btc_icft/dandi000458/stream")
    p.add_argument("--window-seconds", type=float, default=10.0)
    p.add_argument("--max-windows-per-state", type=int, default=10)
    p.add_argument("--max-channels", type=int, default=16)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--subjects", nargs="*", default=None)
    a = p.parse_args()
    return run(a.out, a.window_seconds, a.max_windows_per_state, a.max_channels, a.limit, a.subjects)


if __name__ == "__main__":
    raise SystemExit(main())
