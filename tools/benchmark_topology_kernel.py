#!/usr/bin/env python3
"""Measure the CPU-only Level T topology kernel on deterministic signal windows.

This benchmark intentionally excludes downloads, MNE header parsing, and disk
reads. It isolates the inner calculation used once actual samples are already
available, making performance regressions actionable without requiring a
dataset download or changing any scientific configuration.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from sciencer_d.btc_icft.level_t.eeg_signal_topology import compute_topology_from_channels


def run_benchmark(channels: int, samples: int, iterations: int, seed: int) -> dict:
    if channels < 3:
        raise ValueError("channels must be at least 3 for topology triangles")
    if samples < 2:
        raise ValueError("samples must be at least 2")
    if iterations < 1:
        raise ValueError("iterations must be positive")

    signal = np.random.default_rng(seed).standard_normal((channels, samples)).tolist()
    # Warm imports and interpreter specialization outside the timed section.
    compute_topology_from_channels(signal)
    started = perf_counter()
    for _ in range(iterations):
        compute_topology_from_channels(signal)
    elapsed = perf_counter() - started
    return {
        "kernel": "compute_topology_from_channels",
        "channels": channels,
        "samples": samples,
        "iterations": iterations,
        "seed": seed,
        "elapsed_seconds": elapsed,
        "milliseconds_per_window": elapsed * 1000 / iterations,
        "windows_per_second": iterations / elapsed if elapsed else None,
        "scope": "cpu_only_deterministic_synthetic_signal",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channels", type=int, default=8)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--seed", type=int, default=620)
    parser.add_argument("--out", type=Path, help="Optional JSON destination")
    args = parser.parse_args()
    result = run_benchmark(args.channels, args.samples, args.iterations, args.seed)
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
