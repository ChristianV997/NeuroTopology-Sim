# Persistent-Homology Backend Adapters (`topo_monitor.tda_adapters`)

## Overview

The `topo_monitor.tda_adapters` package provides a backend-neutral persistent-homology adapter layer for topological data analysis (TDA) within `NeuroTopology-Sim`. It abstracts the underlying computational engines for Vietoris-Rips persistent homology ($H_0$ connected components and $H_1$ 1-dimensional cycle persistence) while maintaining strict scientific guardrails, dependency isolation, and bounded memory execution.

## Architecture

```
topo_monitor/tda_adapters/
├── __init__.py           # High-level facade, exports, and invariance verification
├── types.py              # Typed dataclasses, enums, null-safe JSON serialization, SHA-256 checksums
├── validation.py         # Strict shape/finiteness checks, metric validation, scientific semantics guard
├── base.py               # Abstract BaseTDABackend protocol and telemetry instrumentation
├── landscape.py          # Deterministic beta-1 persistence landscape and trapezoidal integration
├── fallback.py           # Pure NumPy/SciPy exact simplicial VR reduction for bounded fixtures
├── backends.py           # Lazy adapters for Ripser, GUDHI, Ripser++, and Giotto-tda
├── registry.py           # Capability discovery, status probing, priority resolution
├── streaming.py          # Memory-bounded windowed point-cloud streaming processor
└── cli.py                # Command-line inspection and execution interface
```

## Supported Backends & Capabilities

Every backend is probed dynamically using lazy imports. No packages are auto-installed, and no remote binaries or assets are downloaded at runtime.

| Backend | Identifier | Primary Technology | Max Dim | Exact Pairs | Status Values |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **Ripser** | `ripser` | C++ persistent cohomology bindings | 2 | No | `available`, `missing`, `disabled_offline`, `failed` |
| **GUDHI** | `gudhi` | C++ SimplexTree / RipsComplex | 3 | Yes | `available`, `missing`, `disabled_offline`, `failed` |
| **Ripser++** | `ripserplusplus` | GPU/CUDA accelerated cohomology | 2 | No | `available`, `missing`, `incompatible`, `disabled_offline` |
| **giotto-tda** | `giotto-tda` | Scikit-learn compatible C++ | 2 | No | `available`, `missing`, `incompatible`, `disabled_offline` |
| **Fallback** | `deterministic-fallback` | NumPy / SciPy GF(2) boundary reduction | 1 | Yes | `available` (unconditional) |

### Capability Status Lifecycle

Backend capability states are represented by `BackendCapabilityStatus`:
- `AVAILABLE`: The package is importable and functional in the active environment.
- `MISSING`: The optional dependency is not installed.
- `INCOMPATIBLE`: Installed library fails hardware or Python ABI requirements.
- `DISABLED_OFFLINE`: Backend is suppressed explicitly via environment variable (e.g. `NEUROTOPO_DISABLE_RIPSER=1`).
- `FAILED`: Backend raised an error during initialization.

## Strict Scientific Semantics

### Graph $\beta_1$ vs. Spatial Topological Charge
`NeuroTopology-Sim` maintains strict separation between topological invariants across domains:
1. **Graph $\beta_1$ (First Betti Number / Homology $H_1$)**:
   - Measures the rank of the first homology group $H_1(K; \mathbb{Z}_2)$ of a simplicial complex or graph.
   - Identifies independent non-bounding 1-cycles (loops) formed by pairwise distance or functional connectivity thresholds.
   - Does not possess spatial orientation, spatial chirality, or physical embedding singularity metrics.
2. **Spatial Winding / Topological Charge ($Q$)**:
   - Represents the contour or surface integral of a continuous spatial phase gradient around a phase vortex singularity:
     $$Q = \frac{1}{2\pi} \oint_C \nabla \theta \cdot d\mathbf{x} \in \mathbb{Z}$$
   - Requires physical sensor coordinates $(x, y)$ or $(x, y, z)$.
3. **Scalar Chirality**:
   - Pertains to geometric parity transformations and pseudo-scalar invariant projections.

> [!CAUTION]
> Under no circumstances may graph cycle counts or $H_1$ persistence intervals be labeled or treated as spatial topological charge or vortex winding. The `assert_not_spatial_charge()` guardrail will raise an immediate `ValueError` if spatial charge terminology is applied to TDA adapter outputs.

## Input Validation and Shape Guarantees

The adapter accepts two primary data representations with strict validation:

1. **Point Clouds** (`InputKind.POINT_CLOUD`):
   - Shape: $(N, D)$ where $N \ge 2$ and $D \ge 1$.
   - Finiteness: All entries must be finite (`isfinite(x)`). Any `NaN` or `Inf` raises `ValueError`.
2. **Distance Matrices** (`InputKind.DISTANCE_MATRIX`):
   - Shape: $(N, N)$ square matrix with $N \ge 2$.
   - Symmetry: $|D_{ij} - D_{ji}| \le 10^{-6}$.
   - Zero Diagonal: $|D_{ii}| \le 10^{-6}$.
   - Non-negativity: $D_{ij} \ge 0$.
   - Finiteness: All entries must be finite.

## Output Structure & Null Serialization

Results are returned as a typed `TDAPersistenceResult` with complete metadata:
- `beta_0_intervals`: List of $H_0$ persistence intervals $[b, d)$.
- `beta_1_intervals`: List of $H_1$ persistence intervals $[b, d)$.
- `persistence_pairs`: Simplex birth/death pairs (where supported).
- `filtration_range`: Bounded range $(0.0, r_{\text{max}})$.
- `backend`: Name of the executed backend.
- `runtime_seconds`: High-resolution execution runtime.
- `memory_telemetry_bytes`: Peak memory allocated during computation via `tracemalloc`.
- `deterministic_checksum`: SHA-256 digest over canonicalized outputs.
- `scientific_status`:
  - `strict_cohomology`: Full persistent cohomology via C++ libraries.
  - `approximate_fixture_only`: Exact boundary reduction restricted to bounded low-dimensional test fixtures ($N \le 128$).
  - `bounded_window_streaming`: Rolling window processing.

### Serialization Rule: No NaN or Infinity
When features do not die within the filtration threshold (essential classes), their death time is represented as `None` in Python and serializes to `null` in JSON. No `NaN` or `Infinity` tokens are ever emitted in JSON payloads.

## Deterministic Betti-1 Persistence Landscapes

Persistence landscapes $\lambda_k(t)$ (Bubenik, 2015) are computed deterministically over an explicit filtration grid:
$$f_{(b, d)}(t) = \max(0, \min(t - b, d - t))$$
$$\lambda_k(t) = k\text{-th largest } \{ f_{(b_i, d_i)}(t) \}_i$$

Integrated landscape area is evaluated using the trapezoidal rule:
$$\text{Area} = \int_{t_{\text{min}}}^{t_{\text{max}}} \sum_{k=1}^K \lambda_k(t) \, dt$$

## Windowed Streaming Mode

For continuous or time-series point clouds $(T, D)$, `stream_point_cloud_windows` processes temporal windows of size $W$ with step $S$:
- Bounded memory footprint: Enforces `window_size <= max_allowed_points_per_window`.
- Telemetry: Aggregates mean $\beta_0$, mean $\beta_1$, maximum $\beta_1$, peak memory, and cumulative SHA-256 stream checksums.
- Generator support: `stream_point_cloud_generator` yields window results lazily without accumulating intermediate representations in memory.

## Benchmarking Utility

A dedicated benchmark script is provided at `scripts/benchmark_tda_backends.py`:
```bash
python scripts/benchmark_tda_backends.py --points 32 --dim 3 --fixture circle --iterations 3 --output-json benchmark_results.json
```

> [!NOTE]
> Runtime benchmarks reflect algorithmic implementations, memory allocations, and hardware bindings for specific sample geometries. They do not imply scientific superiority or theoretical validity.
