#!/usr/bin/env python3
"""CLI utility for reproducible benchmarking of simulation solvers and topological kernels.

Measures:
- Runtime (seconds) via high-precision perf_counter.
- Memory ceiling (MB) via tracemalloc peak memory tracking.
- Numerical residual norms ||L v - lambda v||_2 / ||v||_2.
- Emits RFC 8259 finite JSON telemetry with SHA-256 integrity digests.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import time
import tracemalloc
from typing import Any, Dict, List, Optional, Sequence

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from analysis.serialization import write_canonical_telemetry
from core.topological_filtration import fast_betti_landscape, fast_plv_matrix, pruned_persistence_diagram
from physics.open_quantum import LatticeConfig, LindbladLattice, solve_liouvillian_spectrum


def run_solver_benchmarks(
    n_layers: int = 1,
    solvers: Optional[List[str]] = None,
    tolerance: float = 1e-8,
) -> Dict[str, Any]:
    """Profile selected open-quantum Liouvillian solvers across runtime, memory, and residuals."""
    selected_solvers = solvers or ["exact_dense", "sparse_shift_invert", "matrix_free"]
    config = LatticeConfig(n_protofilaments=13, n_layers=n_layers)
    model = LindbladLattice.from_pbc(config)
    dimension = model.dimension
    superop_size = dimension * dimension

    results: Dict[str, Any] = {
        "lattice": {
            "n_sites": model.n_sites,
            "dimension": dimension,
            "superoperator_size": superop_size,
            "n_layers": n_layers,
        },
        "solvers": {},
    }

    for solver_name in selected_solvers:
        # Skip exact_dense for large dimensions to prevent out-of-memory crashes
        if solver_name == "exact_dense" and dimension > 48:
            results["solvers"][solver_name] = {
                "skipped": True,
                "reason": f"Dimension {dimension} exceeds exact_dense safety cap (48)",
            }
            continue

        tracemalloc.start()
        t0 = time.perf_counter()

        try:
            gap_res = solve_liouvillian_spectrum(
                model=model,
                method=solver_name,
                k=4,
                tolerance_s=tolerance,
            )
            t1 = time.perf_counter()
            _, peak_mem = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            runtime_s = t1 - t0
            peak_mb = peak_mem / (1024.0 * 1024.0)

            results["solvers"][solver_name] = {
                "success": True,
                "runtime_s": float(runtime_s),
                "peak_memory_mb": float(peak_mb),
                "residual_norm": float(gap_res.stationary_residual_s),
                "spectral_gap_s": float(gap_res.gap_s),
                "decoherence_time_s": (
                    float(gap_res.decoherence_time_s)
                    if np.isfinite(gap_res.decoherence_time_s)
                    else None
                ),
                "stationary_eigenvalue_real": float(gap_res.stationary_eigenvalue_s.real),
                "stationary_eigenvalue_imag": float(gap_res.stationary_eigenvalue_s.imag),
                "converged": bool(gap_res.converged),
                "iteration_count": int(gap_res.iteration_count),
            }
        except Exception as exc:
            tracemalloc.stop()
            results["solvers"][solver_name] = {
                "success": False,
                "error": str(exc),
            }

    return results


def run_topological_benchmarks(
    n_channels: int = 32,
    n_samples: int = 1000,
) -> Dict[str, Any]:
    """Profile topological filtration kernels: BLAS-3 PLV and fast Betti landscape."""
    rng = np.random.default_rng(42)
    phases = rng.uniform(-np.pi, np.pi, size=(n_channels, n_samples))

    tracemalloc.start()
    t0 = time.perf_counter()

    plv = fast_plv_matrix(phases)
    t_plv = time.perf_counter()

    dgm = pruned_persistence_diagram(plv, max_dimension=1, min_threshold=0.1)
    t_dgm = time.perf_counter()

    grid = np.linspace(0.1, 0.9, 9, dtype=np.float64)
    landscape = fast_betti_landscape(dgm, grid, k=3)
    t_land = time.perf_counter()

    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "channel_count": n_channels,
        "sample_count": n_samples,
        "plv_runtime_s": float(t_plv - t0),
        "ripser_pruned_runtime_s": float(t_dgm - t_plv),
        "landscape_runtime_s": float(t_land - t_dgm),
        "total_runtime_s": float(t_land - t0),
        "peak_memory_mb": float(peak_mem / (1024.0 * 1024.0)),
        "h1_features_count": int(len(dgm)),
        "mean_plv": float(np.mean(plv[np.triu_indices(n_channels, k=1)])),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark simulation solvers and topological kernels with finite JSON telemetry."
    )
    parser.add_argument("--n-layers", type=int, default=1, help="Number of lattice layers for open quantum model.")
    parser.add_argument(
        "--solvers",
        nargs="+",
        default=["exact_dense", "sparse_shift_invert", "matrix_free"],
        help="Solvers to profile.",
    )
    parser.add_argument("--tolerance", type=float, default=1e-8, help="Numerical tolerance.")
    parser.add_argument(
        "--output-dir",
        default="outputs/benchmarks",
        help="Destination directory for benchmark telemetry artifacts.",
    )
    parser.add_argument(
        "--skip-topo",
        action="store_true",
        help="Skip topological filtration kernel benchmarks.",
    )

    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== NeuroTopology-Sim Solver & Kernel Benchmark ===")
    print(f"Lattice layers: {args.n_layers} | Solvers: {', '.join(args.solvers)}")

    t_start = datetime.now(timezone.utc).isoformat()
    solver_data = run_solver_benchmarks(
        n_layers=args.n_layers,
        solvers=args.solvers,
        tolerance=args.tolerance,
    )

    topo_data = None
    if not args.skip_topo:
        print("Benchmarking topological filtration kernels...")
        topo_data = run_topological_benchmarks(n_channels=32, n_samples=1000)

    payload = {
        "timestamp_utc": t_start,
        "n_layers": args.n_layers,
        "solvers_benchmark": solver_data,
        "topology_benchmark": topo_data,
        "guardrails": {
            "no_clinical_claims": True,
            "no_consciousness_claim": True,
            "no_toe_claim": True,
        },
    }

    target_file = out_dir / "simulation_solver_benchmark.json"
    written_path, digest = write_canonical_telemetry(target_file, payload)

    print(f"\n[OK] Benchmark telemetry written to: {written_path}")
    print(f"[OK] SHA-256 Digest: {digest}")

    # Summary table
    print("\n--- Solver Benchmark Summary ---")
    for name, s_info in solver_data.get("solvers", {}).items():
        if s_info.get("success"):
            print(
                f"  * {name:<20}: "
                f"time={s_info['runtime_s']:.4f}s | "
                f"peak_mem={s_info['peak_memory_mb']:.2f}MB | "
                f"residual={s_info['residual_norm']:.2e} | "
                f"converged={s_info['converged']}"
            )
        else:
            print(f"  * {name:<20}: FAILED / SKIPPED: {s_info.get('error') or s_info.get('reason')}")

    if topo_data:
        print("\n--- Topological Kernel Summary ---")
        print(
            f"  * PLV: {topo_data['plv_runtime_s']:.4f}s | "
            f"Ripser: {topo_data['ripser_pruned_runtime_s']:.4f}s | "
            f"Landscape: {topo_data['landscape_runtime_s']:.4f}s | "
            f"Peak Mem: {topo_data['peak_memory_mb']:.2f}MB"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
