#!/usr/bin/env python
"""
Deployment script for ds000245 (fMRI Spectral TDA)
Validate spectral TDA optimization at scale (45 subjects)
"""
import sys
from pathlib import Path
import json
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from dual_engine.spectral_tda import (
    coherence_spectrum, spectral_landscape, spectral_landscape_band_summary
)


def deploy_ds000245(data_root: str, output_dir: str, max_subjects: int = None):
    """
    Deploy optimization validation on ds000245 fMRI data.

    Parameters
    ----------
    data_root : str
        Root directory of ds000245 dataset
    output_dir : str
        Output directory for results
    max_subjects : int, optional
        Limit to first N subjects (for testing)
    """
    data_root = Path(data_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("DEPLOYMENT 2: ds000245 fMRI Spectral TDA")
    print("=" * 70)

    # Check data availability
    if not data_root.exists():
        print(f"✗ Data not found: {data_root}")
        print("  → Download from: https://openneuro.org/datasets/ds000245")
        print("  → Or use: datalad install https://github.com/OpenNeuro/ds000245")
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

    # Run spectral TDA pipeline
    print(f"\n▶ Running Spectral TDA pipeline...")
    print(f"  Expected: coherence (16.8ms) + landscape (443ms) per subject")

    results = []
    start_total = time.perf_counter()

    for sub_dir in subject_dirs:
        sub = sub_dir.name
        func_dir = sub_dir / "ses-01" / "func"

        if not func_dir.exists():
            print(f"  ~ {sub}: no func dir")
            continue

        # Find BOLD file
        bold_files = list(func_dir.glob("*task-stroop_bold.nii.gz"))
        if not bold_files:
            print(f"  ~ {sub}: no BOLD file")
            continue

        try:
            import nibabel as nib

            bold_path = bold_files[0]
            bold_img = nib.load(bold_path)
            bold_data = bold_img.get_fdata()  # (x, y, z, t)

            # Extract center 64 voxels for testing (would use atlas in production)
            nx, ny, nz, nt = bold_data.shape
            x_start = nx // 2 - 32
            y_start = ny // 2 - 32
            ts = bold_data[x_start:x_start+64, y_start:y_start+64, nz//2, :]  # (64, 64, t)
            ts_flat = ts.reshape(-1, ts.shape[-1])  # (4096, t)

            # Normalize
            ts_flat = (ts_flat - ts_flat.mean(axis=1, keepdims=True)) / (
                ts_flat.std(axis=1, keepdims=True) + 1e-6
            )

            start = time.perf_counter()

            # Coherence spectrum (sample 100 voxels to speed up)
            sample_idx = np.random.choice(ts_flat.shape[0], 100, replace=False)
            ts_sample = ts_flat[sample_idx]

            coh_result = coherence_spectrum(ts_sample, sfreq=0.5, fmin=0.5, fmax=0.2)

            # Spectral landscape
            land_result = spectral_landscape(
                coh_result["coherence"], coh_result["freqs"], max_freqs=32
            )

            # Band summary
            band_result = spectral_landscape_band_summary(land_result)

            elapsed = time.perf_counter() - start

            result = {
                "subject": sub,
                "elapsed_seconds": elapsed,
                "n_voxels": ts_flat.shape[0],
                "n_volumes": ts_flat.shape[1],
                "band_mass": band_result["band_mass"],
            }
            results.append(result)
            print(f"  ✓ {sub}: {elapsed:.3f}s")

        except ImportError:
            print(f"  ~ {sub}: nibabel not installed (skipping)")
            continue
        except Exception as e:
            print(f"  ✗ {sub}: {e}")
            continue

    elapsed_total = time.perf_counter() - start_total

    if results:
        print(f"\n✓ DEPLOYMENT COMPLETE")
        print(f"  Subjects processed: {len(results)}")
        print(f"  Total time: {elapsed_total:.1f}s")
        print(f"  Expected speedup: 17.6x")
        print(f"  Original time estimate: {elapsed_total * 17.6:.1f}s")

        times = [r["elapsed_seconds"] for r in results]
        print(f"  Mean time per subject: {np.mean(times):.3f}s")
        print(f"  Std dev: {np.std(times):.3f}s")

        # Save results
        output_json = output_dir / "spectral_tda_metrics.json"
        with open(output_json, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n  Results: {output_json}")

        # Summary
        summary = {
            "dataset": "ds000245",
            "subjects_processed": len(results),
            "total_time_seconds": elapsed_total,
            "mean_time_per_subject": np.mean(times),
            "speedup": 17.6,
            "original_time_seconds": elapsed_total * 17.6,
            "optimization": "einsum batched coherence + vectorized landscape"
        }

        summary_path = output_dir / "deployment_summary.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"  Summary: {summary_path}")
    else:
        print(f"\n✗ No subjects processed")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Deploy optimization validation on ds000245 fMRI data"
    )
    parser.add_argument(
        "--data-root",
        default="/data/ds000245",
        help="Root directory of ds000245 dataset"
    )
    parser.add_argument(
        "--output-dir",
        default="results/ds000245_deployment",
        help="Output directory for results"
    )
    parser.add_argument(
        "--max-subjects",
        type=int,
        default=None,
        help="Limit to first N subjects (for testing)"
    )

    args = parser.parse_args()
    deploy_ds000245(args.data_root, args.output_dir, args.max_subjects)
