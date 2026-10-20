# TDA Backend Semantic Conformance Specification

## 1. Overview & Mathematical Scope

This specification establishes the semantic conformance contract between the repository's internal topology/persistence representations and optional Topological Data Analysis (TDA) execution backends.

Persistent homology extracts topological invariants (connected components $H_0$, 1-cycles/loops $H_1$, and 2-cavities/voids $H_2$) across a parameterized filtration scale $t \in [0, \infty)$. Because different algorithms, cell complexes, and metric conventions describe fundamentally different mathematical objects, **comparison is only valid when mathematical configurations are strictly equivalent**.

> [!IMPORTANT]
> **Implementation Conformance Only**: Numerical and barcode agreement between backends verifies only the mathematical correctness of simplicial/cubical complex reduction algorithms. It **does not** validate any empirical neural model, choice of metric or filtration threshold, or any hypothesis regarding consciousness or cognitive mechanisms.

---

## 2. Mathematical Comparability Rules

Before comparing persistence barcodes or computing bottleneck distances, the harness evaluates mathematical comparability. If configurations differ in complex type, metric space, coefficient field, or threshold semantics, the comparison is strictly classified as `NOT_COMPARABLE`.

### 2.1 Comparability Matrix

| Dimension / Property | Vietoris-Rips Simplicial | Cubical Sublevel Complex | Conformance Status |
| :--- | :--- | :--- | :--- |
| **Complex Structure** | Clique complex on metric space | Regular $d$-dimensional orthogonal grid | **NOT_COMPARABLE** |
| **Filtration Element** | Simplex diameter $\max_{i<j} d(v_i, v_j)$ | Lower-star grid cell sublevel value | **NOT_COMPARABLE** |
| **Input Representation** | Distance matrix $(N, N)$ or point cloud | Scalar field array $(N_x, N_y)$ or $(N_x, N_y, N_z)$ | **NOT_COMPARABLE** |
| **Default Coefficient** | $\mathbb{Z}_2$ | $\mathbb{Z}_2$ | Comparable if complexes match |
| **Infinite Bar Semantics**| Essential class ($death = \infty$) | Essential class ($death = \infty$) | Comparable if mapped to `None` |

### 2.2 Rejection Rules (No Force-Matching)

1. **Complex Type & Filtration Mismatch**:
   Comparing a cubical sublevel persistence diagram (e.g., from `core.topology.compute_cubical_persistence`) directly to a Vietoris-Rips diagram on a distance matrix (e.g., from `analysis.connectivity_topology.compute_beta1`) is **mathematically invalid**. The comparator rejects this with `FILTRATION_MISMATCH`.
2. **Metric & Dissimilarity Mismatch**:
   Pairwise Euclidean distances, $1 - \mathrm{PLV}$ phase-locking dissimilarities, and $1 - \mathrm{coherence}$ spectral dissimilarities live in different metric spaces. Two backends must be evaluated on the identical metric matrix.
3. **Coefficient Field Mismatch**:
   Homology computed over $\mathbb{Z}_2$ cannot be equated to homology over $\mathbb{Z}_3$ or $\mathbb{Q}$ due to potential torsion differences.
4. **Threshold Truncation Mismatch**:
   A filtration bounded at threshold $T_{\max}$ where features have not yet died must not be matched against an unbounded filtration without explicit handling of boundary truncation.

---

## 3. Deterministic Synthetic Fixture Suite

The conformance harness defines 7 primary analytical synthetic fixtures plus 2 cubical grid fixtures:

### 3.1 Fixture 1: Empty and Degenerate Inputs
- **Empty set ($N=0$)**: Distance matrix of shape `(0, 0)`. Diagram: $H_0 = \emptyset, H_1 = \emptyset$.
- **Single point ($N=1$)**: Distance matrix `[[0.0]]`. Diagram: $H_0 = \{[0.0, \infty)\}, H_1 = \emptyset$.

### 3.2 Fixture 2: Disconnected Components
- **Points**: 4 vertices configured as two distant pairs: $(0,0), (1,0)$ and $(11,0), (12,0)$.
- **Analytical Barcode**:
  - Within-pair distance is $1.0$; cross-pair distance is $10.0$.
  - At $t=0.0$: 4 components born.
  - At $t=1.0$: two pairs merge into two components (two $H_0$ bars die at $1.0$).
  - At $t=10.0$: the two pairs merge into a single component (one $H_0$ bar dies at $10.0$).
  - $H_0$: $[0.0, 1.0), [0.0, 1.0), [0.0, 10.0), [0.0, \infty)$.
  - $H_1$: $\emptyset$.

### 3.3 Fixture 3: Known Loop ($S^1$ Unit Square)
- **Points**: 4 vertices of a unit square: $(0,0), (1,0), (1,1), (0,1)$.
- **Edge lengths**: 4 boundary edges of length $1.0$; 2 diagonals of length $\sqrt{2} \approx 1.41421356$.
- **Analytical Barcode**:
  - At $t=1.0$: 4 boundary edges appear. 3 components merge into 1 (three $H_0$ bars die at $1.0$). A 1-cycle is born at $t=1.0$.
  - At $t=\sqrt{2}$: diagonals appear, introducing 2-simplices that fill the cavity. The 1-cycle dies at $t=\sqrt{2}$.
  - $H_0$: three bars $[0.0, 1.0)$, one bar $[0.0, \infty)$.
  - $H_1$: exactly one bar $[1.0, \sqrt{2} \approx 1.41421356)$. Lifetime $= \sqrt{2} - 1 \approx 0.41421356$.

### 3.4 Fixture 4: Filled Triangle / Simplex (2-Simplex)
- **Points**: 3 vertices of an equilateral triangle with edge length $1.0$.
- **Analytical Barcode**:
  - At $t=1.0$: all 3 edges appear simultaneously.
  - Simultaneously, the 2-simplex $[0, 1, 2]$ has diameter $\max(1.0, 1.0, 1.0) = 1.0$, entering the filtration at $t=1.0$.
  - The cycle boundary is filled at birth; persistence lifetime is $0.0$.
  - $H_0$: two bars $[0.0, 1.0)$, one bar $[0.0, \infty)$.
  - $H_1$: $\emptyset$ (zero-persistence cycles are dropped).

### 3.5 Fixture 5: Reordered Vertices (Permutation Invariance)
- **Distance matrix**: A non-trivial row/column permutation $D_{\pi} = D[\pi, \pi]$ of Fixture 3.
- **Invariance Contract**: Persistent homology is an invariant of the metric space; vertex indexing has zero effect on the persistence diagram. Bottleneck distance $d_B(D, D_{\pi}) = 0.0$.

### 3.6 Fixture 6: Duplicate / Coincident Points
- **Points**: 3 points where point 0 and point 1 are coincident ($d(p_0, p_1) = 0.0$), and point 2 is at distance $1.0$.
- **Robustness Contract**: The zero-distance edge merges components at $t=0.0$ without division by zero, NaNs, or crashes. $H_0$ has one finite merger at $1.0$ and one surviving component $[0.0, \infty)$.

### 3.7 Fixture 7: Threshold Boundary
- **Input**: Unit square evaluated with threshold $T_{\max} = 1.2 < \sqrt{2}$.
- **Boundary Contract**: The loop is born at $1.0$, but its filling simplex at $\sqrt{2}$ exceeds the threshold. In the truncated complex, the bar does not die and is reported with $death = \mathrm{None}$ (infinite in the bounded filtration).

---

## 4. Backend Probing and Graceful Degradation

The harness probes available software without executing harvested code or installing third-party dependencies:

| Backend ID | Package | Primary Source / Authors | License | Optional Status |
| :--- | :--- | :--- | :--- | :--- |
| `reference_simplicial` | Built-in | Pure NumPy implementation over $\mathbb{Z}_2$ | MIT (Repo) | Mandatory Ground Truth |
| `ripser` | `ripser` | Ulrich Bauer / Christopher Tralie | MIT | Optional |
| `gudhi_rips` | `gudhi` | Inria GUDHI Project | MIT | Optional |
| `gudhi_cubical` | `gudhi` | Inria GUDHI Project | MIT | Optional |
| `cripser_cubical` | `cripser` | Takeki Sudo / Kazushi Yoshida | LGPL-3.0 | Optional |

### 4.1 Missing Backend Guarantees
- If `ripser` or `gudhi` is not installed, adapters return `is_available = False` and `success = False`.
- Pairwise comparisons return `ComparabilityStatus.BACKEND_UNAVAILABLE`.
- Tests targeting optional backends use `@pytest.mark.skipif(not is_module_installed(...))` to skip cleanly.
- Under zero optional dependencies, **100% of the base conformance test suite passes**.

### 4.2 Excluded Packages
In accordance with repository guidelines:
- `REA`, `PaperGym`, `AutoResearch`, `OpenResearch`, and `openmed` are **not** TDA backends and are excluded.
- Unverified proposals (e.g. Gemini Round 5) are not independent mathematical sources.

---

## 5. Serialization and Invariant Verification

All persistence outputs adhere to strict finite JSON serialization:
- Infinite death values are represented as `null` in JSON and `None` in Python objects.
- `NaN` and `Infinity` are rejected by `json.dumps(..., allow_nan=False)`.
- Full roundtrip compatibility is maintained with `core.persistence_export.serialize_diagram` and `deserialize_diagram`.

### 5.1 Graph $\beta_1$ vs Spatial Charge Separation
Per repository guardrails, graph cycle count ($\beta_1$) from distance matrices is strictly isolated from continuous spatial phase winding ($Q$ or $Q_{\mathrm{abs}}$):
- `analysis.connectivity_topology.topology_metric_record` enforces `separation.graph_beta1_is_spatial_charge = False`.
- Graph 1-cycles derived from functional connectivity matrices do not imply spatial topological defects or physical vortices.

---

## 6. Execution and Verification

To run the full conformance test suite:
```bash
pytest tests/topology_backend_conformance/ -v
```

To run the CLI conformance audit:
```bash
python -m tools.topology_backend_conformance.cli --output conformance_report.json
```
