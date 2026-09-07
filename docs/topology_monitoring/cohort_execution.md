# Streaming Paired-Cohort Topology Execution Subsystem

## Overview

The `cohort_execution` subsystem provides a memory-bounded, local streaming runner for paired electrophysiology cohorts (e.g. awake vs. sedated, baseline vs. drug, or condition-A vs. condition-B). It connects upstream paired-cohort manifests (`shared/data_loaders/cohort_manifest.py`, PR #235) with persistent-homology backend adapters (`topo_monitor/graph_persistence.py`, PR #238) and spatial phase topological analysis (`topo_monitor/spatial_phase.py`).

The subsystem operates strictly locally without network access, preserves provenance metadata, stream-processes recordings window-by-window, and produces null-safe, finite descriptive summaries without emitting scientific PASS claims or formal Bayes factors.

---

## Architectural Workflow

```
[ PairedCohortManifest JSON ]
           │
           ▼
[ Manifest Readiness Gatekeeper ] ──(Refusal Criteria Met)──► [ REFUSED Summary JSON / Exit 2 ]
           │
           │ (Readiness Validated)
           ▼
[ Bounded Streamer: RecordingStreamer ]
   • Reads 1 pair at a time
   • Window-by-window chunking (window_samples=1024)
   • Memory bounded: no full-cohort materialization
           │
           ▼
[ Window Topology Engine: compute_window_topology ]
   ├─► Hilbert Transform & Instantaneous Phase: θ_i(t)
   ├─► Phase Locking Value (PLV) Adjacency Matrix
   ├─► Graph Persistent Homology:
   │     • H_1 Persistence Diagrams
   │     • Betti-1 Filtration Sweep (beta1_max, mean_beta1)
   │     • Integrated Persistence Landscape Area
   └─► Geometric Spatial Topological Charge:
         • Q_spatial (Delaunay triangulation on 3D sensor montage or 2D grid)
         • STRICTLY SEPARATE from Graph beta_1
           │
           ▼
[ Descriptive Aggregator & Reporter ]
   • Per-condition descriptive statistics (mean, std, min, max)
   • Paired Delta Landscape Area: mean_area(B) - mean_area(A)
   • Descriptive Non-Parametric Wilcoxon Signed-Rank Test (N >= 2 empirical pairs)
   • Segregated synthetic fixture vs. empirical tracking
   • Atomic, null-safe JSON and CSV output
```

---

## Readiness Gates and Refusal Contract

Before reading any recording files from disk, the runner validates the manifest readiness. Normal execution is refused for:

1. **`no_data`**: The manifest reports zero recordings or zero discovered pairs.
2. **`malformed`**: The manifest root is corrupt or contains unparseable entries.
3. **`insufficient_pairs`**: The count of empirical pairs is below `min_pairs` (default 2), unless explicitly bypassed via `--allow-insufficient`.
4. **`ambiguous_labels`**: Unresolvable condition matches or ambiguous condition tags exist.
5. **`incomplete_provenance`**: Discovered recordings lack required provenance origin tracking.

### Diagnostic-Only Mode

Passing `--diagnostic-only` evaluates manifest readiness and prints refusal diagnostics without opening or streaming recording files. It exits with code `0` if the manifest is ready, or code `2` if refusal criteria are triggered.

---

## Mathematical Separation: Graph Persistence vs. Spatial Charge

To ensure mathematical and physical rigor, the runner maintains strict separation between topological spaces:

* **Graph Persistent Homology ($\beta_1$, Landscape Area)**:
  Measures 1-dimensional homological cycle loops over a distance filtration sweep $D_{ij} = 1 - \text{PLV}_{ij}$. Computed via `ripser` through `topo_monitor.graph_persistence`.
* **Spatial Topological Charge ($Q_{\text{spatial}}$)**:
  Measures geometric phase-vortex winding defects over physical electrode positions in 3-dimensional space using Delaunay triangulation on scalp sensor coordinates, or over 2-dimensional sensor grids.
* **Separation Rule**:
  $Q_{\text{spatial}}$ is **never** conflated with or labeled as graph loop count $\beta_1$. Both metrics are calculated via independent mathematical pathways and reported in distinct fields.

---

## CLI Reference

The CLI entrypoint is located at `scripts/run_cohort_topology.py`.

```bash
python scripts/run_cohort_topology.py \
  --manifest path/to/cohort_manifest.json \
  --output-dir artifacts/cohort_topology \
  --window-samples 1024 \
  --chunk-size 4096 \
  --max-windows 10 \
  --seed 42
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--manifest` | *Required* | Path to paired cohort manifest JSON file |
| `--output-dir` | `artifacts/cohort_topology` | Output directory for summaries and CSV tables |
| `--window-samples` | `1024` | Window duration in samples for persistence computation |
| `--chunk-size` | `4096` | Streaming buffer chunk size in samples |
| `--max-windows` | `None` | Optional upper bound on windows processed per recording |
| `--diagnostic-only` | `False` | Validate manifest readiness without streaming data |
| `--allow-insufficient`| `False` | Allow execution when empirical pairs are below threshold |
| `--seed` | `42` | Random seed for deterministic descriptive analysis |

### Exit Codes

* `0`: Execution succeeded, or diagnostic-only check passed without refusal.
* `2`: Manifest readiness check failed and execution was refused (or diagnostic-only refusal).
* `1`: Unexpected exception or fatal runtime error.

---

## Output Artifacts

All outputs are written atomically to `--output-dir` using temporary files and safe replacement:

1. **`cohort_topology_execution_summary.json`**:
   Comprehensive JSON summary complying with strict JSON syntax (`allow_nan=False`). Non-finite floats are converted to `null`.
2. **`cohort_topology_pairs.csv`**:
   Per-pair summary table recording pairing keys, synthetic labels, condition-A/B mean landscape areas, and $\Delta \text{landscape\_area}$.
3. **`cohort_topology_windows.csv`**:
   Window-level detailed table recording per-window $\beta_1$, landscape area, and $Q_{\text{spatial}}$.

---

## Guardrails and Scientific Limitations

* **No Clinical Claims**: Outputs are purely descriptive topological summaries and cannot be used for clinical diagnosis, depth-of-anesthesia monitoring, or medical decisions.
* **No Proof Claims**: Persistent homology changes do not prove any specific theoretical model or theory of consciousness.
* **No Formal Bayes Factor**: Exploratory non-parametric tests (e.g. descriptive Wilcoxon signed-rank test) are labeled descriptive only and do not bypass the project's Bayesian falsification engine.
* **Synthetic Segregation**: Fixture recordings are explicitly labeled `is_synthetic: True` and segregated from empirical descriptive aggregates.
* **Never Emits Scientific PASS**: The subsystem records descriptive execution status (`VALID_COHORT_PROCESSED`, `INSUFFICIENT_PAIRS_PROCESSED`, `SYNTHETIC_EVALUATION`, `REFUSED`) and never issues a scientific PASS verdict.
