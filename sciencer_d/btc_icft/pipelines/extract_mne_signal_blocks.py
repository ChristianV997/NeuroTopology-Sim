from __future__ import annotations
import argparse, sys
from pathlib import Path
from sciencer_d.btc_icft.io.eeg_mne_adapter import extract_mne_signal_windows, write_mne_signal_outputs, _init_result, check_mne_available


def _mock_result(dataset_id: str, source_file: str):
    cap = {"installed": True, "version": "mock"}
    r = _init_result(dataset_id, source_file, "extracted", [], True, Path(source_file).suffix.lower().lstrip('.') or "edf", cap)
    r.sample_rate_hz = 100.0; r.n_channels = 2; r.channel_names=["C3","C4"]; r.duration_s=4.0
    r.windows=[
        {"dataset_id":dataset_id,"row_id":"mock__win_0","source_file":source_file,"window_id":"win-000","window_start_s":0.0,"window_end_s":2.0,"sample_start":0,"sample_end":200,"sample_rate_hz":100.0,"n_channels":2,"n_samples":200,"channel_names":["C3","C4"],"signal_values":[[0.1]*200,[0.2]*200],"extraction_status":"extracted","warnings":[]},
        {"dataset_id":dataset_id,"row_id":"mock__win_1","source_file":source_file,"window_id":"win-001","window_start_s":2.0,"window_end_s":4.0,"sample_start":200,"sample_end":400,"sample_rate_hz":100.0,"n_channels":2,"n_samples":200,"channel_names":["C3","C4"],"signal_values":[[0.3]*200,[0.4]*200],"extraction_status":"extracted","warnings":[]},
    ]; r.n_windows=2
    return r

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--dataset-id", default="DS005620")
    ap.add_argument("--input")
    ap.add_argument("--out", default="outputs/btc_icft/eeg_mne_extract/DS005620")
    ap.add_argument("--window-seconds", type=float, default=2.0)
    ap.add_argument("--max-windows", type=int, default=10)
    ap.add_argument("--picks")
    ap.add_argument("--mock-fixture", action="store_true")
    ap.add_argument("--mock-mne-missing", action="store_true")
    a=ap.parse_args()
    if not a.mock_fixture and not a.mock_mne_missing and not a.input:
        print("A local EEG file is required. Provide --input or use --mock-fixture.")
        return 1
    if a.mock_fixture:
        res=_mock_result(a.dataset_id, a.input or "mock.edf")
    elif a.mock_mne_missing:
        cap={"installed":False,"version":None}
        res=_init_result(a.dataset_id, a.input or "unknown.edf", "dependency_missing", ["optional_dependency_missing:mne"], True, "edf", cap)
    else:
        picks = [x.strip() for x in a.picks.split(",")] if a.picks else None
        res=extract_mne_signal_windows(a.input, a.dataset_id, a.window_seconds, a.max_windows, picks)
        if check_mne_available()["installed"] is False and res.extraction_status=="dependency_missing":
            write_mne_signal_outputs(res, a.out); return 0
    write_mne_signal_outputs(res, a.out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
