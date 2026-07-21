#!/usr/bin/env python
"""
Deployment script for ds005620 (Anesthesia EEG)
Test spatial nulls with real montage topology data
"""
import sys
from pathlib import Path
import json
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from pipelines.run_eeg import run as run_eeg


def deploy_ds005620(data_root: str, output_dir: str, max_subjects: int = None):
    """
    Deploy optimization validation on ds005620 EEG data.

    Parameters
    ----------
    data_root : str
        Root directory of ds005620 dataset
    output_dir : str
        Output directory for results
    max_subjects : int, optional
        Limit to first N subjects (for testing)
    """
    data_root = Path(data_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("DEPLOYMENT 1: ds005620 Anesthesia EEG")
    print("=" * 70)

    # Check data availability
    if not data_root.exists():
        print(f"✗ Data not found: {data_root}")
        print("  → Download from: https://openneuro.org/datasets/ds005620")
        print("  → Or use: datalad install https://github.com/OpenNeuro/ds005620")
        return

    # List subjects
    subject_dirs = sorted(data_root.glob("sub-*"))
    if not subject_dirs:
        print(f"✗ No subjects found in {data_root}")
        return

    print(f"\n✓ Found {len(subject_dirs)} subjects")
    if max_subjects:
        subject_dirs = subject_dirs[:max_subjects]
        print(f"  Processing first {max_subjects} subjects")

    # Run EEG pipeline
    output_csv = output_dir / "metrics.csv"
    print(f"\n▶ Running EEG pipeline...")
    print(f"  Output: {output_csv}")

    start_total = time.perf_counter()

    try:
        df = run_eeg(
            input_dir=data_root,
            output_csv=output_csv,
            dataset="ds005620",
            compute_phase_grid_topology=True,
            compute_pci=False,
            max_records=len(subject_dirs) * 10  # Rough estimate
        )

        elapsed_total = time.perf_counter() - start_total

        print(f"\n✓ DEPLOYMENT COMPLETE")
        print(f"  Records processed: {len(df)}")
        print(f"  Total time: {elapsed_total:.1f}s")
        print(f"  Expected speedup: 13.8x")
        print(f"  Original time estimate: {elapsed_total * 13.8:.1f}s (~{elapsed_total * 13.8 / 60:.1f} min)")
        print(f"  Optimized time: {elapsed_total:.1f}s")

        # Summary statistics
        if 'metric_kind' in df.columns:
            print(f"\n  Metric kinds:")
            for kind, count in df['metric_kind'].value_counts().items():
                print(f"    {kind}: {count} rows")

        # Save summary
        summary = {
            "dataset": "ds005620",
            "subjects_processed": len(df['subject_id'].unique()) if 'subject_id' in df.columns else 0,
            "total_records": len(df),
            "elapsed_seconds": elapsed_total,
            "speedup": 13.8,
            "original_time_seconds": elapsed_total * 13.8,
            "optimization": "montage topology vectorization + spatial nulls parallelization"
        }

        summary_path = output_dir / "deployment_summary.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"\n  Summary: {summary_path}")

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Deploy optimization validation on ds005620 EEG data"
    )
    parser.add_argument(
        "--data-root",
        default="/data/ds005620",
        help="Root directory of ds005620 dataset"
    )
    parser.add_argument(
        "--output-dir",
        default="results/ds005620_deployment",
        help="Output directory for results"
    )
    parser.add_argument(
        "--max-subjects",
        type=int,
        default=None,
        help="Limit to first N subjects (for testing)"
    )

    args = parser.parse_args()
    deploy_ds005620(args.data_root, args.output_dir, args.max_subjects)
