"""CLI: EEG Level T signal topology extraction.

Usage:
    python -m sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal \\
        --dataset-id DS005620 \\
        --signal-blocks outputs/btc_icft/ds005620/signal_blocks \\
        --out outputs/btc_icft/eeg_level_t/DS005620

    python -m sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal \\
        --mock-fixture \\
        --out outputs/btc_icft/eeg_level_t/DS005620
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from sciencer_d.btc_icft.level_t.eeg_signal_topology import (
    load_signal_window_inventory,
    compute_signal_topology_rows,
    build_topology_quality_report,
    build_signal_topology_artifact_report,
    build_level_t_signal_omega_event,
    write_level_t_signal_outputs,
    EEGLevelTSignalTopologyResult,
    _SAFE_CLAIM,
)
from sciencer_d.btc_icft.pipelines.probe_eeg_signal_blocks import (
    run as run_signal_probe,
)


def _run_mock_signal_blocks(out_dir: str) -> str:
    """Generate mock signal block outputs for offline testing.

    Args:
        out_dir: Output directory root.

    Returns:
        Path to the signal blocks directory containing window_inventory.csv.
    """
    signal_blocks_dir = str(Path(out_dir) / ".mock_signal_blocks")
    rc = run_signal_probe(
        paths=None,
        out_dir=signal_blocks_dir,
        mock_fixture=True,
        window_seconds=0.5,
        max_windows_per_file=3,
    )
    if rc != 0:
        raise RuntimeError(f"Mock signal block probe failed with code {rc}")
    return signal_blocks_dir


def run(
    dataset_id: str = "DS005620",
    signal_blocks: str = "outputs/btc_icft/ds005620/signal_blocks",
    out_dir: str = "outputs/btc_icft/eeg_level_t/DS005620",
    mock_fixture: bool = False,
) -> int:
    """Run Level T signal topology extraction.

    Args:
        dataset_id: Dataset identifier.
        signal_blocks: Path to signal blocks output directory (contains window_inventory.csv).
        out_dir: Output directory for artifacts.
        mock_fixture: If True, generate and use mock fixture signal blocks.

    Returns:
        0 on success, 1 on error.
    """
    if mock_fixture:
        print("Generating mock signal block fixtures...")
        try:
            signal_blocks = _run_mock_signal_blocks(out_dir)
        except Exception as e:
            print(f"Error generating mock fixtures: {e}")
            return 1
        print(f"Using mock signal blocks from: {signal_blocks}")

    try:
        windows = load_signal_window_inventory(signal_blocks)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"Loaded {len(windows)} windows from signal block inventory.")

    topology_rows, skipped_windows = compute_signal_topology_rows(dataset_id, windows)
    print(f"Computed {len(topology_rows)} topology rows, {len(skipped_windows)} skipped.")

    tqr = build_topology_quality_report(topology_rows, skipped_windows)
    ar = build_signal_topology_artifact_report(topology_rows)

    result = EEGLevelTSignalTopologyResult(
        dataset_id=dataset_id,
        n_windows=len(windows),
        n_topology_rows=len(topology_rows),
        n_skipped_windows=len(skipped_windows),
        topology_rows=[_row_to_dict(r) for r in topology_rows],
        skipped_windows=skipped_windows,
        topology_quality_report=tqr,
        artifact_report=ar,
        omega_event={},
        safe_claim=_SAFE_CLAIM,
        forbidden_claims=[],
        warnings=[],
    )
    result.omega_event = build_level_t_signal_omega_event(result)

    outputs = write_level_t_signal_outputs(result, out_dir)
    print(f"Wrote {len(outputs)} output artifacts:")
    for name, path in outputs.items():
        print(f"  - {name}: {path}")

    q = tqr.get("mean_topology_quality", 0.0)
    passed = tqr.get("quality_passed", False)
    print(f"Mean topology quality: {q:.4f} | quality_passed: {passed}")

    return 0


def _row_to_dict(row) -> dict:
    from dataclasses import asdict
    return asdict(row)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="EEG Level T signal topology extraction."
    )
    parser.add_argument(
        "--dataset-id",
        default="DS005620",
        help="Dataset identifier",
    )
    parser.add_argument(
        "--signal-blocks",
        default="outputs/btc_icft/ds005620/signal_blocks",
        help="Path to signal-block outputs directory (must contain window_inventory.csv)",
    )
    parser.add_argument(
        "--out",
        default="outputs/btc_icft/eeg_level_t/DS005620",
        help="Output directory for Level T signal topology artifacts",
    )
    parser.add_argument(
        "--mock-fixture",
        action="store_true",
        help="Generate mock fixture signal blocks and run topology extraction",
    )

    args = parser.parse_args()
    return run(
        dataset_id=args.dataset_id,
        signal_blocks=args.signal_blocks,
        out_dir=args.out,
        mock_fixture=args.mock_fixture,
    )


if __name__ == "__main__":
    sys.exit(main())
