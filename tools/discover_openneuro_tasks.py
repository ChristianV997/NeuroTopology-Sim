#!/usr/bin/env python3
"""Structurally discover the real BIDS task labels of an OpenNeuro EEG dataset.

Lists the distinct `task-<label>` entities that physically exist in a dataset (by
scanning object keys under its first few subjects on the OpenNeuro public S3
bucket), so a human authoring a `dataset_onboarding_registry.json` entry can see
the real task labels instead of guessing them.

This is STRUCTURAL discovery only. It deliberately does NOT propose a
task->state mapping: assigning semantic state/condition labels is a human
decision (the repo's no_label_inference policy). The output is a scaffold with
every discovered task mapped to a `TODO_state` placeholder that a human must
fill in before the dataset can be streamed.

Usage:
    python tools/discover_openneuro_tasks.py ds004148
    python tools/discover_openneuro_tasks.py ds004148 --max-subjects 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.streaming import base_runner

_BUCKET = "openneuro.org"


def discover(dataset_id: str, max_subjects: int = 3) -> list[str]:
    return base_runner.list_s3_task_labels(_BUCKET, dataset_id, max_subjects=max_subjects)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dataset_id", help="OpenNeuro accession, e.g. ds004148")
    p.add_argument("--max-subjects", type=int, default=3,
                   help="How many subjects to scan for task entities (default 3; BIDS tasks are shared across subjects)")
    a = p.parse_args()

    tasks = discover(a.dataset_id, max_subjects=a.max_subjects)
    if not tasks:
        print(f"No task-* entities found for {a.dataset_id!r} "
              f"(is it an EEG dataset? are subjects named sub-*?).", file=sys.stderr)
        return 1

    # A registry scaffold with placeholders a human must replace -- never guess states.
    scaffold = {
        "dataset_id": a.dataset_id,
        "title": f"OpenNeuro {a.dataset_id}",
        "task_to_state": {t.lower(): "TODO_state" for t in tasks},
        "contrasts": [
            {"name": "TODO_contrast_name", "label_field": "state_label",
             "class0": "TODO_state_a", "class1": "TODO_state_b"}
        ],
        "default_task": "TODO_contrast_name",
        "window_seconds": 4.0,
        "max_windows_per_file": 5,
        "max_channels": 8,
        "report_input_heading": "## Input",
        "report_input_source": f"- Source: real BIDS EEG signal ({a.dataset_id}).",
        "report_extra_window_lines": [],
        "report_extra_next_step_lines": [],
        "format_note": "TODO: fill in format/montage/sampling notes",
    }
    print(f"# Discovered {len(tasks)} real BIDS task label(s) in {a.dataset_id} "
          f"(scanned {a.max_subjects} subject(s)):", file=sys.stderr)
    print(f"#   {tasks}", file=sys.stderr)
    print("# Registry scaffold below -- REPLACE every TODO_* (esp. task_to_state values) "
          "with human-authored state labels before streaming:", file=sys.stderr)
    print(json.dumps(scaffold, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
