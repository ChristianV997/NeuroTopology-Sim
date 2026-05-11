"""CLI: EEG signal-level M+T residual benchmark.

Usage:
    python -m sciencer_d.btc_icft.pipelines.run_eeg_signal_mt \\
        --dataset-id DS005620 \\
        --m-features outputs/btc_icft/eeg_level_m/DS005620/features_m_signal.csv \\
        --t-features outputs/btc_icft/eeg_level_t/DS005620/features_t_signal.csv \\
        --out outputs/btc_icft/eeg_signal_mt/DS005620

    python -m sciencer_d.btc_icft.pipelines.run_eeg_signal_mt \\
        --mock-fixture \\
        --out outputs/btc_icft/eeg_signal_mt/DS005620
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from sciencer_d.btc_icft.evaluation.eeg_signal_residual import (
    load_level_m_signal_features,
    load_level_t_signal_features,
    join_signal_m_t_rows,
    evaluate_signal_mt_residual,
    write_signal_mt_outputs,
)

_MOCK_ERROR_MSG = (
    "Level M and Level T signal feature tables are required. "
    "Run run_eeg_level_m_signal and run_eeg_level_t_signal first or use --mock-fixture."
)


def _write_mock_m_csv(path: Path, dataset_id: str, n_rows: int = 5) -> None:
    """Write deterministic mock features_m_signal.csv (no y targets)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "dataset_id", "row_id", "source_file", "window_id",
        "window_start_s", "window_end_s", "sample_start", "sample_end",
        "n_channels", "n_samples", "sample_rate_hz",
        "spectral_power_proxy", "entropy_proxy", "lzc_proxy",
        "artifact_score", "feature_status", "warnings",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for i in range(n_rows):
            writer.writerow({
                "dataset_id": dataset_id,
                "row_id": f"mock__win_{i}",
                "source_file": f"/mock/signal_{i}.csv",
                "window_id": f"win-{i:03d}",
                "window_start_s": str(i * 1.0),
                "window_end_s": str(i * 1.0 + 1.0),
                "sample_start": str(i * 100),
                "sample_end": str(i * 100 + 100),
                "n_channels": "4",
                "n_samples": "100",
                "sample_rate_hz": "100.0",
                "spectral_power_proxy": f"{0.3 + i * 0.05:.4f}",
                "entropy_proxy": f"{0.5 + i * 0.03:.4f}",
                "lzc_proxy": f"{0.4 + i * 0.04:.4f}",
                "artifact_score": f"{0.1 + i * 0.02:.4f}",
                "feature_status": "ok",
                "warnings": "",
            })


def _write_mock_t_csv(path: Path, dataset_id: str, n_rows: int = 5) -> None:
    """Write deterministic mock features_t_signal.csv."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "dataset_id", "row_id", "source_file", "window_id",
        "window_start_s", "window_end_s", "sample_start", "sample_end",
        "n_channels", "n_samples", "sample_rate_hz",
        "q_net", "q_abs", "f_dress", "defect_density",
        "n_triangles", "n_valid_triangles", "topology_quality",
        "topology_status", "warnings",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for i in range(n_rows):
            writer.writerow({
                "dataset_id": dataset_id,
                "row_id": f"mock__win_{i}",
                "source_file": f"/mock/signal_{i}.csv",
                "window_id": f"win-{i:03d}",
                "window_start_s": str(i * 1.0),
                "window_end_s": str(i * 1.0 + 1.0),
                "sample_start": str(i * 100),
                "sample_end": str(i * 100 + 100),
                "n_channels": "4",
                "n_samples": "100",
                "sample_rate_hz": "100.0",
                "q_net": f"{0.1 + i * 0.01:.4f}",
                "q_abs": f"{0.2 + i * 0.02:.4f}",
                "f_dress": f"{0.05 + i * 0.01:.4f}",
                "defect_density": f"{0.15 + i * 0.01:.4f}",
                "n_triangles": "4",
                "n_valid_triangles": str(3 + i % 2),
                "topology_quality": f"{0.7 + i * 0.02:.4f}",
                "topology_status": "ok",
                "warnings": "",
            })


def run(
    dataset_id: str = "DS005620",
    m_features: str = "outputs/btc_icft/eeg_level_m/DS005620/features_m_signal.csv",
    t_features: str = "outputs/btc_icft/eeg_level_t/DS005620/features_t_signal.csv",
    out_dir: str = "outputs/btc_icft/eeg_signal_mt/DS005620",
    mock_fixture: bool = False,
) -> int:
    """Run signal-level M+T residual benchmark.

    Args:
        dataset_id: Dataset identifier.
        m_features: Path to features_m_signal.csv.
        t_features: Path to features_t_signal.csv.
        out_dir: Output directory.
        mock_fixture: Generate deterministic mock inputs when True.

    Returns:
        0 on success, 1 on error.
    """
    if mock_fixture:
        mock_dir = Path(out_dir) / ".mock_features"
        m_path = mock_dir / "features_m_signal.csv"
        t_path = mock_dir / "features_t_signal.csv"
        _write_mock_m_csv(m_path, dataset_id)
        _write_mock_t_csv(t_path, dataset_id)
        m_features = str(m_path)
        t_features = str(t_path)
        print(f"Generated mock M features: {m_features}")
        print(f"Generated mock T features: {t_features}")

    try:
        m_rows = load_level_m_signal_features(m_features)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    try:
        t_rows = load_level_t_signal_features(t_features)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"Loaded {len(m_rows)} M rows, {len(t_rows)} T rows.")

    try:
        joined_rows, join_warnings = join_signal_m_t_rows(m_rows, t_rows)
    except ValueError as e:
        print(f"Join error: {e}")
        return 1

    if join_warnings:
        for w in join_warnings[:5]:
            print(f"  Warning: {w}")

    print(f"Joined {len(joined_rows)} rows.")

    result = evaluate_signal_mt_residual(
        joined_rows, dataset_id, m_rows=m_rows, t_rows=t_rows,
        join_warnings=join_warnings,
    )

    outputs = write_signal_mt_outputs(result, out_dir, joined_rows=joined_rows)
    print(f"Wrote {len(outputs)} output artifacts:")
    for name, path in outputs.items():
        print(f"  - {name}: {path}")

    print(f"Promoted: {result.promoted} | {result.promotion_reason}")
    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="EEG signal-level M+T residual benchmark."
    )
    parser.add_argument("--dataset-id", default="DS005620")
    parser.add_argument(
        "--m-features",
        default="outputs/btc_icft/eeg_level_m/DS005620/features_m_signal.csv",
    )
    parser.add_argument(
        "--t-features",
        default="outputs/btc_icft/eeg_level_t/DS005620/features_t_signal.csv",
    )
    parser.add_argument(
        "--out",
        default="outputs/btc_icft/eeg_signal_mt/DS005620",
    )
    parser.add_argument("--mock-fixture", action="store_true")

    args = parser.parse_args()
    return run(
        dataset_id=args.dataset_id,
        m_features=args.m_features,
        t_features=args.t_features,
        out_dir=args.out,
        mock_fixture=args.mock_fixture,
    )


if __name__ == "__main__":
    sys.exit(main())
