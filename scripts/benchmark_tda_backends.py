#!/usr/bin/env python3
"""Benchmark persistent-homology backend adapters across available engines.

Compares computational runtime, memory telemetry, and feature counts across
available TDA backends on synthetic benchmark fixtures.

Scientific Notice:
Runtime differences benchmark computational efficiency of specific algorithmic
implementations and hardware bindings. Runtime or memory performance does NOT
constitute scientific superiority, mathematical proof, or biological validation.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from topo_monitor.tda_adapters import (
    BackendCapabilityStatus,
    InputKind,
    TDAConfig,
    compute_persistence,
    get_all_capabilities,
    list_available_backends,
)


def generate_benchmark_fixture(fixture_type: str, n_points: int, dim: int = 3, seed: int = 42) -> np.ndarray:
    """Generate reproducible synthetic point clouds for computational benchmarking."""
    rng = np.random.default_rng(seed)
    if fixture_type == "circle":
        theta = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
        pts = np.zeros((n_points, max(2, dim)))
        pts[:, 0] = np.cos(theta)
        pts[:, 1] = np.sin(theta)
        return pts
    elif fixture_type == "sphere":
        # Points on unit 2-sphere embedded in R^dim
        pts = rng.normal(0, 1, (n_points, max(3, dim)))
        norms = np.linalg.norm(pts[:, :3], axis=1, keepdims=True)
        pts[:, :3] /= np.maximum(norms, 1e-12)
        return pts
    elif fixture_type == "uniform":
        return rng.uniform(-1.0, 1.0, (n_points, dim))
    else:
        raise ValueError(f"Unknown fixture type '{fixture_type}'. Supported: 'circle', 'sphere', 'uniform'")


def run_single_benchmark(
    backend_name: str,
    data: np.ndarray,
    iterations: int = 3,
    max_edge: float | None = None,
) -> dict[str, Any]:
    """Benchmark a single backend over multiple iterations."""
    runtimes: list[float] = []
    peak_mems: list[int] = []
    b0_counts: list[int] = []
    b1_counts: list[int] = []
    checksums: list[str] = []

    config = TDAConfig(
        max_edge_length=max_edge,
        max_dimension=1,
        compute_landscape=True,
        track_memory=True,
    )

    # Warm-up run
    try:
        compute_persistence(data, input_kind=InputKind.POINT_CLOUD, backend=backend_name, config=config)
    except Exception as exc:
        return {
            "backend": backend_name,
            "status": "execution_failed",
            "error": str(exc),
        }

    for _ in range(iterations):
        tracemalloc.start()
        t0 = time.perf_counter()
        try:
            res = compute_persistence(
                data,
                input_kind=InputKind.POINT_CLOUD,
                backend=backend_name,
                config=config,
            )
            t1 = time.perf_counter()
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        runtimes.append(t1 - t0)
        peak_mems.append(int(peak))
        b0_counts.append(len(res.beta_0_intervals))
        b1_counts.append(len(res.beta_1_intervals))
        checksums.append(res.deterministic_checksum)

    deterministic = (len(set(checksums)) == 1)

    return {
        "backend": backend_name,
        "status": "success",
        "iterations": iterations,
        "runtime_mean_seconds": float(np.mean(runtimes)),
        "runtime_std_seconds": float(np.std(runtimes)),
        "peak_memory_mean_bytes": float(np.mean(peak_mems)),
        "beta_0_count": b0_counts[0] if b0_counts else 0,
        "beta_1_count": b1_counts[0] if b1_counts else 0,
        "deterministic": deterministic,
        "checksum": checksums[0] if checksums else None,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persistent homology backend adapter benchmark utility.",
    )
    parser.add_argument("--points", type=int, default=32, help="Number of points in benchmark fixture.")
    parser.add_argument("--dim", type=int, default=3, help="Spatial dimension of point cloud.")
    parser.add_argument("--fixture", type=str, choices=["circle", "sphere", "uniform"], default="circle")
    parser.add_argument("--iterations", type=int, default=3, help="Number of benchmark iterations per backend.")
    parser.add_argument("--max-edge", type=float, default=None, help="Filtration max edge length.")
    parser.add_argument("--output-json", type=str, default=None, help="Path to write JSON benchmark summary.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print("=" * 72)
    print(" NeuroTopology-Sim: Persistent Homology Backend Benchmark")
    print("=" * 72)
    print("Scientific Notice:")
    print("  Runtime differences benchmark algorithmic efficiency on synthetic geometries.")
    print("  Runtime alone does NOT imply scientific superiority or theoretical validity.")
    print("-" * 72)

    all_caps = get_all_capabilities()
    available = list_available_backends()

    print(f"Fixture: {args.fixture} (N={args.points}, D={args.dim})")
    print(f"Registered backends: {list(all_caps.keys())}")
    print(f"Available backends:  {available}")
    print("-" * 72)

    data = generate_benchmark_fixture(args.fixture, args.points, args.dim)

    results: list[dict[str, Any]] = []

    for name, cap in all_caps.items():
        if cap.status != BackendCapabilityStatus.AVAILABLE:
            print(f"[{cap.status.value.upper():12s}] {name:20s}: Skipped ({cap.description})")
            results.append({
                "backend": name,
                "status": cap.status.value,
                "reason": cap.description,
            })
            continue

        print(f"Benchmarking {name} ({args.iterations} iterations)...", end="", flush=True)
        res = run_single_benchmark(name, data, iterations=args.iterations, max_edge=args.max_edge)
        results.append(res)

        if res["status"] == "success":
            print(
                f" Mean: {res['runtime_mean_seconds'] * 1000.0:.2f} ms | "
                f"Peak Mem: {res['peak_memory_mean_bytes'] / 1024.0:.1f} KB | "
                f"H0: {res['beta_0_count']} | H1: {res['beta_1_count']} | "
                f"Deterministic: {res['deterministic']}"
            )
        else:
            print(f" Failed: {res.get('error', 'unknown error')}")

    print("=" * 72)

    if args.output_json:
        payload = {
            "fixture": args.fixture,
            "num_points": args.points,
            "dimension": args.dim,
            "iterations": args.iterations,
            "scientific_semantics": {
                "metric": "Vietoris-Rips persistent homology (H0, H1)",
                "charge_separation": "Graph beta-1 cycle rank is strictly separated from spatial topological winding charge.",
                "disclaimer": "Benchmark measures computational latency only; no scientific superiority claimed.",
            },
            "results": results,
        }
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"Benchmark results saved to: {args.output_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
