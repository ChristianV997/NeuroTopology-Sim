from __future__ import annotations
import argparse, sys
from pathlib import Path
from sciencer_d.btc_icft.io.eeg_mne_adapter import (
    build_mne_adapter_omega_event,
    check_mne_available,
    extract_mne_signal_windows,
    mne_extract_evidence_watermarks,
    write_mne_signal_outputs,
    _init_result,
)


def _mock_window(dataset_id: str, source_file: str, idx: int, start: int, end: int, values: list) -> dict:
    """Deterministic offline fixture window — never claims scientific_pass."""
    marks = mne_extract_evidence_watermarks(mock_fixture=True)
    return {
        "dataset_id": dataset_id,
        "row_id": f"mock__win_{idx}",
        "source_file": source_file,
        "window_id": f"win-{idx:03d}",
        "window_start_s": float(start) / 100.0,
        "window_end_s": float(end) / 100.0,
        "sample_start": start,
        "sample_end": end,
        "sample_rate_hz": 100.0,
        "n_channels": 2,
        "n_samples": end - start,
        "channel_names": ["C3", "C4"],
        "signal_values": values,
        "extraction_status": "extracted",
        "warnings": ["mock_fixture_non_empirical"],
        # Finite synthetic values may be engineering-ready, but never scientific.
        "scientific_pass": False,
        "is_valid": True,
        "non_finite_samples": False,
        "evidence_class": marks["evidence_class"],
        "run_mode": marks["run_mode"],
        "metrics_are_empirical": marks["metrics_are_empirical"],
    }


def _mock_result(dataset_id: str, source_file: str):
    """Offline mock extract result with fail-closed evidence watermarks."""
    # Do not pretend a real MNE install: version label is explicitly mock.
    cap = {"installed": False, "version": "mock_fixture"}
    r = _init_result(
        dataset_id,
        source_file,
        "extracted",
        [],
        True,
        Path(source_file).suffix.lower().lstrip(".") or "edf",
        cap,
    )
    marks = mne_extract_evidence_watermarks(mock_fixture=True)
    r.sample_rate_hz = 100.0
    r.n_channels = 2
    r.channel_names = ["C3", "C4"]
    r.duration_s = 4.0
    r.windows = [
        _mock_window(
            dataset_id,
            source_file,
            0,
            0,
            200,
            [[0.1] * 200, [0.2] * 200],
        ),
        _mock_window(
            dataset_id,
            source_file,
            1,
            200,
            400,
            [[0.3] * 200, [0.4] * 200],
        ),
    ]
    r.n_windows = 2
    r.scientific_pass = False
    r.warnings = list(r.warnings) + ["mock_fixture_non_empirical"]
    r.evidence_class = marks["evidence_class"]
    r.run_mode = marks["run_mode"]
    r.metrics_are_empirical = marks["metrics_are_empirical"]
    # Rebuild omega after windows/watermarks are attached (init had n_windows=0).
    r.omega_event = build_mne_adapter_omega_event(r)
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
        res = _mock_result(a.dataset_id, a.input or "mock.edf")
    elif a.mock_mne_missing:
        cap = {"installed": False, "version": None}
        res = _init_result(
            a.dataset_id,
            a.input or "unknown.edf",
            "dependency_missing",
            ["optional_dependency_missing:mne"],
            True,
            "edf",
            cap,
        )
        marks = mne_extract_evidence_watermarks(mock_fixture=True)
        res.evidence_class = marks["evidence_class"]
        res.run_mode = marks["run_mode"]
        res.metrics_are_empirical = marks["metrics_are_empirical"]
        res.scientific_pass = False
        res.omega_event = build_mne_adapter_omega_event(res)
    else:
        picks = [x.strip() for x in a.picks.split(",")] if a.picks else None
        res = extract_mne_signal_windows(
            a.input, a.dataset_id, a.window_seconds, a.max_windows, picks
        )
        marks = mne_extract_evidence_watermarks(mock_fixture=False)
        res.evidence_class = marks["evidence_class"]
        res.run_mode = marks["run_mode"]
        res.metrics_are_empirical = marks["metrics_are_empirical"]
        # Preserve finite-window scientific_pass from extractor; never flip True here.
        if res.scientific_pass is not True:
            res.scientific_pass = False
        res.omega_event = build_mne_adapter_omega_event(res)
        if check_mne_available()["installed"] is False and res.extraction_status == "dependency_missing":
            write_mne_signal_outputs(res, a.out)
            return 0
    write_mne_signal_outputs(res, a.out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
