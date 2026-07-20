from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sciencer_d.btc_icft.level_m.ds003816_windows import (
    evaluate_level_m_windows,
    write_level_m_window_outputs,
)
from sciencer_d.btc_icft.level_m.real_features import build_mfdfa_report, build_real_level_m_features_report


def _write_real_features_report(result, out_dir: str, sample_size: int | None) -> str:
    report = build_real_level_m_features_report(result.rows, sample_size=sample_size)
    path = Path(out_dir) / "real_level_m_features_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return str(path)


def _write_mfdfa_report(result, out_dir: str, sample_size: int | None, max_duration_s: float | None) -> str:
    report = build_mfdfa_report(result.rows, sample_size=sample_size, max_duration_s=max_duration_s)
    path = Path(out_dir) / "mfdfa_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DS003816 real/local Level M window extraction")
    parser.add_argument("--out", default="outputs/btc_icft/ds003816/m_real")
    parser.add_argument("--task", default="lkm_vs_resting")
    parser.add_argument("--window-seconds", type=float, default=10.0)
    parser.add_argument("--max-windows-per-file", type=int, default=2)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--bids-root", default=None,
                        help="Local BIDS root for --real (e.g. s3-synced ds003816).")
    parser.add_argument("--max-channels", type=int, default=16)
    parser.add_argument("--subject", default=None, help="Restrict to a single subject_id (e.g. sub-01lt).")
    parser.add_argument("--real-features-sample-size", type=int, default=0,
                        help="Bound how many windows the real band-power/complexity/aperiodic "
                             "features report (real_level_m_features_report.json) runs on; 0 means all windows.")
    parser.add_argument("--mfdfa-sample-size", type=int, default=5,
                        help="Bound the number of distinct RECORDINGS (not windows) the multifractal-DFA "
                             "report fits; 0 means all recordings.")
    parser.add_argument("--mfdfa-max-duration-s", type=float, default=120.0,
                        help="Truncate each recording to this many seconds before MFDFA fitting; 0 means use the full recording.")
    args = parser.parse_args()

    if not args.real:
        print("run_ds003816_m_real currently only supports --real (no mock/inspection path exists for ds003816).", file=sys.stderr)
        return 2
    if not args.bids_root:
        print("--real requires --bids-root pointing at a local BIDS dataset "
              "(e.g. `aws s3 sync --no-sign-request s3://openneuro.org/ds003816 <dir>`).",
              file=sys.stderr)
        return 2

    from sciencer_d.btc_icft.level_m.ds003816_windows_real import build_and_extract_real_windows

    windows = build_and_extract_real_windows(
        args.bids_root,
        window_seconds=args.window_seconds,
        max_windows_per_file=args.max_windows_per_file,
        max_channels=args.max_channels,
        subject_filter=args.subject,
    )
    result = evaluate_level_m_windows(windows, task=args.task)
    paths = write_level_m_window_outputs(result, args.out)
    paths["real_level_m_features_report"] = _write_real_features_report(
        result, args.out, sample_size=(args.real_features_sample_size or None)
    )
    paths["mfdfa_report"] = _write_mfdfa_report(
        result, args.out, sample_size=(args.mfdfa_sample_size if args.mfdfa_sample_size > 0 else None),
        max_duration_s=(args.mfdfa_max_duration_s if args.mfdfa_max_duration_s > 0 else None),
    )
    for k, v in paths.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
