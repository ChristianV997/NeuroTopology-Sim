from __future__ import annotations

import argparse
import sys

from sciencer_d.btc_icft.level_m.ds005620_baseline import (
    build_mock_ds005620_level_m_rows,
    evaluate_level_m_baseline,
    write_level_m_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/btc_icft/ds005620_m.yaml")
    parser.add_argument("--out", default="outputs/btc_icft/ds005620/m_baseline")
    parser.add_argument("--task", default="awake_vs_sedated")
    parser.add_argument("--mock", action="store_true", default=True)
    parser.add_argument("--real", action="store_true", help="Disable mock mode.")
    parser.add_argument("--bids-root", default=None)
    args = parser.parse_args()

    use_mock = args.mock and not args.real
    if not use_mock:
        print(
            "Real DS005620 ingestion is not implemented in this baseline scaffold. Use --mock for offline validation.",
            file=sys.stderr,
        )
        return 2

    rows = build_mock_ds005620_level_m_rows()
    result = evaluate_level_m_baseline(rows, task=args.task)
    write_level_m_outputs(result, out_dir=args.out)
    print(f"wrote DS005620 Level M baseline outputs to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
