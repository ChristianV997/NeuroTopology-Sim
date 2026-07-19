from __future__ import annotations

import argparse
import sys

from sciencer_d.btc_icft.level_m.ds003969_windows import (
    evaluate_level_m_windows,
    write_level_m_window_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DS003969 real/local Level M window extraction")
    parser.add_argument("--out", default="outputs/btc_icft/ds003969/m_real")
    parser.add_argument("--task", default="meditation_vs_thinking")
    parser.add_argument("--window-seconds", type=float, default=10.0)
    parser.add_argument("--max-windows-per-file", type=int, default=2)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--bids-root", default=None,
                        help="Local BIDS root for --real (e.g. s3-synced ds003969).")
    parser.add_argument("--max-channels", type=int, default=16)
    parser.add_argument("--subject", default=None, help="Restrict to a single subject_id (e.g. sub-001).")
    args = parser.parse_args()

    if not args.real:
        print("run_ds003969_m_real currently only supports --real (no mock/inspection path exists for ds003969).", file=sys.stderr)
        return 2
    if not args.bids_root:
        print("--real requires --bids-root pointing at a local BIDS dataset "
              "(e.g. `aws s3 sync --no-sign-request s3://openneuro.org/ds003969 <dir>`).",
              file=sys.stderr)
        return 2

    from sciencer_d.btc_icft.level_m.ds003969_windows_real import build_and_extract_real_windows

    windows = build_and_extract_real_windows(
        args.bids_root,
        window_seconds=args.window_seconds,
        max_windows_per_file=args.max_windows_per_file,
        max_channels=args.max_channels,
        subject_filter=args.subject,
    )
    result = evaluate_level_m_windows(windows, task=args.task)
    paths = write_level_m_window_outputs(result, args.out)
    for k, v in paths.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
