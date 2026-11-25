#!/usr/bin/env python
"""Baseline-vs-optimized benchmark for the bounded streaming pipeline.

Compares a memory-heavy "baseline" streaming pipeline (materialize the whole
transformed signal and retain every per-window result) against the bounded,
buffer-reusing pipeline from :mod:`tools.streaming.bounded`. It reports runtime
telemetry (``time.perf_counter``), transient peak-memory telemetry
(``tracemalloc``), and exact output checksums so numerical equivalence can be
verified.

Scientific-integrity note: the fixtures here are synthetic and deterministic.
Their only purpose is performance measurement -- they are NOT empirical or
scientific evidence, and the pipeline computes plain per-window signal
statistics, not topology/Bayes-factor semantics.

Usage
-----
    python scripts/benchmark_streaming_pipeline.py \
        --channels 32 --samples 200000 --chunk-size 4096 --window 1024 --repeats 5
"""
from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from dataclasses import asdict, dataclass
from typing import Callable

import numpy as np

from tools.streaming.bounded import bounded_stream, iter_windows


# --------------------------------------------------------------------------- #
# Deterministic fixtures
# --------------------------------------------------------------------------- #
def make_fixture(n_samples: int, n_channels: int, seed: int = 0) -> np.ndarray:
    """Return a deterministic ``(n_samples, n_channels)`` float64 signal."""
    if n_samples < 1 or n_channels < 1:
        raise ValueError("n_samples and n_channels must be >= 1")
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples, dtype=np.float64)[:, None]
    freqs = (1.0 + np.arange(n_channels, dtype=np.float64))[None, :]
    base = np.sin(2.0 * np.pi * freqs * t / max(n_samples, 1))
    noise = rng.standard_normal((n_samples, n_channels))
    return (base + 0.1 * noise).astype(np.float64)


def _chunk_transform(chunk: np.ndarray, out: np.ndarray) -> np.ndarray:
    """Deterministic per-sample transform written into a reusable buffer."""
    np.multiply(chunk, 2.0, out=out)
    out += 1.0
    return out


def _window_energy(window: np.ndarray) -> float:
    """Deterministic scalar per window: total per-channel variance (float64)."""
    return float(window.var(axis=0).sum())


# --------------------------------------------------------------------------- #
# Pipelines
# --------------------------------------------------------------------------- #
def baseline_pipeline(signal: np.ndarray, window: int) -> dict:
    """Memory-heavy reference computing the SAME outputs as the optimized path.

    Materializes the whole transformed signal and the full list of per-window
    energies, and computes the same per-channel aggregates (mean/var/min/max)
    that :func:`tools.streaming.bounded.bounded_stream` produces.
    """
    transformed = signal * 2.0 + 1.0                       # full-size allocation
    sample_checksum = float(transformed.sum())
    mean = transformed.mean(axis=0)
    var = transformed.var(axis=0)
    minimum = transformed.min(axis=0)
    maximum = transformed.max(axis=0)
    moments_checksum = float(mean.sum() + var.sum() + minimum.sum() + maximum.sum())
    # Retain every window result (memory grows with number of windows).
    energies = [
        _window_energy(transformed[start:start + window])
        for start in range(0, transformed.shape[0] - window + 1, window)
    ]
    topo_checksum = float(np.sum(energies))
    return {
        "sample_checksum": sample_checksum,
        "moments_checksum": moments_checksum,
        "topo_checksum": topo_checksum,
        "n_windows": len(energies),
    }


def effective_chunk_size(chunk_size: int, window: int) -> int:
    """Round ``chunk_size`` up to a whole multiple of ``window``.

    Aligning chunk boundaries to window boundaries lets the optimized pipeline
    compute per-window energies *inside* each transformed chunk in a single
    streaming pass (no redundant second transform, no full-signal buffer).
    """
    if chunk_size < window:
        return window
    return ((chunk_size + window - 1) // window) * window


def optimized_pipeline(signal: np.ndarray, chunk_size: int, window: int) -> dict:
    """Bounded single-pass pipeline: chunked transform (reused buffer) that also
    accumulates per-window energies from each transformed chunk."""
    eff_chunk = effective_chunk_size(chunk_size, window)
    energies: list[float] = []

    def summarize(_index: int, values: np.ndarray) -> float:
        # ``values`` is the transformed chunk (reused buffer). Chunk boundaries
        # are window-aligned, so its whole windows are exactly the global windows.
        total = 0.0
        m = values.shape[0]
        for start in range(0, m - window + 1, window):
            total += _window_energy(values[start:start + window])
        return total

    result = bounded_stream(
        signal,
        eff_chunk,
        transform=_chunk_transform,
        summarize=summarize,
        store_history=False,
        check_finite=True,
    )
    topo_checksum = float(np.sum(result.summaries)) if result.summaries else 0.0
    moments_checksum = float(result.mean.sum() + result.variance.sum()
                             + result.minimum.sum() + result.maximum.sum())
    n_windows = (signal.shape[0] // window)
    return {
        "sample_checksum": result.checksum,
        "moments_checksum": moments_checksum,
        "topo_checksum": topo_checksum,
        "n_windows": n_windows,
        "effective_chunk_size": eff_chunk,
    }


# --------------------------------------------------------------------------- #
# Measurement
# --------------------------------------------------------------------------- #
@dataclass
class Measurement:
    label: str
    best_seconds: float
    mean_seconds: float
    peak_bytes: int


def _measure(fn: Callable[[], dict], label: str, repeats: int) -> tuple[Measurement, dict]:
    fn()  # warm-up
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        payload = fn()
        times.append(time.perf_counter() - t0)
    tracemalloc.start()
    tracemalloc.reset_peak()
    payload = fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    arr = np.asarray(times)
    return Measurement(label, float(arr.min()), float(arr.mean()), int(peak)), payload


def run_benchmark(channels: int, samples: int, chunk_size: int, window: int,
                  repeats: int, seed: int, tolerance: float) -> dict:
    signal = make_fixture(samples, channels, seed)

    base_m, base_out = _measure(lambda: baseline_pipeline(signal, window), "baseline", repeats)
    opt_m, opt_out = _measure(lambda: optimized_pipeline(signal, chunk_size, window), "optimized", repeats)

    def _rel(a: float, b: float) -> float:
        denom = max(abs(a), abs(b), 1e-300)
        return abs(a - b) / denom

    sample_rel = _rel(base_out["sample_checksum"], opt_out["sample_checksum"])
    moments_rel = _rel(base_out["moments_checksum"], opt_out["moments_checksum"])
    topo_rel = _rel(base_out["topo_checksum"], opt_out["topo_checksum"])
    equivalent = sample_rel <= tolerance and moments_rel <= tolerance and topo_rel <= tolerance

    return {
        "config": {
            "channels": channels, "samples": samples, "chunk_size": chunk_size,
            "window": window, "repeats": repeats, "seed": seed, "tolerance": tolerance,
        },
        "baseline": asdict(base_m),
        "optimized": asdict(opt_m),
        "checksums": {
            "baseline": base_out, "optimized": opt_out,
            "sample_rel_err": sample_rel, "moments_rel_err": moments_rel,
            "topo_rel_err": topo_rel,
            "equivalent_within_tolerance": bool(equivalent),
        },
        "speedup_best": (base_m.best_seconds / opt_m.best_seconds) if opt_m.best_seconds > 0 else float("inf"),
        "peak_memory_ratio": (opt_m.peak_bytes / base_m.peak_bytes) if base_m.peak_bytes > 0 else float("inf"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--channels", type=int, default=32)
    ap.add_argument("--samples", type=int, default=200_000)
    ap.add_argument("--chunk-size", type=int, default=4096)
    ap.add_argument("--window", type=int, default=1024)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tolerance", type=float, default=1e-9)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON only")
    args = ap.parse_args(argv)

    report = run_benchmark(args.channels, args.samples, args.chunk_size,
                           args.window, args.repeats, args.seed, args.tolerance)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["checksums"]["equivalent_within_tolerance"] else 1

    cfg = report["config"]
    print(f"Fixture: samples={cfg['samples']} channels={cfg['channels']} "
          f"chunk={cfg['chunk_size']} window={cfg['window']} repeats={cfg['repeats']} seed={cfg['seed']}")
    for key in ("baseline", "optimized"):
        m = report[key]
        print(f"  {m['label']:9s} best={m['best_seconds']*1e3:8.3f} ms  "
              f"mean={m['mean_seconds']*1e3:8.3f} ms  peak={m['peak_bytes']/1e6:8.3f} MB")
    ck = report["checksums"]
    print(f"  speedup(best)={report['speedup_best']:.2f}x  "
          f"peak_mem_ratio(opt/base)={report['peak_memory_ratio']:.3f}")
    print(f"  sample_rel_err={ck['sample_rel_err']:.2e}  moments_rel_err={ck['moments_rel_err']:.2e}  "
          f"topo_rel_err={ck['topo_rel_err']:.2e}  equivalent={ck['equivalent_within_tolerance']}")
    return 0 if ck["equivalent_within_tolerance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
