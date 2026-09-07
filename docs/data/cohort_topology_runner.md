# Local Streaming Paired-Cohort Topology Execution Runner

## 1. Overview and Scientific Motivation

The `cohort_topology_runner` subsystem provides a local, streaming execution bridge that consumes a validated paired-cohort manifest (`PairedCohortManifest`) and runs persistent topology analysis across paired electrophysiological recordings.

Prior cohort pipelines suffered from three fundamental limitations:
1. **Unbounded Memory Pressure**: Attempted to load entire cohorts into RAM simultaneously or required monolithic arrays.
2. **Readiness Obliviousness**: Crashed on unvalidated, ambiguous, or incomplete cohort discovery states.
3. **Metric Conflation**: Risked conflating graph persistence homology ($\beta_1$) with geometric spatial phase winding ($Q_{\text{spatial}}$).

The `cohort_topology_runner` resolves these bottlenecks through bounded, streaming, single-pair processing with explicit metric separation, provenance preservation, and strict adherence to repository guardrails.

---

## 2. Core Architecture and Pipeline Flow

```
   [PairedCohortManifest.json] (from PR #235)
                │
                ▼
   [Manifest Validation Gate]
                │
                ├── Refusal check: no_data, malformed_cohort, insufficient_pairs, ambiguous_matches
                │   (Bypassed only with explicit --diagnostic-only or --allow-insufficient)
                ▼
     [Pair-by-Pair Streamer]  <-- Processes 1 pair at a time; constant memory
                │
         ┌──────┴──────┐
         ▼             ▼
   [Condition A]  [Condition B]
         │             │
         └──────┬──────┘
                │
                ▼
   [Bounded Window Chunker]  <-- shape (channels, samples), bounded by chunk_samples and max_windows
                │
                ▼
    [Topological Analysis]
    ├── Analytic Signal & Phase (Hilbert transform)
    ├── PLV Adjacency Matrix (bivariate phase synchrony)
    ├── Graph Persistent Homology (Ripser filtration sweep -> beta-1, persistence landscape area)
    └── Geometric Spatial Phase Charge (sensor Delaunay triangulation / winding charge)
                │
                ▼
  [Descriptive Cohort Aggregator]
    ├── Paired differences (delta landscape area)
    ├── Subject-level provenance and checksum propagation
    ├── Descriptive non-parametric Wilcoxon test (when empirical N >= min_pairs)
    └── Null-safe serialization (allow_nan=False)
                │
                ▼
  [Deterministic Artifacts]
    ├── cohort_topology_execution_summary.json
    └── cohort_topology_execution_summary.csv
```

---

## 3. Strict Metric Separation

In strict compliance with repository rules:

- **Graph Persistent Homology ($\beta_1$)**: Evaluated on the filtration sweep of the Phase-Locking Value (PLV) adjacency graph. Summarized via `mean_beta1`, `mean_filtration_beta1_max`, and integrated persistence landscape area.
- **Geometric Spatial Phase Charge ($Q_{\text{spatial}}$)**: Computed strictly from 3D sensor coordinates via Delaunay triangulation or 2D grid winding numbers on sensor geometry.
- **Independence Principle**: Graph $\beta_1$ cycle counts and geometric spatial charge are mathematically distinct and never conflated, combined, or substituted for one another.

---

## 4. Scientific Guardrails and Readiness Gating

1. **No Formal Bayes Factor**: The runner computes only descriptive statistics (means, medians, variances, and non-parametric Wilcoxon signed-rank tests). It never computes or claims a formal Bayes factor by itself.
2. **Synthetic Input Invariants**: Synthetic fixtures (e.g. `.npy` or `.csv` test arrays) are explicitly tracked (`is_synthetic = True`). The runner **never emits PASS** on synthetic inputs; runs involving synthetic data are classified as `SYNTHETIC_EVALUATION` or `INCONCLUSIVE_SYNTHETIC_MIXED`.
3. **Execution Refusal**: Execution is refused before loading files if the manifest reports:
   - `no_data`: Zero recordings discovered.
   - `malformed_cohort`: Corrupt headers or unresolvable companion files.
   - `insufficient_pairs`: Empirical paired count falls below `min_pairs` (unless `--allow-insufficient` or `--diagnostic-only` is passed).
   - `ambiguous labels`: Inconsistent or colliding condition matches.
4. **No Consciousness or Clinical Claims**: Adheres to global guardrails forbidding proof claims, consciousness inferences, or clinical efficacy assertions.

---

## 5. CLI Usage and Parameters

```bash
python scripts/cohort_topology_runner.py \
    --manifest artifacts/data_manifests/paired_cohort_manifest.json \
    --output-dir artifacts/cohort_topology \
    --chunk-samples 500 \
    --max-windows 12 \
    --seed 42
```

### Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--manifest`, `--manifest-path` | `Path` | *Required* | Path to input `PairedCohortManifest` JSON. |
| `--output-dir` | `Path` | `artifacts/cohort_topology` | Directory where output JSON and CSV are written. |
| `--chunk-samples` | `int` | `500` | Sample length of each streaming chunk window. |
| `--max-windows` | `int` | `12` | Upper bound on number of windows processed per condition. |
| `--diagnostic-only` | `flag` | `False` | Forces execution for diagnostic purposes even if manifest is invalid or insufficient. |
| `--allow-insufficient` | `flag` | `False` | Allows execution when empirical pairs are fewer than `min_pairs`. |
| `--seed` | `int` | `42` | Deterministic random seed for any stochastic sampling. |

---

## 6. Output Artifacts

### `cohort_topology_execution_summary.json`
Contains cohort-level metadata, per-pair topology records, descriptive aggregations, and scientific notes. Null-safe numbers ensure compliance with JSON standards.

### `cohort_topology_execution_summary.csv`
Flat tabular representation containing one row per processed pair with metrics:
- `pair_key`
- `is_synthetic`
- `finite_status`
- `delta_landscape_area`
- `cond_a_samples`, `cond_a_channels`, `cond_a_sfreq`, `cond_a_mean_beta1`, `cond_a_landscape_area`, `cond_a_spatial_q`
- `cond_b_samples`, `cond_b_channels`, `cond_b_sfreq`, `cond_b_mean_beta1`, `cond_b_landscape_area`, `cond_b_spatial_q`
