#!/usr/bin/env python3
"""Convert ds005620 EEG windows to PITNN CSV input format."""
from pathlib import Path
import json
import csv
from typing import Optional
import sys

def convert_ds005620_to_pitnn(
    output_dir: str | Path = "data/ds005620_pitnn_input",
    subjects: Optional[list[str]] = None,
) -> dict:
    """
    Convert ds005620 existing topology features to PITNN CSV format.

    Reads Level-T topology feature CSVs (q_net, f_dress, defect_density, etc.)
    from stream_rescaled/ outputs and formats as time series for PITNN
    empirical falsification pipeline.

    Args:
        output_dir: Where to write PITNN input CSVs
        subjects: Specific subjects to convert; None uses pilot 3

    Returns:
        dict with conversion status, file paths, and stats
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if subjects is None:
        subjects = ["sub-1010", "sub-1016", "sub-1017"]

    status = {
        "subjects": subjects,
        "output_dir": str(output_dir),
        "converted": [],
        "failed": [],
        "stats": {},
        "note": "ds005620 propofol anesthesia state classification via topological metrics"
    }

    # Path to existing topology feature CSVs from streaming pipeline
    stream_dir = Path("outputs/btc_icft/ds005620/stream_rescaled")

    if not stream_dir.exists():
        status["error"] = f"Streaming output directory not found: {stream_dir}"
        return status

    for subject in subjects:
        # Read Level-T topology features
        feature_csv = stream_dir / f"{subject}_features_t.csv"
        if not feature_csv.exists():
            status["failed"].append({
                "subject": subject,
                "reason": f"Feature CSV not found: {feature_csv}"
            })
            continue

        windows_by_state = {"awake": [], "sedated": []}
        window_count = 0

        try:
            import csv as csvmodule
            with open(feature_csv, 'r') as f:
                reader = csvmodule.DictReader(f)
                for row in reader:
                    task_label = row.get("task_label", "unknown").lower()
                    window_id = row.get("window_id", "")
                    start_s = float(row.get("window_start_s", 0))
                    end_s = float(row.get("window_end_s", 4))

                    # Map task label to state (propofol anesthesia study)
                    if "awake" in task_label or "rest" in task_label:
                        state = "awake"
                    elif "sedated" in task_label or "sed" in task_label or "propofol" in task_label:
                        state = "sedated"
                    else:
                        state = "awake"  # default to baseline

                    # Extract topology metrics (q_net, f_dress are primary PITNN targets)
                    windows_by_state[state].append({
                        "window_id": window_id,
                        "start_s": start_s,
                        "end_s": end_s,
                        "q_net": float(row.get("q_net", 0)),
                        "q_abs": float(row.get("q_abs", 0)),
                        "f_dress": float(row.get("f_dress", 0)),
                        "defect_density": float(row.get("defect_density", 0)),
                    })
                    window_count += 1

        except Exception as e:
            status["failed"].append({
                "subject": subject,
                "reason": f"Error reading feature CSV: {str(e)}"
            })
            continue

        # Write PITNN input CSV (window-level topology features)
        # Each row represents a 10-second window with state label and topology metrics
        output_csv = output_dir / f"{subject}_pitnn_input.csv"
        try:
            with open(output_csv, 'w', newline='') as f:
                writer = csvmodule.DictWriter(
                    f,
                    fieldnames=["subject_id", "state", "window_id", "duration_s", "q_net", "q_abs", "f_dress", "defect_density"]
                )
                writer.writeheader()

                for state, windows in windows_by_state.items():
                    for window in windows:
                        writer.writerow({
                            "subject_id": subject,
                            "state": state,
                            "window_id": window["window_id"],
                            "duration_s": window["end_s"] - window["start_s"],
                            "q_net": window["q_net"],
                            "q_abs": window["q_abs"],
                            "f_dress": window["f_dress"],
                            "defect_density": window["defect_density"],
                        })

            status["converted"].append({
                "subject": subject,
                "output_path": str(output_csv),
                "windows_awake": len(windows_by_state["awake"]),
                "windows_sedated": len(windows_by_state["sedated"]),
                "total_windows": window_count
            })
            status["stats"][subject] = {
                "awake": len(windows_by_state["awake"]),
                "sedated": len(windows_by_state["sedated"]),
                "total": window_count
            }

        except Exception as e:
            status["failed"].append({
                "subject": subject,
                "reason": f"Error writing output CSV: {str(e)}"
            })

    return status

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert ds005620 windows to PITNN CSV format"
    )
    parser.add_argument("--output-dir", default="data/ds005620_pitnn_input",
                       help="Where to write PITNN input CSVs")
    parser.add_argument("--subjects", nargs="+",
                       default=["sub-1010", "sub-1016", "sub-1017"],
                       help="Subjects to convert (default: pilot 3)")
    args = parser.parse_args()

    result = convert_ds005620_to_pitnn(
        output_dir=args.output_dir,
        subjects=args.subjects
    )
    print(json.dumps(result, indent=2))

    # Exit with error code if any conversions failed
    if result["failed"]:
        sys.exit(1)
