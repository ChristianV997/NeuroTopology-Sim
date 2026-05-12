from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from sciencer_d.btc_icft.labels.ds005620_contract_activation import (
    load_contract_drafts,
    load_metadata_rows,
    prepare_ds005620_activation_proposal,
    write_ds005620_activation_outputs,
)


def _mock_metadata_rows() -> list[dict]:
    rows: list[dict] = []
    binary = ["explicit_yes", "explicit_no", "explicit_yes", "explicit_no"]
    multiclass = ["condition_a", "condition_b", "condition_c", "condition_a"]
    for i in range(4):
        rows.append(
            {
                "dataset_id": "DS005620",
                "row_id": f"row_{i}",
                "source_file": f"/mock/sub-001_task-rest_run-{i+1:02d}_eeg.edf",
                "window_id": f"win_{i}",
                "window_start_s": str(float(i)),
                "window_end_s": str(float(i) + 1.0),
                "sample_start": str(i * 100),
                "sample_end": str(i * 100 + 100),
                "candidate_state": binary[i],
                "condition_group": multiclass[i],
                "notes": f"free text notes for review row {i}",
                "file_path": f"/mock/metadata/events_row_{i}.tsv",
            }
        )
    return rows


def _write_mock_metadata_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["dataset_id"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def run(
    metadata: str | None = None,
    contract_drafts: str | None = None,
    out_dir: str = "outputs/btc_icft/ds005620_contract_activation",
    mock_fixture: bool = False,
) -> int:
    if not metadata and not mock_fixture:
        print(
            "DS005620 local metadata is required. Provide --metadata or use --mock-fixture.",
            file=sys.stderr,
        )
        return 1

    metadata_rows: list[dict]
    if mock_fixture:
        metadata_rows = _mock_metadata_rows()
        mock_path = Path(out_dir) / ".mock_fixture" / "local_ds005620_metadata.csv"
        _write_mock_metadata_csv(mock_path, metadata_rows)
    else:
        try:
            metadata_rows = load_metadata_rows(str(metadata))
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1

    drafts_payload = None
    if contract_drafts:
        try:
            drafts_payload = load_contract_drafts(contract_drafts)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1

    result = prepare_ds005620_activation_proposal(metadata_rows, drafts_payload)
    outputs = write_ds005620_activation_outputs(result, out_dir)

    print(json.dumps({
        "dataset_id": result.dataset_id,
        "contract_activation_allowed": result.activation_proposal.get("contract_activation_allowed", False),
        "n_metadata_rows": result.n_metadata_rows,
        "outputs": outputs,
    }, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare DS005620 human-reviewed contract activation packet."
    )
    parser.add_argument("--metadata", default=None, help="Local DS005620 metadata file (.csv/.tsv/.json).")
    parser.add_argument("--contract-drafts", default=None, help="Optional contract drafts JSON path.")
    parser.add_argument(
        "--out",
        default="outputs/btc_icft/ds005620_contract_activation",
        help="Output directory.",
    )
    parser.add_argument(
        "--mock-fixture",
        action="store_true",
        help="Use deterministic DS005620-like fixture metadata.",
    )
    args = parser.parse_args()
    return run(
        metadata=args.metadata,
        contract_drafts=args.contract_drafts,
        out_dir=args.out,
        mock_fixture=args.mock_fixture,
    )


if __name__ == "__main__":
    raise SystemExit(main())
