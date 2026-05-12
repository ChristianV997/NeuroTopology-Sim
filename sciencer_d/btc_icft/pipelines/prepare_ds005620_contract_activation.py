"""P16 CLI — DS005620 human-reviewed label contract activation packet.

Audits local DS005620 metadata and produces an activation proposal and
human-review packet. Does NOT activate any real label contract.

Usage
-----
# Mock fixture (no real data required):
python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation \\
  --mock-fixture --out outputs/btc_icft/ds005620_contract_activation

# Real/local metadata:
python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation \\
  --metadata data/DS005620/events.tsv \\
  --contract-drafts outputs/btc_icft/label_contract_drafts/contract_drafts.json \\
  --out outputs/btc_icft/ds005620_contract_activation
"""
from __future__ import annotations

import argparse
import sys

from sciencer_d.btc_icft.labels.ds005620_contract_activation import (
    _SAFE_CLAIM,
    load_contract_drafts,
    load_metadata_rows,
    prepare_ds005620_activation_proposal,
    write_ds005620_activation_outputs,
)

_NO_METADATA_MSG = (
    "DS005620 local metadata is required. "
    "Provide --metadata or use --mock-fixture."
)

_MOCK_METADATA_ROWS = [
    {"onset": "0.0", "duration": "10.0", "trial_type": "focus",
     "condition": "A", "notes": "participant reported mild distraction",
     "filename": "sub-01_task-rest_eeg.set"},
    {"onset": "10.0", "duration": "10.0", "trial_type": "mind_wandering",
     "condition": "B", "notes": "no report",
     "filename": "sub-01_task-rest_eeg.set"},
    {"onset": "20.0", "duration": "10.0", "trial_type": "focus",
     "condition": "A", "notes": "stable",
     "filename": "sub-01_task-rest_eeg.set"},
    {"onset": "30.0", "duration": "10.0", "trial_type": "mind_wandering",
     "condition": "B", "notes": "n/a",
     "filename": "sub-01_task-rest_eeg.set"},
    {"onset": "40.0", "duration": "10.0", "trial_type": "focus",
     "condition": "A", "notes": "n/a",
     "filename": "sub-02_task-rest_eeg.set"},
    {"onset": "50.0", "duration": "10.0", "trial_type": "mind_wandering",
     "condition": "B", "notes": "distracted",
     "filename": "sub-02_task-rest_eeg.set"},
]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "P16: DS005620 human-reviewed label contract activation packet. "
            "Read-only audit. contract_activation_allowed is always false."
        )
    )
    p.add_argument(
        "--metadata",
        default=None,
        help="Path to local DS005620 metadata file (.csv, .tsv, or .json).",
    )
    p.add_argument(
        "--contract-drafts",
        default=None,
        dest="contract_drafts",
        help=(
            "Path to P14.1 contract_drafts.json. "
            "Used as inactive hints only; does not activate any contract."
        ),
    )
    p.add_argument(
        "--out",
        default="outputs/btc_icft/ds005620_contract_activation",
        help="Output directory.",
    )
    p.add_argument(
        "--mock-fixture",
        action="store_true",
        default=False,
        help="Use deterministic mock metadata (no real data required).",
    )

    a = p.parse_args(argv)

    # Load metadata
    if a.mock_fixture:
        metadata_rows = _MOCK_METADATA_ROWS
        print("[p16] Using mock fixture metadata.", file=sys.stderr)
    elif a.metadata is not None:
        try:
            metadata_rows = load_metadata_rows(a.metadata)
        except FileNotFoundError as exc:
            print(f"[p16] ERROR: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"[p16] ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"[p16] Loaded {len(metadata_rows)} rows from {a.metadata}.", file=sys.stderr)
    else:
        print(f"[p16] ERROR: {_NO_METADATA_MSG}", file=sys.stderr)
        return 1

    # Load contract drafts if provided
    contract_drafts = None
    if a.contract_drafts is not None:
        try:
            contract_drafts = load_contract_drafts(a.contract_drafts)
            print(
                f"[p16] Loaded contract drafts from {a.contract_drafts} "
                "(used as inactive hints only).",
                file=sys.stderr,
            )
        except FileNotFoundError as exc:
            print(f"[p16] ERROR: {exc}", file=sys.stderr)
            return 1

    # Prepare activation result
    result = prepare_ds005620_activation_proposal(metadata_rows, contract_drafts)

    # Write outputs
    try:
        paths = write_ds005620_activation_outputs(result, a.out)
    except ValueError as exc:
        print(f"[p16] FAILED: {exc}", file=sys.stderr)
        return 1

    # Summary
    proposal = result.activation_proposal
    print(f"\n[p16] DS005620 contract activation packet complete.", file=sys.stderr)
    print(f"  n_metadata_rows: {result.n_metadata_rows}", file=sys.stderr)
    print(f"  metadata_file_exists: {result.metadata_file_exists}", file=sys.stderr)
    print(
        f"  candidate_label_columns: {proposal.get('candidate_label_columns', [])}",
        file=sys.stderr,
    )
    print(f"  positive_values: [] (not declared)", file=sys.stderr)
    print(f"  negative_values: [] (not declared)", file=sys.stderr)
    print(f"  contract_activation_allowed: False (always)", file=sys.stderr)
    print(f"  activation_blockers: {len(proposal.get('activation_blockers', []))}", file=sys.stderr)

    if result.warnings:
        print(f"  warnings:", file=sys.stderr)
        for w in result.warnings:
            print(f"    - {w}", file=sys.stderr)

    print(f"\n  Outputs written to: {a.out}", file=sys.stderr)
    for key, path in paths.items():
        print(f"    {key}: {path}", file=sys.stderr)

    print(
        "\n  NOTE: Real contract activation requires a separate human-reviewed PR "
        "with declared explicit_label_column, positive_values, negative_values, "
        "label_scope, and join_keys.",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
