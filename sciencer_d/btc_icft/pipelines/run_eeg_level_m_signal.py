from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from sciencer_d.btc_icft.io.eeg_signal_blocks import probe_signal_paths, write_signal_probe_outputs
from sciencer_d.btc_icft.level_m.eeg_signal_features import (
    extract_signal_window_features,
    load_signal_window_inventory,
    load_study_readiness,
    write_level_m_signal_outputs,
)


def _mk_mock_signal(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["# channels: 2", "# sample_rate: 100", "ch1,ch2"]
    for i in range(200):
        rows.append(f"{0.1 * i:.3f},{0.2 * i:.3f}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def run(dataset_id: str, signal_blocks: str, study_dir: str | None, out_dir: str, mock_fixture: bool = False) -> int:
    signal_blocks_dir = Path(signal_blocks)
    if mock_fixture:
        fixture_dir = signal_blocks_dir / ".mock_fixture"
        sig = fixture_dir / "mock_signal.csv"
        _mk_mock_signal(sig)
        result = probe_signal_paths([str(sig)], sample_rate_hz=100.0, window_seconds=1.0, max_windows_per_file=2)
        write_signal_probe_outputs(result, str(signal_blocks_dir))
    try:
        windows = load_signal_window_inventory(str(signal_blocks_dir))
    except FileNotFoundError as e:
        print(str(e))
        return 1
    readiness = load_study_readiness(study_dir)
    extracted = extract_signal_window_features(dataset_id=dataset_id, windows=windows)
    extracted.warnings.extend(readiness.get("warnings", []))
    ra = signal_blocks_dir / "reader_alignment_report.json"
    if ra.exists():
        import json
        ready = json.loads(ra.read_text(encoding="utf-8")).get("ready_for_p9_signal_extraction")
        if ready is False:
            extracted.warnings.append("Signal block probe did not mark this dataset ready for P9 signal extraction.")
    write_level_m_signal_outputs(extracted, out_dir)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-id", default="DS005620")
    ap.add_argument("--signal-blocks", default="outputs/btc_icft/ds005620/signal_blocks")
    ap.add_argument("--study-dir", default=None)
    ap.add_argument("--out", default="outputs/btc_icft/eeg_level_m/DS005620")
    ap.add_argument("--mock-fixture", action="store_true")
    args = ap.parse_args()
    return run(args.dataset_id, args.signal_blocks, args.study_dir, args.out, args.mock_fixture)


if __name__ == "__main__":
    sys.exit(main())
