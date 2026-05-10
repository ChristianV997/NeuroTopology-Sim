from __future__ import annotations
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from sciencer_d.btc_icft.datasets.ds005620_bids import inspect_ds005620_bids_root, write_bids_inspection_outputs


def _build_mock() -> str:
    tmp = tempfile.mkdtemp(prefix="ds005620_bids_")
    root = Path(tmp)
    (root / "participants.tsv").write_text("participant_id\nsub-001\nsub-002\n", encoding="utf-8")
    p1 = root / "sub-001" / "ses-01" / "eeg"
    p1.mkdir(parents=True, exist_ok=True)
    (p1 / "sub-001_ses-01_task-awake_run-01_eeg.edf").write_text("", encoding="utf-8")
    p2 = root / "sub-002" / "ses-01" / "eeg"
    p2.mkdir(parents=True, exist_ok=True)
    (p2 / "sub-002_ses-01_task-sedated_run-01_eeg.edf").write_text("", encoding="utf-8")
    return tmp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bids-root")
    ap.add_argument("--out", default="outputs/btc_icft/ds005620/bids_inspection")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    if not args.bids_root and not args.mock:
        print("Provide --bids-root to a local DS005620-style root or use --mock.", file=sys.stderr)
        return 2
    tmp = None
    bids_root = args.bids_root
    if args.mock:
        tmp = _build_mock()
        bids_root = bids_root or tmp
    if not bids_root or not Path(bids_root).exists():
        print(f"BIDS root not found: {bids_root}. Provide an existing local path.", file=sys.stderr)
        return 2
    result = inspect_ds005620_bids_root(bids_root)
    paths = write_bids_inspection_outputs(result, args.out)
    print("Wrote outputs:")
    for k, v in paths.items():
        print(f"- {k}: {v}")
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
