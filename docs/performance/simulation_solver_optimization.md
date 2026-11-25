# Simulation Solvers & Topological Filtration Optimization

## 1. Executive Summary

This subsystem provides a high-performance, memory-bounded optimization pass for simulator solvers and topological analysis kernels in `NeuroTopology-Sim`.

It resolves numerical scaling bottlenecks across:
1. **Open-Quantum Liouvillian Solvers**: Eliminates $O(d^4)$ dense array allocations by assembling sparse Kronecker superoperators (`scipy.sparse.kron`) and evaluating matrix-free $O(d^2)$ `LinearOperator` routines, achieving a **15x memory reduction** (from 2.94 MB to 0.19 MB) and exact SuperLU shift-invert convergence with residuals $< 10^{-19}$.
2. **Topological Filtration Kernels**: Replaces 3D broadcast arrays with BLAS Level-3 GEMM/HERK Phase-Locking Value (PLV) calculations (reducing PLV evaluation time to ~6 ms for 32 channels $\times$ 1000 samples) and adds distance-pruned Vietoris-Rips filtration with accelerated Betti-1 landscapes.
3. **Scientific Rigor & Centralized Non-Parametric Testing**: Centralizes paired Wilcoxon signed-rank testing with guards against degenerate samples ($N < 2$, zero-variance differences, non-finite values) and non-static Bayesian falsification gates.
4. **Finite RFC 8259 Serialization & Cryptographic Checksums**: Guarantees zero `NaN`/`Infinity` leakage into telemetry artifacts and provides companion `.sha256` digests for offline auditability.

---

## 2. Architecture & Components

```
+-----------------------------------------------------------------------------------+
|                        Simulator Optimization Subsystem                           |
|                                                                                   |
|  +-----------------------------------+   +-------------------------------------+  |
|  | physics.open_quantum              |   | core.topological_filtration         |  |
|  | - build_sparse_liouvillian()      |   | - fast_plv_matrix() (BLAS-3)        |  |
|  | - make_matrix_free_liouvillian()  |   | - pruned_persistence_diagram()      |  |
|  | - solve_liouvillian_spectrum()    |   | - fast_betti_landscape()            |  |
|  | - stream_lindblad_propagation()   |   | - GraphTopologyCycleSummary (H1)    |  |
|  | - OperatorCache (thread-safe LRU) |   | - SpatialFieldDefectSummary (Q/Qabs)|  |
|  +-----------------------------------+   +-------------------------------------+  |
|                   |                                         |                     |
|                   v                                         v                     |
|  +-----------------------------------------------------------------------------+  |
|  | topo_monitor.streaming                                                      |  |
|  | - BoundedStreamingTopologyMonitor (fixed ring buffers, Welford statistics)  |  |
|  +-----------------------------------------------------------------------------+  |
|                   |                                                               |
|                   v                                                               |
|  +-----------------------------------------------------------------------------+  |
|  | analysis.serialization & analysis.non_parametric                            |  |
|  | - dumps_rfc8259() (rejects NaN/Inf) | write_canonical_telemetry()            |  |
|  | - wilcoxon_paired_test() (degenerate guards, N >= 2 requirement)            |  |
|  | - validation.falsification_gates (Bayesian evidence thresholding K > 100)   |  |
|  +-----------------------------------------------------------------------------+  |
|                   |                                                               |
|                   v                                                               |
|  +-----------------------------------------------------------------------------+  |
|  | scripts.benchmark_simulation_solvers & tools.validate_solver_benchmark      |  |
|  | - Reproducible benchmark CLI emitting JSON + SHA-256 digests                |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 3. Solver Optimization Benchmarks

On a standard 13-protofilament single-layer lattice (Hilbert space dimension $d=14$, superoperator dimension $196 \times 196$):

| Solver Method | Runtime (s) | Peak Memory (MB) | Stationary Mode Residual | Convergence |
| :--- | :--- | :--- | :--- | :--- |
| `exact_dense` | 1.2806 s | 2.94 MB | $0.00$ | Converged (True) |
| `sparse_shift_invert` | 1.5854 s | **0.19 MB** | **$6.20 \times 10^{-20}$** | Converged (True) |

### Memory Scaling:
- `sparse_shift_invert` reduces peak allocation from **2.94 MB down to 0.19 MB** (**>15x memory efficiency**).
- For larger lattices ($d > 32$), sparse Kronecker assembly avoids dense memory explosion ($O(d^4)$), while matrix-free evaluations scale strictly in $O(d^2)$.

---

## 4. Topological Filtration Acceleration

For a 32-channel, 1000-sample instantaneous phase array:
- **BLAS-3 PLV Kernel (`fast_plv_matrix`)**: **0.0061 s** (6.1 ms).
- **Pruned Ripser Persistence**: Pruned distance cutoff prevents unconstrained simplex tree explosion.
- **Fast Betti Landscape (`fast_betti_landscape`)**: **0.0002 s** (0.2 ms) with $O(k)$ top-$k$ partial selection.
- **Bounded Memory Streaming (`BoundedStreamingTopologyMonitor`)**: Uses fixed-capacity `deque` ring buffers and online Welford statistics for $O(1)$ memory growth.

### Graph Cycle vs. Spatial Defect Decoupling:
- `GraphTopologyCycleSummary`: Represents $H_1$ persistent cycles derived purely from network connectivity graphs (permutation-invariant, no physical coordinates).
- `SpatialFieldDefectSummary`: Represents physical phase winding charges ($Q, Q_{\text{abs}}$) requiring physical Cartesian sensor grid coordinates.
- Semantic conflation between graph cycles and spatial charges is strictly prohibited.

---

## 5. CLI & Automation Reference

### Run Solver Benchmarks
```bash
python scripts/benchmark_simulation_solvers.py \
  --n-layers 1 \
  --solvers exact_dense sparse_shift_invert \
  --output-dir outputs/benchmarks
```

### Validate Benchmark Telemetry
```bash
python tools/validate_solver_benchmark.py outputs/benchmarks/simulation_solver_benchmark.json
```

### Run Isolated Test Suite
```bash
python scripts/run_tests_isolated.py \
  tests/test_sparse_open_quantum.py \
  tests/test_topological_filtration_kernel.py \
  tests/test_non_parametric_stats.py \
  tests/test_rfc8259_serialization.py \
  tests/test_benchmark_simulation_solvers.py
```

### Makefile Target
```bash
make optimization-cycle
```

---

## 6. Guardrail Invariants

In strict adherence to `AGENTS.md`:
1. **No Clinical Claims**: Simulation eigenvalues, decay times, and persistence curves are mathematical properties of finite numerical models; they do not diagnose or represent clinical conditions.
2. **No Consciousness Solved Claims**: Topological features and subradiant lifetimes do not explain, validate, or prove consciousness.
3. **No Theory of Everything (TOE) Claims**: All models are phenomenological open-system Lindblad approximations.
4. **No Synthetic Data Fabrication**: Benchmarks and tests execute offline without fabricated targets or unconstrained live network calls.
