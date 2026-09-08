# Persistent-Homology Adapter Layer: Post-Integration Hardening

## 1. Overview & Architecture

The persistent-homology adapter layer (`topo_monitor/tda_adapters`) provides a unified, backend-neutral interface for topological data analysis (TDA) across:
- **Accelerated C++ / GPU backends:** Ripser (`ripser`), GUDHI (`gudhi`), Ripser++ (`ripserplusplus`), and Giotto-tda (`gtda`).
- **Deterministic Pure NumPy/SciPy fallback:** `DeterministicFallbackBackend`, providing exact Vietoris-Rips boundary matrix reduction over GF(2) for low-dimensional, bounded verification fixtures without requiring external TDA packages.

This hardening pass audits numerical edge cases, enforces strict shape and property validations, prevents conflation between graph topological homology and spatial physical winding, documents discrete spatial lattice singularities, and ensures null-safe serialization.

---

## 2. Hardened Audits & Improvements

### 2.1 Input Shape and Geometric Validation
- **Point Clouds:** Strictly validated as real-valued 2D arrays $(N, D)$ with $N \ge 2$ and $D \ge 1$. Inputs with complex values, non-finite values (NaN, Inf, -Inf), $N < 2$, or $D < 1$ raise descriptive `ValueError`s.
- **Distance Matrices:** Strictly validated as real-valued, square $(N, N)$ arrays with $N \ge 2$, zero diagonal ($|D_{ii}| \le \text{atol}$), non-negative entries ($D_{ij} \ge -\text{atol}$), and exact symmetry ($|D_{ij} - D_{ji}| \le \text{atol}$). Validated matrices are canonicalized via $(D + D^T) / 2$ with zeroed diagonal and non-negative clamping. Negative tolerance parameters (`atol < 0`) are explicitly rejected.
- **Coincident & Degenerate Point Clouds:** Point clouds where all points are identical are handled without division-by-zero or numerical crashes: $H_0$ correctly retains 1 essential component, while all other components and $H_1$ holes with zero persistence ($d \le b$) are cleanly pruned.

### 2.2 Node-Reordering Invariance
- Permuting input points or nodes via an arbitrary permutation $\sigma \in S_N$ is guaranteed to leave computed persistence intervals and persistence landscapes invariant.
- The `verify_reordering_invariance` utility normalizes intervals via rounding and deterministic sorting by $(birth, death)$ before comparison, ensuring index tie-breaks do not produce false negative mismatches.

### 2.3 Persistence Landscapes & Exact Trapezoidal Integration
- Implements Bubenik (2015) persistence landscapes with explicit tent functions:
  $$f_{(b, d)}(t) = \max(0, \min(t - b, d - t))$$
- Evaluates $k$-th landscape layers $\lambda_k(t)$ by descending sort across tents at each filtration grid point.
- Validated against analytic geometry: for a single feature $(b, d)$, the tent function forms an isosceles triangle with base $d - b$ and height $(d - b) / 2$, yielding exact analytic area:
  $$\text{Area} = \frac{(d - b)^2}{4}$$
  Trapezoidal integration matches this value to $< 10^{-3}$ precision. Empty intervals evaluate to exactly zero area and zeroed layers.

### 2.4 Bounded Streaming Processing
- Memory-bounded streaming is supported via `stream_point_cloud_generator` (lazy generator yielding $(window\_range, result)$ tuples) and `stream_point_cloud_windows` (aggregate summary with peak memory and runtime telemetry).
- Enforces strict window constraints: $window\_size \ge 2$, $step\_size \ge 1$, $max\_allowed\_points\_per\_window \ge 2$, and $window\_size \le max\_allowed\_points\_per\_window$.
- Point cloud length smaller than window size raises an explicit `ValueError`.
- Aggregated streams compute a cumulative SHA-256 digest across window checksums.

### 2.5 Backend Capability Probing & Runtime Error Isolation
- Backends use **lazy dynamic imports**; no external package is imported at module load time.
- Probing via `get_capability()` returns explicit status flags: `AVAILABLE`, `MISSING`, `INCOMPATIBLE`, `DISABLED_OFFLINE`, or `FAILED`.
- Disabling backends via environment variables (e.g. `NEUROTOPO_DISABLE_RIPSER=1`) safely marks capability as `DISABLED_OFFLINE` without throwing exceptions.
- Runtime failures during backend execution (e.g., C++ internal memory exhaustion or binding exceptions) are caught and wrapped in a clean `RuntimeError(f"Backend '{name}' computation failed: ...")`.

### 2.6 Strict Scientific Status & Fallback Isolation
- The deterministic fallback backend is explicitly tagged with `ScientificStatus.APPROXIMATE_FIXTURE_ONLY`.
- Fallback fixtures are restricted to $N \le 128$ points. Exceeding this bound raises a descriptive `ValueError` directing the user to accelerated engines (`ripser`, `gudhi`).
- Fallback and synthetic fixture outputs must **never** be interpreted as empirical or biological evidence.

### 2.7 Strict Separation: Graph Beta-1 vs Spatial Topological Charge
- Enforces strict lexical and conceptual separation: `assert_not_spatial_charge()` rejects any attempt to alias or label graph $H_1$ cycle rank as `spatial_charge`, `spatial_topological_charge`, `winding_charge`, `vortex_charge`, `phase_winding`, `winding_number`, `topological_charge`, or `spatial_winding`.
- Graph $H_1$ cycle rank represents the number of independent 1-cycles in an abstract metric simplicial complex. Spatial topological charge represents the line integral of a continuous phase gradient over physical sensor/grid coordinates.

---

## 3. Investigation: Spatial-Vortex Integer-Coordinate Cancellation

### 3.1 Numerical Mechanism of Plaquette Grid Cancellation
In discrete lattice phase topology, the spatial winding charge $Q$ is computed by summing the discrete phase curl (contour integral) around elementary grid plaquettes:
$$Q = \sum_{\text{plaquettes}} q_{\text{cell}}$$
where around a 4-vertex square $[(x, y), (x+1, y), (x+1, y+1), (x, y+1)]$:
$$q_{\text{cell}} = \frac{1}{2\pi} \sum_{e \in \partial \text{cell}} \text{wrap}(\Delta \theta_e)$$

**Numerical Singularity Collision:**
1. When an analytic phase vortex $\theta(x, y) = q \cdot \text{atan2}(y - y_0, x - x_0)$ has its center $(x_0, y_0)$ placed **directly on an integer grid vertex** (e.g. $(10.0, 10.0)$), the central node satisfies $\Delta y = 0, \Delta x = 0$.
2. Under standard IEEE 754 floating-point arithmetic, $\text{atan2}(0, 0) = 0.0$. The singularity is not in the interior of any cell, but lies directly on the corner vertex shared by four adjacent plaquettes.
3. Across the negative horizontal axis ($x < x_0, y = y_0$), the phase approaches $\pm \pi$. The difference $\text{wrap}(\pi - 0)$ collides with the branch cut, causing the discrete phase differences across the four adjacent plaquettes to experience destructive cancellation or spurious defect generation (evaluating to $-2.0$ or $0.0$ instead of the true charge $+1.0$).

### 3.2 Resolution & Contrast with TDA Invariance
- **Spatial Plaquette Resolution:** Offsetting the vortex center by half a cell (e.g. $(x_0, y_0) = (10.5, 10.5)$) encloses the singularity strictly within the interior of a single plaquette without intersecting any boundary vertex, accurately recovering unit topological charge ($|Q| = 1.0$).
- **TDA Persistent Homology Immunity:** Unlike discrete grid plaquettes, Vietoris-Rips persistent homology operates directly on pairwise metric distances between sampled points:
  $$d(p_i, p_j) = \|p_i - p_j\|_2$$
  Because Euclidean distances are invariant under rigid translations ($p_i \mapsto p_i + c$), computing TDA persistent homology on a point cloud sampled around an integer-centered vortex $(10.0, 10.0)$ vs an off-integer vortex $(10.5, 10.5)$ yields **identical birth times, identical death times, and identical persistence landscapes**.
- TDA is completely immune to grid coordinate centering artifacts.

---

## 4. Null-Safe Serialization Guarantee

- `TDAPersistenceResult.to_dict()` and `to_json()` guarantee that all infinite filtration death times, unclosed cycles, and missing metrics serialize to JSON `null`.
- Floating-point `NaN`, `Infinity`, and `-Infinity` are recursively replaced with `None` across intervals, landscape grids, integrated areas, runtime telemetry, and arbitrary user metadata.
- JSON output is exported with `allow_nan=False`, guaranteeing strict adherence to RFC 8259 JSON standards.

---

## 5. Verification Commands & Coverage

All tests run in isolated, no-network environments:

```bash
# Run existing adapter tests and hardened adversarial tests
uv run python -m pytest -c /dev/null -o addopts="--import-mode=importlib" tests/topology_monitoring/test_tda_adapters.py tests/topology_monitoring/test_tda_adapter_hardening.py

# Run full topology analytic ground-truth suite
uv run python -m pytest -c /dev/null -o addopts="--import-mode=importlib" tests/test_topo_monitor.py tests/test_topology_analytic_ground_truth.py
```

### Test Results
- `tests/topology_monitoring/test_tda_adapters.py`: 13 passed
- `tests/topology_monitoring/test_tda_adapter_hardening.py`: 13 passed
- `tests/test_topo_monitor.py`: 3 passed
- `tests/test_topology_analytic_ground_truth.py`: 46 passed
- **Total: 75 tests passing (100% pass rate).**
