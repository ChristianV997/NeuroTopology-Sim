#!/usr/bin/env python
"""Process-memory benchmark: RSS + tracemalloc for streaming and PITNN kernels.

Complements PR #211's tracemalloc-only benchmark by adding *process-level* RSS
telemetry (via :mod:`tools.streaming.memory_telemetry`) so peak-memory claims can
be cross-checked against total process memory, not just Python-tracked bytes.

It measures two workloads across configurable sizes:

1. **Streaming** -- bounded chunked processing (``tools.streaming.bounded``) vs a
   full-materialization baseline, across multiple chunk sizes and
   channel/sample sizes. Deterministic checksums verify numerical equivalence.
2. **PITNN kernel** -- ``sim.pitnn.kernels_fast.heun_step`` over a fixed number
   of steps, measured on the optional Numba path and the NumPy fallback when
   each is available (selected via the module's ``NUMBA_AVAILABLE`` flag at
   run time; the kernel source is never modified).

Output is JSON-safe (no NaN/Infinity; unavailable metrics are ``null``).

Scientific-integrity note: fixtures are synthetic and deterministic and are
performance evidence only -- never scientific evidence. No topology or
Bayes-factor semantics are computed here.

Usage
-----
    python scripts/benchmark_process_memory.py \
        --samples-list 50000 200000 --channels-list 16 32 \
        --chunk-sizes 2048 16384 --window 1024 --repeats 3
    python scripts/benchmark_process_memory.py --json   # machine-readable
"""
from __future__ import annotations

import argparse
from typing import Callable, Dict, List, Optional

import numpy as np

import sim.pitnn.kernels_fast as kf
from tools.streaming.bounded import bounded_stream
from tools.streaming.memory_telemetry import TelemetryRecord, dumps, measure_workload


# --------------------------------------------------------------------------- #
# Deterministic fixtures & workloads
# --------------------------------------------------------------------------- #
def make_signal(n_samples: int, n_channels: int, seed: int = 0) -> np.ndarray:
    """Deterministic ``(n_samples, n_channels)`` float64 fixture."""
    if n_samples < 1 or n_channels < 1:
        raise ValueError("n_samples and n_channels must be >= 1")
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples, dtype=np.float64)[:, None]
    freqs = (1.0 + np.arange(n_channels, dtype=np.float64))[None, :]
    return (np.sin(2.0 * np.pi * freqs * t / max(n_samples, 1))
            + 0.1 * rng.standard_normal((n_samples, n_channels))).astype(np.float64)


def _transform(chunk: np.ndarray, out: np.ndarray) -> np.ndarray:
    np.multiply(chunk, 2.0, out=out)
    out += 1.0
    return out


def bounded_checksum(signal: np.ndarray, chunk_size: int) -> float:
    """Bounded streaming workload returning a deterministic checksum."""
    result = bounded_stream(signal, chunk_size, transform=_transform,
                            store_history=False, check_finite=True)
    return float(result.checksum)


def full_materialization_checksum(signal: np.ndarray) -> float:
    """Full-materialization baseline returning the same checksum semantics."""
    transformed = signal * 2.0 + 1.0            # full-size allocation
    return float(transformed.sum())


def kernel_checksum(n_spins: int, n_steps: int, seed: int = 0) -> float:
    """Advance heun_step ``n_steps`` times; deterministic checksum of final state."""
    rng = np.random.default_rng(seed)
    spins = rng.standard_normal((n_spins, 3))
    spins /= np.linalg.norm(spins, axis=1, keepdims=True)
    ws = kf.LLGWorkspace.create(n_spins)
    noise = np.zeros((n_spins, 3))
    for _ in range(n_steps):
        spins = kf.heun_step(spins, noise, noise, dt=1e-3, exchange=0.8, dmi=0.15,
                             damping=0.05, ciss_torque=0.02, workspace=ws)
    return float(spins.sum())


# --------------------------------------------------------------------------- #
# Runners
# --------------------------------------------------------------------------- #
def _rel_err(a: float, b: float) -> float:
    denom = max(abs(a), abs(b), 1e-300)
    return abs(a - b) / denom


def run_streaming_configs(samples_list: List[int], channels_list: List[int],
                          chunk_sizes: List[int], repeats: int, seed: int,
                          tolerance: float) -> Dict[str, object]:
    records: List[dict] = []
    comparisons: List[dict] = []
    for samples in samples_list:
        for channels in channels_list:
            signal = make_signal(samples, channels, seed)
            dims = {"samples": samples, "channels": channels}

            full_rec = measure_workload(
                lambda s=signal: full_materialization_checksum(s),
                label="streaming_full", repetitions=repeats,
                backend="numpy", input_dims=dims, chunk_size=None,
            )
            records.append(full_rec.to_dict())

            for chunk in chunk_sizes:
                bnd_rec = measure_workload(
                    lambda s=signal, c=chunk: bounded_checksum(s, c),
                    label="streaming_bounded", repetitions=repeats,
                    backend="numpy", input_dims=dims, chunk_size=chunk,
                )
                records.append(bnd_rec.to_dict())
                rel = _rel_err(full_rec.checksum, bnd_rec.checksum)
                tm_full = full_rec.tracemalloc_peak_bytes
                tm_bnd = bnd_rec.tracemalloc_peak_bytes
                comparisons.append({
                    "samples": samples, "channels": channels, "chunk_size": chunk,
                    "checksum_rel_err": rel,
                    "equivalent_within_tolerance": bool(rel <= tolerance),
                    "tracemalloc_peak_full": tm_full,
                    "tracemalloc_peak_bounded": tm_bnd,
                    "tracemalloc_bounded_lower": (
                        None if tm_full is None or tm_bnd is None else bool(tm_bnd < tm_full)
                    ),
                })
    return {"records": records, "comparisons": comparisons}


def run_kernel_configs(n_spins: int, n_steps: int, repeats: int, seed: int,
                       tolerance: float) -> Dict[str, object]:
    """Measure heun_step on each available backend; verify determinism per backend.

    The NumPy fallback and the optional Numba path can differ numerically (the
    Numba kernel uses fastmath), so we assert determinism *within* a backend, not
    equality across backends.
    """
    records: List[dict] = []
    backends: List[str] = ["numpy"]
    if kf.NUMBA_AVAILABLE:
        backends.append("numba")

    original = kf.NUMBA_AVAILABLE
    dims = {"n_spins": n_spins, "n_steps": n_steps}
    per_backend_checksums: Dict[str, float] = {}
    try:
        for backend in backends:
            kf.NUMBA_AVAILABLE = (backend == "numba")
            rec = measure_workload(
                lambda: kernel_checksum(n_spins, n_steps, seed),
                label="pitnn_heun_step", repetitions=repeats,
                backend=backend, input_dims=dims, chunk_size=None,
            )
            records.append(rec.to_dict())
            per_backend_checksums[backend] = rec.checksum
    finally:
        kf.NUMBA_AVAILABLE = original

    return {
        "records": records,
        "backends_measured": backends,
        "per_backend_checksums": per_backend_checksums,
    }


def run_all(samples_list: List[int], channels_list: List[int], chunk_sizes: List[int],
            repeats: int, seed: int, tolerance: float,
            kernel_spins: int, kernel_steps: int) -> Dict[str, object]:
    streaming = run_streaming_configs(samples_list, channels_list, chunk_sizes,
                                      repeats, seed, tolerance)
    kernel = run_kernel_configs(kernel_spins, kernel_steps, repeats, seed, tolerance)
    all_equiv = all(c["equivalent_within_tolerance"] for c in streaming["comparisons"])
    return {
        "config": {
            "samples_list": samples_list, "channels_list": channels_list,
            "chunk_sizes": chunk_sizes, "repeats": repeats,
            "seed": seed, "tolerance": tolerance,
            "kernel_spins": kernel_spins, "kernel_steps": kernel_steps,
            "numba_available": bool(kf.NUMBA_AVAILABLE),
        },
        "streaming": streaming,
        "kernel": kernel,
        "streaming_all_equivalent": bool(all_equiv),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_text(report: Dict[str, object]) -> None:
    cfg = report["config"]
    print(f"numba_available={cfg['numba_available']} repeats={cfg['repeats']} seed={cfg['seed']}")
    print("streaming records:")
    for rec in report["streaming"]["records"]:  # type: ignore[index]
        rss = rec["rss_delta_bytes"]
        rss_s = "n/a" if rss is None else f"{rss/1e6:+.2f}MB"
        peak = rec["peak_rss_bytes"]
        peak_s = "n/a" if peak is None else f"{peak/1e6:.1f}MB"
        print(f"  {rec['label']:18s} dims={rec['input_dims']} chunk={rec['chunk_size']} "
              f"best={rec['wall_best_s']*1e3:8.3f}ms tm_peak={rec['tracemalloc_peak_bytes']/1e6:7.3f}MB "
              f"rss_delta={rss_s} peak_rss={peak_s}")
    print("streaming equivalence:")
    for c in report["streaming"]["comparisons"]:  # type: ignore[index]
        print(f"  s={c['samples']} c={c['channels']} chunk={c['chunk_size']}: "
              f"rel_err={c['checksum_rel_err']:.2e} equiv={c['equivalent_within_tolerance']} "
              f"tm_bounded_lower={c['tracemalloc_bounded_lower']}")
    print("kernel records:")
    for rec in report["kernel"]["records"]:  # type: ignore[index]
        print(f"  backend={rec['backend']:6s} dims={rec['input_dims']} "
              f"best={rec['wall_best_s']*1e3:8.3f}ms cpu={rec['cpu_time_s']} "
              f"tm_peak={rec['tracemalloc_peak_bytes']/1e6:7.3f}MB checksum={rec['checksum']:.6f}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples-list", type=int, nargs="+", default=[50000, 200000])
    ap.add_argument("--channels-list", type=int, nargs="+", default=[16, 32])
    ap.add_argument("--chunk-sizes", type=int, nargs="+", default=[2048, 16384])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tolerance", type=float, default=1e-9)
    ap.add_argument("--kernel-spins", type=int, default=64)
    ap.add_argument("--kernel-steps", type=int, default=200)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    report = run_all(args.samples_list, args.channels_list, args.chunk_sizes,
                     args.repeats, args.seed, args.tolerance,
                     args.kernel_spins, args.kernel_steps)

    if args.json:
        print(dumps(report))
    else:
        _print_text(report)
    return 0 if report["streaming_all_equivalent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
