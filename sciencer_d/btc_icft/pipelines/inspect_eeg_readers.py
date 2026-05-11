"""CLI: Inspect EEG reader adapter capabilities and file readability.

Usage:
    python -m sciencer_d.btc_icft.pipelines.inspect_eeg_readers \\
        --paths file1.edf file2.csv \\
        --out outputs/btc_icft/ds005620/eeg_readers

    python -m sciencer_d.btc_icft.pipelines.inspect_eeg_readers \\
        --mock-fixture \\
        --out outputs/btc_icft/ds005620/eeg_readers
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sciencer_d.btc_icft.io import (
    inspect_eeg_files,
    write_eeg_reader_outputs,
)


def _generate_mock_fixture_files(tmp_dir: Path) -> list[str]:
    """Generate mock fixture files for testing.

    Args:
        tmp_dir: Temporary directory to write fixture files.

    Returns:
        List of paths to generated fixture files.
    """
    tmp_dir.mkdir(parents=True, exist_ok=True)

    fixture_files = []

    # Create a CSV fixture
    csv_file = tmp_dir / "mock_sensor_1.csv"
    with open(csv_file, "w") as f:
        f.write("# channels: 8\n")
        f.write("# sample_rate: 250.0\n")
        f.write("time,ch1,ch2,ch3,ch4,ch5,ch6,ch7,ch8\n")
        for i in range(100):
            f.write(f"{i*0.004},")
            f.write(",".join([f"{0.1*i*j}" for j in range(1, 9)]))
            f.write("\n")
    fixture_files.append(str(csv_file))

    # Create a TXT fixture
    txt_file = tmp_dir / "mock_sensor_2.txt"
    with open(txt_file, "w") as f:
        f.write("# channels: 4\n")
        f.write("# sample_rate: 128.0\n")
        for i in range(50):
            f.write(" ".join([f"{0.05*i*j}" for j in range(1, 5)]))
            f.write("\n")
    fixture_files.append(str(txt_file))

    return fixture_files


def run(paths: list[str] | None = None, out_dir: str = "outputs/btc_icft/ds005620/eeg_readers", mock_fixture: bool = False) -> int:
    """Run EEG reader adapter inspection.

    Args:
        paths: List of file paths to inspect. If None and not mock_fixture, error.
        out_dir: Output directory for reports.
        mock_fixture: If True, generate and inspect mock fixture files.

    Returns:
        0 on success, 1 on error.
    """
    files_to_inspect = []

    if mock_fixture:
        tmp_dir = Path(out_dir) / ".mock_fixtures"
        files_to_inspect = _generate_mock_fixture_files(tmp_dir)
        print(f"Generated {len(files_to_inspect)} mock fixture files.")
    elif paths:
        files_to_inspect = paths
    else:
        print("Error: either --paths or --mock-fixture must be provided.")
        return 1

    if not files_to_inspect:
        print("Error: no files to inspect.")
        return 1

    print(f"Inspecting {len(files_to_inspect)} files...")
    readability_rows = inspect_eeg_files(files_to_inspect)

    n_readable = sum(1 for r in readability_rows if r.readable)
    print(f"Readable files: {n_readable}/{len(readability_rows)}")

    outputs = write_eeg_reader_outputs(readability_rows, out_dir)
    print(f"Wrote {len(outputs)} output files:")
    for name, path in outputs.items():
        print(f"  - {name}: {path}")

    return 0


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Inspect EEG reader adapter capabilities and file readability."
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        help="File paths to inspect",
    )
    parser.add_argument(
        "--out",
        default="outputs/btc_icft/ds005620/eeg_readers",
        help="Output directory",
    )
    parser.add_argument(
        "--mock-fixture",
        action="store_true",
        help="Generate and inspect mock fixture files",
    )

    args = parser.parse_args()
    return run(paths=args.paths, out_dir=args.out, mock_fixture=args.mock_fixture)


if __name__ == "__main__":
    sys.exit(main())
