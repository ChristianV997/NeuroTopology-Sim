#!/usr/bin/env python3
"""Download ds005620 raw EEG for pilot subjects from OpenNeuro S3 (unsigned access)."""
from pathlib import Path
import json
from typing import Optional
import sys

def get_s3_pilot_subjects() -> dict[str, list[str]]:
    """Map pilot subjects to their task/acq combinations to download."""
    return {
        "sub-1010": ["task-awake_acq-EC", "task-sedated_acq-EC"],
        "sub-1016": ["task-awake_acq-EC", "task-sedated_acq-EC"],
        "sub-1017": ["task-awake_acq-EC", "task-sedated_acq-EC"],
    }

def download_pilot_eeg(output_dir: str | Path = "data/ds005620",
                       dry_run: bool = False) -> dict:
    """
    Download ds005620 pilot subjects from OpenNeuro S3.

    PITNN will process these into macro signals for validation.
    Returns: dict with download status and file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Pilot subjects to download
    pilots = get_s3_pilot_subjects()

    # S3 endpoint for ds005620 (unsigned access)
    s3_bucket = "s3://openneuro.org/ds005620"

    status = {
        "subjects_requested": list(pilots.keys()),
        "s3_bucket": s3_bucket,
        "dry_run": dry_run,
        "downloaded": [],
        "failed": [],
        "notes": "ds005620 propofol anesthesia EEG (21 subjects, 56-channel EEGLAB format)"
    }

    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
    except ImportError:
        status["error"] = "boto3 not installed; install with: pip install boto3"
        return status

    # S3 unsigned access (no credentials needed for public datasets)
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED),
                      region_name='us-west-2')

    downloaded_files = {}
    for subject, tasks in pilots.items():
        subject_dir = output_dir / subject / "eeg"
        subject_dir.mkdir(parents=True, exist_ok=True)

        for task_desc in tasks:
            # Construct S3 key
            filename = f"{subject}_{task_desc}_eeg"
            for ext in [".vhdr", ".vmrk", ".eeg"]:  # EEGLAB format trio
                s3_key = f"sub-sample/ses-01/eeg/{filename}{ext}"  # Adjust path as needed
                local_path = subject_dir / f"{filename}{ext}"

                if not dry_run:
                    try:
                        print(f"Downloading s3://{s3_bucket}/{s3_key}...")
                        s3.download_file(s3_bucket.replace("s3://", ""), s3_key,
                                        str(local_path))
                        downloaded_files[str(local_path)] = s3_key
                        status["downloaded"].append(str(local_path))
                    except Exception as e:
                        status["failed"].append({
                            "file": s3_key,
                            "error": str(e)
                        })
                else:
                    status["downloaded"].append(f"[DRY RUN] {s3_key}")

    status["files"] = downloaded_files
    return status

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Download ds005620 pilot EEG from OpenNeuro S3"
    )
    parser.add_argument("--output-dir", default="data/ds005620",
                       help="Where to save downloaded EEG files")
    parser.add_argument("--dry-run", action="store_true",
                       help="Don't actually download, just show what would be downloaded")
    args = parser.parse_args()

    result = download_pilot_eeg(output_dir=args.output_dir, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
