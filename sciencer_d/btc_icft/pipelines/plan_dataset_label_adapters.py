"""CLI: P14 — Dataset label adapter readiness planning scaffold.

Inspects local metadata files and reports whether each dataset has enough
explicit metadata to activate a P12 label contract.

Usage:
    python -m sciencer_d.btc_icft.pipelines.plan_dataset_label_adapters \\
        --data-root data \\
        --out outputs/btc_icft/label_adapter_readiness

    python -m sciencer_d.btc_icft.pipelines.plan_dataset_label_adapters \\
        --mock-fixture \\
        --out outputs/btc_icft/label_adapter_readiness

    python -m sciencer_d.btc_icft.pipelines.plan_dataset_label_adapters \\
        --list-datasets
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from sciencer_d.btc_icft.labels.dataset_label_adapter import (
    assess_all_datasets,
    assess_dataset_adapter_readiness,
    get_label_adapter_specs,
    write_adapter_readiness_outputs,
)

_MOCK_METADATA_COLS = [
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
    "trial_type",
]


def _write_mock_metadata(path: Path, dataset_id: str, n_rows: int = 4) -> None:
    """Write deterministic mock events metadata with 2 trial types."""
    path.parent.mkdir(parents=True, exist_ok=True)
    values = ["condition_a", "condition_b"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_MOCK_METADATA_COLS)
        writer.writeheader()
        for i in range(n_rows):
            writer.writerow({
                "dataset_id": dataset_id,
                "row_id": f"mock__win_{i}",
                "source_file": f"/mock/signal_{i}.csv",
                "window_id": f"win-{i:03d}",
                "window_start_s": str(float(i)),
                "window_end_s": str(float(i) + 1.0),
                "sample_start": str(i * 100),
                "sample_end": str(i * 100 + 100),
                "trial_type": values[i % 2],
            })


def run(
    data_root: str = "data",
    dataset_id: str | None = None,
    out_dir: str = "outputs/btc_icft/label_adapter_readiness",
    mock_fixture: bool = False,
) -> int:
    """Run P14 dataset label adapter readiness assessment.

    Args:
        data_root: Root directory containing per-dataset subdirectories.
        dataset_id: If given, assess only this dataset; otherwise all.
        out_dir: Output directory for readiness artifacts.
        mock_fixture: Generate mock metadata files for demonstration.

    Returns:
        0 on success, 1 on error.
    """
    specs = get_label_adapter_specs()

    if mock_fixture:
        mock_base = Path(out_dir) / ".mock_metadata"
        for ds_id in specs:
            mock_ds_dir = mock_base / ds_id
            mock_path = mock_ds_dir / "mock_events.csv"
            _write_mock_metadata(mock_path, ds_id)
        data_root = str(mock_base)
        print(f"Generated mock metadata fixtures under: {data_root}")

    if dataset_id is not None:
        if dataset_id not in specs:
            print(f"Error: Unknown dataset_id {dataset_id!r}. "
                  f"Known: {sorted(specs)}", file=sys.stderr)
            return 1
        try:
            result = assess_dataset_adapter_readiness(
                dataset_id,
                str(Path(data_root) / dataset_id),
            )
        except Exception as exc:
            print(f"Error assessing {dataset_id}: {exc}", file=sys.stderr)
            return 1

        # Wrap single-dataset result in summary structure
        from dataclasses import asdict
        from sciencer_d.btc_icft.labels.dataset_label_adapter import (
            LabelAdapterReadinessSummary,
            _SAFE_CLAIM,
        )
        d = asdict(result)
        summary = LabelAdapterReadinessSummary(
            n_datasets=1,
            n_ready_to_activate=1 if result.readiness_status == "ready_to_activate" else 0,
            n_needs_explicit_mapping=1 if result.readiness_status == "needs_explicit_mapping" else 0,
            n_missing_metadata=1 if result.readiness_status in (
                "metadata_file_not_found", "metadata_empty_or_unreadable"
            ) else 0,
            n_planning_required=0,
            per_dataset={dataset_id: d},
            safe_claim=_SAFE_CLAIM,
            forbidden_claims=[
                "No consciousness proof.", "No self or soul claim.",
                "No liberation or enlightenment claim.", "No afterlife claim.",
                "No ontology proof.", "No label inference.", "No target fabrication.",
            ],
        )
    else:
        try:
            summary = assess_all_datasets(data_root, dataset_id_subdirs=True)
        except Exception as exc:
            print(f"Error during readiness assessment: {exc}", file=sys.stderr)
            return 1

    outputs = write_adapter_readiness_outputs(summary, out_dir)
    print(f"Wrote {len(outputs)} output artifacts:")
    for name, path in outputs.items():
        print(f"  - {name}: {path}")

    print()
    print("Dataset label adapter readiness summary:")
    for ds_id, d in summary.per_dataset.items():
        print(f"  {ds_id}: {d['readiness_status']}")
    print()
    print(f"n_ready_to_activate: {summary.n_ready_to_activate}")
    print(f"n_needs_explicit_mapping: {summary.n_needs_explicit_mapping}")
    print(f"n_missing_metadata: {summary.n_missing_metadata}")
    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="P14 — Dataset label adapter readiness planning scaffold."
    )
    parser.add_argument(
        "--data-root",
        default="data",
        help="Root directory containing per-dataset subdirectories.",
    )
    parser.add_argument(
        "--dataset-id",
        default=None,
        help="Assess only this dataset ID. Default: assess all known datasets.",
    )
    parser.add_argument(
        "--out",
        default="outputs/btc_icft/label_adapter_readiness",
        help="Output directory for readiness artifacts.",
    )
    parser.add_argument(
        "--mock-fixture",
        action="store_true",
        help="Generate mock metadata files for demonstration.",
    )
    parser.add_argument(
        "--list-datasets",
        action="store_true",
        help="List known dataset IDs and exit.",
    )
    args = parser.parse_args()

    if args.list_datasets:
        specs = get_label_adapter_specs()
        for ds_id, spec in specs.items():
            print(f"  {ds_id} — {spec.title}")
        return 0

    return run(
        data_root=args.data_root,
        dataset_id=args.dataset_id,
        out_dir=args.out,
        mock_fixture=args.mock_fixture,
    )


if __name__ == "__main__":
    sys.exit(main())
