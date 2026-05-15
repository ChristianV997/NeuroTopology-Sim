"""P18.3 CLI — DS005620 real/local execution gate.

Inspects prerequisites for a real DS005620 run and writes gate outputs.
Does NOT execute real data, download data, infer labels, or confirm human review.

Usage
-----
# Default paths (writes 7 outputs to outputs/btc_icft/ds005620_real_execution_gate/):
python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_real_local_execution

# Custom out directory:
python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_real_local_execution \\
  --out outputs/btc_icft/ds005620_real_execution_gate

# JSON summary to stdout:
python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_real_local_execution --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sciencer_d.btc_icft.p18.ds005620_real_local_execution_gate import (
    build_default_real_local_path_config,
    build_real_local_execution_gate,
    write_real_local_execution_gate_outputs,
)

_DEFAULT_OUT = "outputs/btc_icft/ds005620_real_execution_gate"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "P18.3: DS005620 real/local execution gate. "
            "Inspects prerequisites and prepares human-reviewed execution commands. "
            "Does NOT execute real data or confirm peer review."
        )
    )
    ap.add_argument("--dataset-id", default="DS005620")
    ap.add_argument(
        "--metadata",
        default=None,
        help="Path to DS005620 metadata file (default: data/DS005620/events.tsv)",
    )
    ap.add_argument(
        "--reviewed-contract",
        default=None,
        dest="reviewed_contract",
        help="Path to reviewed external contract JSON",
    )
    ap.add_argument(
        "--mne-extract",
        default=None,
        dest="mne_extract",
        help="Path to MNE extraction output directory",
    )
    ap.add_argument(
        "--signal-blocks",
        default=None,
        dest="signal_blocks",
        help="Path to canonical signal blocks directory",
    )
    ap.add_argument(
        "--level-m",
        default=None,
        dest="level_m",
        help="Path to features_m_signal.csv",
    )
    ap.add_argument(
        "--level-t",
        default=None,
        dest="level_t",
        help="Path to features_t_signal.csv",
    )
    ap.add_argument(
        "--execution-root",
        default=None,
        dest="execution_root",
        help="Real execution output root directory",
    )
    ap.add_argument(
        "--out",
        default=_DEFAULT_OUT,
        help="Output directory for gate artifacts",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit nonzero if gate is not artifact-ready (still does not execute)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json_out",
        help="Print JSON summary to stdout",
    )
    args = ap.parse_args(argv)

    cfg = build_default_real_local_path_config(
        dataset_id=args.dataset_id,
        metadata=args.metadata,
        reviewed_contract=args.reviewed_contract,
        mne_extract=args.mne_extract,
        signal_blocks=args.signal_blocks,
        level_m=args.level_m,
        level_t=args.level_t,
        execution_root=args.execution_root,
    )

    result = build_real_local_execution_gate(cfg)

    try:
        artifact_paths = write_real_local_execution_gate_outputs(result, args.out)
    except Exception as exc:
        print(f"ERROR writing gate outputs: {exc}", file=sys.stderr)
        return 1

    for name, path in artifact_paths.items():
        print(f"{name}: {path}")

    if args.json_out:
        summary = {
            "dataset_id": result.dataset_id,
            "ready_for_real_execution": result.ready_for_real_execution,
            "all_required_artifacts_present": result.all_required_artifacts_present,
            "reviewed_contract_static_gate_passed": result.reviewed_contract_static_gate_passed,
            "peer_review_required": True,
            "peer_review_confirmed_by_human": False,
            "can_use_execute_flag": False,
            "next_action": result.next_action,
            "missing_groups": result.missing_groups,
        }
        print(json.dumps(summary, indent=2))

    if args.strict and not result.ready_for_real_execution:
        print(
            f"Gate not artifact-ready: next_action={result.next_action}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
