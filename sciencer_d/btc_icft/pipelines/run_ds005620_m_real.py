from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sciencer_d.btc_icft.level_m.ds005620_windows import (
    build_level_m_windows_from_bids_inventory,
    build_mock_level_m_windows_from_inspection,
    evaluate_level_m_windows,
    extract_level_m_window_features,
    load_bids_inspection_outputs,
    write_level_m_window_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DS005620 real/local Level M window extraction scaffold")
    parser.add_argument("--inspection", default="outputs/btc_icft/ds005620/bids_inspection")
    parser.add_argument("--out", default="outputs/btc_icft/ds005620/m_real")
    parser.add_argument("--task", default="awake_vs_sedated")
    parser.add_argument("--window-seconds", type=float, default=10.0)
    parser.add_argument("--max-windows-per-file", type=int, default=2)
    parser.add_argument("--mock-fixture", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--bids-root", default=None,
                        help="Local BIDS root for --real (e.g. eegdash cache or s3-synced ds005620).")
    parser.add_argument("--max-channels", type=int, default=16)
    args = parser.parse_args()

    if args.real:
        if not args.bids_root:
            print("--real requires --bids-root pointing at a local BIDS dataset "
                  "(e.g. `aws s3 sync --no-sign-request s3://openneuro.org/ds005620 <dir>`).",
                  file=sys.stderr)
            return 2
        from sciencer_d.btc_icft.level_m.ds005620_windows_real import (
            build_and_extract_real_windows,
        )
        windows = build_and_extract_real_windows(
            args.bids_root,
            window_seconds=args.window_seconds,
            max_windows_per_file=args.max_windows_per_file,
            max_channels=args.max_channels,
        )
        # features are already real; go straight to evaluation
        result = evaluate_level_m_windows(windows, task=args.task)
        paths = write_level_m_window_outputs(result, args.out)
        for k, v in paths.items():
            print(f"{k}: {v}")
        return 0

    if args.mock_fixture:
        windows = build_mock_level_m_windows_from_inspection()
    else:
        if not Path(args.inspection).exists():
            print(
                "BIDS inspection outputs are required. Run inspect_ds005620_bids first or use --mock-fixture for offline validation.",
                file=sys.stderr,
            )
            return 2
        inspection = load_bids_inspection_outputs(args.inspection)
        windows = build_level_m_windows_from_bids_inventory(
            inspection,
            window_seconds=args.window_seconds,
            max_windows_per_file=args.max_windows_per_file,
        )

    rows = extract_level_m_window_features(windows)
    result = evaluate_level_m_windows(rows, task=args.task)
    paths = write_level_m_window_outputs(result, args.out)
    for k, v in paths.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
