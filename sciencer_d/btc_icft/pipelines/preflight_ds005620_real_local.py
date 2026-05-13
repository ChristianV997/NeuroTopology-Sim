"""
P18.2 Real/Local Preflight CLI.

Checks all prerequisites for a live P18.1 DS005620 real/local execution.
Does NOT execute any pipeline stage, download data, or activate contracts.

Usage:
  python -m sciencer_d.btc_icft.pipelines.preflight_ds005620_real_local \\
    --reviewed-contract outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json \\
    --metadata data/DS005620/events.tsv \\
    --signal-blocks outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620 \\
    --level-m outputs/btc_icft/eeg_level_m/DS005620 \\
    --level-t outputs/btc_icft/eeg_level_t/DS005620 \\
    --out outputs/btc_icft/ds005620_real_local_preflight
"""
from __future__ import annotations

import argparse
import sys

from sciencer_d.btc_icft.p18.ds005620_real_local_preflight import (
    run_real_local_preflight,
    write_preflight_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DS005620 real/local preflight check (P18.2)")
    parser.add_argument("--dataset-id", default="DS005620")
    parser.add_argument("--reviewed-contract", default=None)
    parser.add_argument("--metadata", default=None)
    parser.add_argument("--signal-blocks", default=None)
    parser.add_argument("--level-m", default=None)
    parser.add_argument("--level-t", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    result = run_real_local_preflight(
        dataset_id=args.dataset_id,
        reviewed_contract=args.reviewed_contract,
        metadata=args.metadata,
        signal_blocks=args.signal_blocks,
        level_m=args.level_m,
        level_t=args.level_t,
    )

    artifacts = write_preflight_outputs(result, args.out)

    print(f"all_ready: {result.all_ready}")
    print(f"next_action: {result.next_action}")
    print(f"blockers: {len(result.blockers)}")
    print(f"artifacts written to: {args.out}")
    return 0 if result.all_ready else 1


if __name__ == "__main__":
    sys.exit(main())
