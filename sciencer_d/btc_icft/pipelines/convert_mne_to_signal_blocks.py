from __future__ import annotations
import argparse
import sys
from pathlib import Path
from sciencer_d.btc_icft.io.mne_signal_block_conversion import (
    convert_mne_windows_to_canonical_blocks,
    load_mne_signal_metadata,
    load_mne_signal_windows,
    load_mne_signal_window_values,
    write_mne_signal_block_outputs,
)

def _mock_extracted(dataset_id: str) -> tuple[dict, list[dict], dict]:
    meta = {"dataset_id": dataset_id, "source_file": "mock.edf", "extraction_status": "extracted"}
    windows = [
        {"dataset_id": dataset_id, "row_id": "mock__win_0", "source_file": "mock.edf", "window_id": "win-000", "window_start_s": 0.0, "window_end_s": 2.0, "sample_start": 0, "sample_end": 200, "sample_rate_hz": 100.0, "n_channels": 2, "n_samples": 200, "channel_names": ["C3", "C4"]},
        {"dataset_id": dataset_id, "row_id": "mock__win_1", "source_file": "mock.edf", "window_id": "win-001", "window_start_s": 2.0, "window_end_s": 4.0, "sample_start": 200, "sample_end": 400, "sample_rate_hz": 100.0, "n_channels": 2, "n_samples": 200, "channel_names": ["C3", "C4"]},
    ]
    values = {"dataset_id": dataset_id, "source_file": "mock.edf", "windows": [{"row_id": w["row_id"], "window_id": w["window_id"], "channel_names": ["C3", "C4"], "signal_values": [[0.1] * 200, [0.2] * 200]} for w in windows]}
    return meta, windows, values

def _mock_blocked(dataset_id: str) -> tuple[dict, list[dict], dict]:
    return {"dataset_id": dataset_id, "source_file": "mock.edf", "extraction_status": "dependency_missing"}, [], {"dataset_id": dataset_id, "source_file": "mock.edf", "windows": []}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-id", default="DS005620")
    ap.add_argument("--mne-extract")
    ap.add_argument("--out", default="outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620")
    ap.add_argument("--mock-fixture", action="store_true")
    ap.add_argument("--mock-blocked-input", action="store_true")
    ap.add_argument("--max-windows", type=int)
    args = ap.parse_args()
    if not args.mne_extract and not args.mock_fixture and not args.mock_blocked_input:
        print("P19.1 MNE extraction output directory is required. Provide --mne-extract or use --mock-fixture.")
        return 1
    if args.mock_fixture:
        meta, windows, values = _mock_extracted(args.dataset_id)
    elif args.mock_blocked_input:
        meta, windows, values = _mock_blocked(args.dataset_id)
    else:
        d = Path(args.mne_extract)
        req = ["mne_signal_metadata.json", "mne_signal_windows.csv", "mne_signal_window_values.json"]
        missing = [x for x in req if not (d / x).exists()]
        if missing:
            print(f"Missing required P19.1 input files in {d}: {', '.join(missing)}")
            return 1
        meta = load_mne_signal_metadata(str(d / "mne_signal_metadata.json"))
        windows = load_mne_signal_windows(str(d / "mne_signal_windows.csv"))
        values = load_mne_signal_window_values(str(d / "mne_signal_window_values.json"))
    if args.max_windows is not None:
        windows = windows[: args.max_windows]
    result = convert_mne_windows_to_canonical_blocks(meta, windows, values, args.dataset_id)
    write_mne_signal_block_outputs(result, args.out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
