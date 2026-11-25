# TDA Backend Reproducibility and Equivalence Audit

## 1. Executive Summary and Purpose

The Topological Data Analysis (TDA) Reproducibility and Equivalence subsystem provides an autonomous, bounded, and mathematically rigorous validation harness for persistent homology computations in `NeuroTopology-Sim`.

Heterogeneous TDA packages (`ripser`, `GUDHI`, `giotto-tda`, `ripser++`, and repository fallbacks) employ varying underlying algorithmic optimizations—ranging from cohomology reduction, clearing, and dualization to simplex trees and GPU-accelerated boundary matrices. While theoretically computing equivalent homology groups over field coefficients $\mathbb{Z}_2$, numerical tolerances, floating-point truncation, simplex filtration ordering, and infinite interval handling can induce subtle divergences across environments.

This subsystem continuously audits:
1. **Backend Availability & Compatibility**: Probes installed packages safely without triggering dynamic installations or network access.
2. **Mathematical Invariants**: Enforces distance matrix symmetry, zero diagonal, finite interval boundaries, node-reordering invariance, and bounded memory capacity.
3. **Cross-Backend Equivalence**: Compares persistence diagrams pairwise across all active backends using bottleneck distance, Wasserstein distance, and coordinate deltas.
4. **Explicit Disagreement Logging**: Directly records any numerical or topological divergence without artificial consensus or silent smoothing.
5. **Spatial Charge Isolation**: Strictly enforces that graph $\beta_1$ 1-cycle counts are never conflated with or labeled as geometric spatial phase charge ($Q_{\text{spatial}}$).

> [!NOTE]
> **Scientific Guardrail**: All benchmark fixtures and comparative evaluations are synthetic engineering tests. Synthetic data does not constitute empirical biological evidence. Persistent homology cycle rank ($\beta_1$) is purely topological and strictly separate from geometric vortex winding charge ($Q_{\text{spatial}}$).

---

## 2. Monitored TDA Backends

The audit probes five distinct backend engines:

| Backend ID | Nature | Expected homological dimensions | Input Types | Description |
|---|---|---|---|---|
| `ripser` | Exact | $H_0, H_1, H_2$ | Distance matrix, point cloud | High-performance C++ cohomology engine via sparse boundary reduction. |
| `gudhi` | Exact | $H_0, H_1, H_2, \dots$ | Distance matrix, point cloud | INRIA GUDHI library utilizing `RipsComplex` and `SimplexTree` persistence. |
| `gtda` | Exact | $H_0, H_1$ | Point cloud, distance matrix | `giotto-tda` scikit-learn compatible transformer. |
| `ripserplusplus` | Exact | $H_0, H_1$ | Distance matrix | GPU/multicore parallelized Ripser implementation. |
| `fallback` | Bounded exact / approx | $H_0, H_1$ ($N \le 45$) | Distance matrix | Pure NumPy/SciPy boundary matrix reduction over $\mathbb{Z}_2$ for small complexes; Kruskal Minimum Spanning Tree for $H_0$ on larger complexes. |

---

## 3. Mathematical & Operational Invariants

Every audit execution verifies seven core invariants across all inputs and diagram outputs:

### 3.1 Distance Matrix Symmetry ($D = D^T$)
- Input matrices must be finite, non-negative, and strictly symmetric:
  $$\max_{i, j} |D_{ij} - D_{ji}| \le 10^{-8}$$

### 3.2 Zero Diagonal ($\text{diag}(D) = 0$)
- Self-distances must evaluate to zero within numerical precision:
  $$\max_i |D_{ii}| \le 10^{-8}$$

### 3.3 Finite Intervals ($0 \le \text{birth} \le \text{death}$)
- For every finite persistence pair $(b, d)$, the death time must strictly equal or exceed the birth time. Pairs with zero lifespan ($d - b \le 10^{-7}$) represent numerical artifacts and are pruned. Non-finite death values must be explicitly represented as `null` in JSON.

### 3.4 Node-Reordering Invariance
- Permuting vertex indices via an arbitrary permutation $\pi \in S_N$ transforms the distance matrix to $D' = P_\pi D P_\pi^T$. The resulting canonical persistence diagrams and deterministic checksums must be invariant under this group action:
  $$\text{Dgm}_k(P_\pi D P_\pi^T) = \text{Dgm}_k(D)$$

### 3.5 Bounded Point Capacity
- To prevent catastrophic combinatorial simplex explosion ($O(N^3)$ or $O(2^N)$), input point counts are capped (default: $N \le 256$). Inputs exceeding the threshold are cleanly rejected before allocating simplex complexes.

### 3.6 Spatial Phase Charge Isolation
- **Strict Guardrail**: Graph Betti-1 homology ($\beta_1 \in \{0, 1, 2, \dots\}$) measures the rank of 1-cycles in graph/Vietoris-Rips complexes. Spatial phase charge ($Q_{\text{spatial}} \in \mathbb{Z}$) measures the signed integer winding of phase fields across geometric sensor coordinates. The audit scanner verifies that keys, schemas, and pipeline payloads never equate, cross-label, or alias $\beta_1$ with $Q_{\text{spatial}}$.

### 3.7 Deterministic Repeated Checksums
- Repeated executions on identical distance matrices must generate bit-for-bit identical SHA-256 digests computed over canonically sorted interval strings:
  $$\text{SHA256}\left(\bigoplus_{i} \text{dim}_i : \text{birth}_i : \text{death}_i\right)$$

---

## 4. Cross-Backend Equivalence Criteria

When two or more backends execute successfully on the same fixture, their outputs are compared pairwise:

1. **Exact Pair Matching**: Intervals are sorted by `(dimension, birth, death)`. Differences in birth and death coordinates are audited against a tolerance threshold $\epsilon = 10^{-4}$.
2. **Bottleneck Distance**: Evaluates the infimum over all bijections $\gamma$:
   $$d_B(X, Y) = \inf_\gamma \sup_{p \in X} \|p - \gamma(p)\|_\infty$$
   Computed via `persim` when available, or bounded diagonal projection matching.
3. **Wasserstein Distance**: Evaluates optimal transport cost with $p=2$:
   $$W_p(X, Y) = \left( \inf_\gamma \sum_{p \in X} \|p - \gamma(p)\|_\infty^p \right)^{1/p}$$
4. **Disagreement Policy**: If two backends diverge in cycle count or exceed the tolerance threshold, the audit records `equivalent = false` and logs an explicit `disagreement_reason`. Disagreements are never silently masked or averaged out.

---

## 5. CLI Usage and Telemetry

The audit is executable via `scripts/audit_tda_reproducibility.py`:

```bash
# Standard summary output
python scripts/audit_tda_reproducibility.py --format summary

# Strict JSON output (null-safe, allow_nan=False)
python scripts/audit_tda_reproducibility.py --format json --output outputs/tda_audit.json

# Markdown output
python scripts/audit_tda_reproducibility.py --format markdown --output docs/topology_monitoring/latest_audit.md

# Filter specific fixtures in strict CI mode
python scripts/audit_tda_reproducibility.py --fixtures circle_s1_12,triangle_equilateral_3 --strict
```

### Command-Line Arguments:
- `--fixtures`: Comma-separated list of fixture IDs to evaluate (`circle_s1_12`, `two_clusters_10`, `line_segment_8`, `triangle_equilateral_3`, `random_euclidean_14_s42`).
- `--output`: File path to persist report (JSON or Markdown).
- `--format`: Format for standard output (`summary`, `json`, `markdown`).
- `--strict`: Exit code 1 if any invariant fails or if backends disagree.
- `--max-points`: Point count capacity threshold (default: 256).
- `--seed`: Deterministic pseudo-random seed (default: 42).
- `--export-obsidian`: Optional path to write an Obsidian mirror markdown note.

---

## 6. Output Schema & Null-Safety

The output JSON follows `schema_version: "1.0.0"`. In strict compliance with repository null-safety rules:
- No `NaN` or `Infinity` tokens are ever emitted in JSON (`allow_nan=False`).
- Infinite persistence death values are converted to explicit `null`.
- Empty diagrams are represented as empty lists `[]`.
- Telemetry captures wall-clock duration in seconds and heap peak delta via `tracemalloc`.
