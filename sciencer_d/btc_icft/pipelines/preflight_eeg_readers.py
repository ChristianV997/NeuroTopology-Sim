from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sciencer_d.btc_icft.io.eeg_reader_preflight import (
    build_reader_preflight_report,
    check_optional_reader_capabilities,
    scan_eeg_dataset_files,
    write_reader_preflight_outputs,
)


def _write_mock_files(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in ["signal.csv", "events.tsv", "notes.txt", "subject01.edf", "subject01.set", "subject01.fif", "subject01.hea", "subject01.mat", "unsupported.xyz"]:
        (root / name).write_text("1,2,3\n4,5,6\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-id", default="DS005620")
    p.add_argument("--root")
    p.add_argument("--out", default="outputs/btc_icft/eeg_reader_preflight/DS005620")
    p.add_argument("--max-files", type=int)
    p.add_argument("--mock-fixture", action="store_true")
    args = p.parse_args()

    root = args.root
    if args.mock_fixture:
        root = str(Path(args.out) / ".mock_fixture")
        _write_mock_files(Path(root))
    elif not root:
        print("Local EEG dataset root is required. Provide --root or use --mock-fixture.")
        return 1

    rows = scan_eeg_dataset_files(root=root, dataset_id=args.dataset_id, max_files=args.max_files)
    caps = check_optional_reader_capabilities()
    result = build_reader_preflight_report(args.dataset_id, rows, caps)
    write_reader_preflight_outputs(result, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
