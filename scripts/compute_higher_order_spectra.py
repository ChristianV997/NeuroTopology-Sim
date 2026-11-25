"""CLI for bounded higher-order spectral summaries.

Input files are local ``.npy``, ``.npz`` or numeric CSV arrays.  The command
does not download data or import repository signal loaders.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

# Allow direct ``python scripts/compute_higher_order_spectra.py`` execution
# without relying on the caller's working directory or PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from topo_monitor.higher_order.spectra import compute_higher_order_spectra, report_to_json
from topo_monitor.higher_order.spectral_types import SCHEMA_VERSION, SegmentConfiguration


def _load_signal(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npy":
        return np.load(path, allow_pickle=False)
    if path.suffix.lower() == ".npz":
        with np.load(path, allow_pickle=False) as archive:
            if not archive.files:
                raise ValueError("NPZ input contains no arrays")
            key = "signal" if "signal" in archive.files else sorted(archive.files)[0]
            return archive[key]
    return np.loadtxt(path, delimiter=",")


def _error_payload(source: str, error: Exception) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": {"source": source, "sampling_rate_hz": None, "synthetic": None, "checksum_sha256": None},
        "bispectrum": None,
        "trispectrum": None,
        "modulogram": None,
        "comparisons": {},
        "surrogates": [],
        "diagnostics": {},
        "warnings": [],
        "errors": [f"{type(error).__name__}: {error}"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sampling-rate", type=float, required=True, dest="sampling_rate_hz")
    parser.add_argument("--source", default=None)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--segment-length", type=int, default=256)
    parser.add_argument("--n-fft", type=int, default=256)
    parser.add_argument("--overlap", type=float, default=0.5)
    parser.add_argument("--taper", choices=("boxcar", "hann", "hamming", "blackman"), default="hann")
    parser.add_argument("--detrend", choices=("none", "constant", "linear"), default="constant")
    parser.add_argument("--frequency-bins", type=int, default=32)
    parser.add_argument("--trispectrum-slices", type=int, default=4)
    parser.add_argument("--max-channels", type=int, default=8)
    parser.add_argument("--memory-budget-mb", type=float, default=64.0)
    parser.add_argument("--surrogate-method", action="append", default=[])
    parser.add_argument("--surrogate-count", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.source or str(args.input)
    try:
        signal = _load_signal(args.input)
        config = SegmentConfiguration(
            segment_length=args.segment_length,
            n_fft=args.n_fft,
            overlap=args.overlap,
            taper=args.taper,
            detrend=args.detrend,
            frequency_bins=args.frequency_bins,
            trispectrum_slices=args.trispectrum_slices,
            max_channels=args.max_channels,
            memory_budget_bytes=int(args.memory_budget_mb * 1024 * 1024),
        )
        report = compute_higher_order_spectra(
            signal,
            args.sampling_rate_hz,
            config=config,
            source=source,
            synthetic=args.synthetic,
            surrogate_methods=args.surrogate_method,
            surrogate_count=args.surrogate_count,
            seed=args.seed,
        )
        payload = report_to_json(report)
    except Exception as error:  # CLI contract: errors are finite JSON, not tracebacks.
        payload = json.dumps(_error_payload(source, error), allow_nan=False, sort_keys=True, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
