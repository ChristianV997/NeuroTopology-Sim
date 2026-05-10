from __future__ import annotations

import argparse
import sys

from sciencer_d.btc_icft.level_m.ds005620_baseline import build_mock_ds005620_level_m_rows
from sciencer_d.btc_icft.level_t.ds005620_features import (
    build_mock_ds005620_level_t_rows,
    evaluate_mt_residual,
    join_level_m_and_t_rows,
    write_mt_outputs,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/btc_icft/ds005620_mt.yaml")
    p.add_argument("--out", default="outputs/btc_icft/ds005620/mt_residual")
    p.add_argument("--task", default="awake_vs_sedated")
    p.add_argument("--mock", action="store_true", default=True)
    p.add_argument("--real", action="store_true")
    args = p.parse_args()

    if args.real:
        print("Real DS005620 M+T ingestion is not implemented in this residual scaffold. Use --mock for offline validation.", file=sys.stderr)
        return 1

    m_rows = build_mock_ds005620_level_m_rows()
    t_rows = build_mock_ds005620_level_t_rows()
    joined = join_level_m_and_t_rows(m_rows, t_rows)
    result = evaluate_mt_residual(joined, args.task)
    write_mt_outputs(result, args.out)
    print(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
