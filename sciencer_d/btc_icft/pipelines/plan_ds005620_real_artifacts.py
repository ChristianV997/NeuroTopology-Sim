"""P20 CLI — DS005620 real artifact build operator.

Plans local DS005620 artifact preparation without executing real data,
downloading data, or weakening label/target/ontology/language guardrails.

All commands are emitted for manual operator use only. Nothing is executed.

Usage
-----
# Default paths (writes 6 outputs to outputs/btc_icft/ds005620_real_artifact_operator/):
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts

# Custom out directory:
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts \\
  --out outputs/btc_icft/ds005620_real_artifact_operator

# JSON summary to stdout:
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts --json

# Exit nonzero if any prerequisite stage is not complete:
python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts --strict
"""
from __future__ import annotations

import argparse
import json
import sys

from sciencer_d.btc_icft.p18.ds005620_real_artifact_operator import (
    build_default_real_artifact_path_config,
    build_ds005620_real_artifact_build_plan,
    write_ds005620_real_artifact_operator_outputs,
)

_DEFAULT_OUT = "outputs/btc_icft/ds005620_real_artifact_operator"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "P20: DS005620 real artifact build operator. "
            "Plans local artifact preparation without executing real data. "
            "Does NOT download data, infer labels, or confirm peer review."
        )
    )
    ap.add_argument("--dataset-id", default="DS005620")
    ap.add_argument(
        "--metadata",
        default=None,
        help="Path to DS005620 metadata file (default: data/DS005620/events.tsv)",
    )
    ap.add_argument(
        "--raw-eeg-root",
        default=None,
        dest="raw_eeg_root",
        help="Directory containing raw DS005620 EEG files",
    )
    ap.add_argument(
        "--reviewed-contract-source",
        default=None,
        dest="reviewed_contract_source",
        help="Path to human-authored DS005620 activation declaration JSON",
    )
    ap.add_argument(
        "--reviewed-contract",
        default=None,
        dest="reviewed_contract",
        help="Path to materialized P12 reviewed external contract JSON",
    )
    ap.add_argument(
        "--reader-preflight",
        default=None,
        dest="reader_preflight",
        help="Path to EEG reader preflight output directory",
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
        "--real-execution-gate",
        default=None,
        dest="real_execution_gate",
        help="Path to P18.3 real execution gate ready_for_real_execution.json",
    )
    ap.add_argument(
        "--out",
        default=_DEFAULT_OUT,
        help="Output directory for operator artifacts",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit nonzero if any prerequisite stage is not complete",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json_out",
        help="Print JSON summary to stdout",
    )
    args = ap.parse_args(argv)

    cfg = build_default_real_artifact_path_config(
        dataset_id=args.dataset_id,
        metadata=args.metadata,
        raw_eeg_root=args.raw_eeg_root,
        reviewed_contract_source=args.reviewed_contract_source,
        reviewed_contract=args.reviewed_contract,
        reader_preflight=args.reader_preflight,
        mne_extract=args.mne_extract,
        signal_blocks=args.signal_blocks,
        level_m=args.level_m,
        level_t=args.level_t,
        real_execution_gate=args.real_execution_gate,
    )

    plan = build_ds005620_real_artifact_build_plan(cfg)

    try:
        artifact_paths = write_ds005620_real_artifact_operator_outputs(plan, args.out)
    except Exception as exc:
        print(f"ERROR writing operator outputs: {exc}", file=sys.stderr)
        return 1

    for name, path in artifact_paths.items():
        print(f"{name}: {path}")

    if args.json_out:
        summary = {
            "dataset_id": plan.dataset_id,
            "planner_version": plan.planner_version,
            "all_stages_complete": plan.all_stages_complete,
            "ready_for_real_execution_gate": plan.ready_for_real_execution_gate,
            "ready_for_manual_real_execution": plan.ready_for_manual_real_execution,
            "next_action": plan.next_action,
            "next_command": plan.next_command,
            "blockers": plan.blockers,
            "warnings": plan.warnings,
            "guardrails": plan.guardrails,
        }
        print(json.dumps(summary, indent=2))

    if args.strict and not plan.all_stages_complete:
        missing = [s.stage_id for s in plan.stages if s.status != "complete"]
        print(
            f"Incomplete stages: {missing}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
