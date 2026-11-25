"""CLI: Probe EEG fixture files for signal-block extraction capability.

Usage:
    python -m sciencer_d.btc_icft.pipelines.probe_eeg_signal_blocks \\
        --paths file1.csv file2.txt \\
        --out outputs/btc_icft/ds005620/signal_blocks

    python -m sciencer_d.btc_icft.pipelines.probe_eeg_signal_blocks \\
        --mock-fixture \\
        --out outputs/btc_icft/ds005620/signal_blocks
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sciencer_d.btc_icft.io.eeg_signal_blocks import (
    probe_signal_paths,
    write_signal_probe_outputs,
)


def _generate_mock_fixture_files(tmp_dir: Path) -> list[str]:
    """Generate mock fixture files for offline testing.

    Args:
        tmp_dir: Directory to write fixture files.

    Returns:
        List of paths to generated fixture files.
    """
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fixture_files = []

    # CSV fixture: 8 channels, 250 Hz, 50 rows
    csv_file = tmp_dir / "mock_signal_8ch.csv"
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("# channels: 8\n")
        f.write("# sample_rate: 250.0\n")
        f.write("time,ch1,ch2,ch3,ch4,ch5,ch6,ch7,ch8\n")
        for i in range(50):
            vals = [f"{0.1 * i * j:.4f}" for j in range(1, 9)]
            f.write(f"{i * 0.004:.4f}," + ",".join(vals) + "\n")
    fixture_files.append(str(csv_file))

    # TXT fixture: 4 channels, 100 Hz, 200 rows (no time column)
    txt_file = tmp_dir / "mock_signal_4ch.txt"
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write("# channels: 4\n")
        f.write("# sample_rate: 100.0\n")
        for i in range(200):
            vals = [f"{0.05 * i * j:.4f}" for j in range(1, 5)]
            f.write(" ".join(vals) + "\n")
    fixture_files.append(str(txt_file))

    # TSV fixture: 2 channels, 128 Hz, 30 rows
    tsv_file = tmp_dir / "mock_signal_2ch.tsv"
    with open(tsv_file, "w", encoding="utf-8") as f:
        f.write("# channels: 2\n")
        f.write("# sample_rate: 128.0\n")
        f.write("# channel_names: left,right\n")
        for i in range(30):
            f.write(f"{0.2 * i:.4f}\t{-0.2 * i:.4f}\n")
    fixture_files.append(str(tsv_file))

    return fixture_files


def run(
    paths: list[str] | None = None,
    out_dir: str = "outputs/btc_icft/ds005620/signal_blocks",
    sample_rate_hz: float | None = None,
    window_seconds: float = 10.0,
    max_windows_per_file: int = 3,
    mock_fixture: bool = False,
) -> int:
    """Run EEG signal-block probe.

    Args:
        paths: List of file paths to probe. Required if not mock_fixture.
        out_dir: Output directory for artifacts.
        sample_rate_hz: Explicit sample rate when a file lacks ``# sample_rate``.
            ``None`` refuses silent 100 Hz defaults.
        window_seconds: Window duration in seconds.
        max_windows_per_file: Max windows per file (0 = no limit).
        mock_fixture: If True, generate and probe mock fixture files.

    Returns:
        0 on success, 1 on error.
    """
    files_to_probe: list[str] = []

    if mock_fixture:
        tmp_dir = Path(out_dir) / ".mock_fixtures"
        files_to_probe = _generate_mock_fixture_files(tmp_dir)
        print(f"Generated {len(files_to_probe)} mock fixture files.")
    elif paths:
        files_to_probe = paths
    else:
        print("Error: either --paths or --mock-fixture must be provided.")
        return 1

    if not files_to_probe:
        print("Error: no files to probe.")
        return 1

    max_w: int | None = max_windows_per_file if max_windows_per_file > 0 else None

    print(f"Probing {len(files_to_probe)} files...")
    result = probe_signal_paths(
        files_to_probe,
        sample_rate_hz=sample_rate_hz,
        window_seconds=window_seconds,
        max_windows_per_file=max_w,
    )

    print(f"Readable files: {result.n_readable_files}/{result.n_files}")
    print(f"Total windows: {result.n_windows}")
    if result.n_skipped_files:
        print(f"Skipped files: {result.n_skipped_files}")

    outputs = write_signal_probe_outputs(result, out_dir)
    print(f"Wrote {len(outputs)} output artifacts:")
    for name, path in outputs.items():
        print(f"  - {name}: {path}")

    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Probe EEG fixture files for signal-block extraction capability."
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        help="File paths to probe",
    )
    parser.add_argument(
        "--out",
        default="outputs/btc_icft/ds005620/signal_blocks",
        help="Output directory",
    )
    parser.add_argument(
        "--sample-rate-hz",
        type=float,
        default=None,
        help=(
            "Explicit sample rate in Hz when file header lacks # sample_rate. "
            "Omitted by default (no silent 100 Hz imputation)."
        ),
    )
    parser.add_argument(
        "--window-seconds",
        type=float,
        default=10.0,
        help="Window duration in seconds",
    )
    parser.add_argument(
        "--max-windows-per-file",
        type=int,
        default=3,
        help="Max windows per file (0 = no limit)",
    )
    parser.add_argument(
        "--mock-fixture",
        action="store_true",
        help="Generate and probe mock fixture files",
    )

    args = parser.parse_args()
    return run(
        paths=args.paths,
        out_dir=args.out,
        sample_rate_hz=args.sample_rate_hz,
        window_seconds=args.window_seconds,
        max_windows_per_file=args.max_windows_per_file,
        mock_fixture=args.mock_fixture,
    )


if __name__ == "__main__":
    sys.exit(main())
