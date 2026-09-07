# Streaming Paired-Cohort Topology Execution Subsystem

## Overview

The `cohort_execution` subsystem provides a memory-bounded, local streaming runner for paired electrophysiology cohorts (e.g., awake vs. sedated, baseline vs. drug, or condition-A vs. condition-B). It consumes upstream paired-cohort manifests (`shared/data_loaders/cohort_manifest.py`, PR #235) and persistent-homology backend adapters (`topo_monitor/graph_persistence.py`, PR #238) into a bounded descriptive topology runner without modifying underlying topology algorithms or Bayesian falsification engines.

The subsystem operates strictly locally without network access, processes one paired recording at a time to prevent whole-cohort memory materialization, produces finite null-safe outputs with canonicalized checksum verification, and strictly enforces scientific guardrails.

---

## Architectural Workflow

```
[ PairedCohortManifest JSON ]
           │
           ▼
[ Manifest Readiness Gatekeeper ] ──(Refusal Criteria Met)──► [ REFUSED / Refusal Status Code ]
           │
           │ (Readiness Validated)
           ▼
[ Bounded Streamer: RecordingStreamer ]
   • Reads 1 pair at a time
   • Window-by-window chunking (configurable window_samples / window_duration_s)
   • Configurable step duration, channel limit, and sample limit
   • Memory bounded: no full-cohort or whole-recording matrix materialization
           │
           ▼
[ Window Topology Engine: compute_window_topology ]
   ├─► Hilbert Transform & Instantaneous Phase: θ_i(t)
   ├─► Phase Locking Value (PLV) Adjacency Matrix
   ├─► Graph Persistent Homology:
   │     • H_0 and H_1 Persistence Diagrams via ripser
   │     • Betti-0 and Betti-1 Filtration Sweeps (beta0_summary, beta1_summary)
   │     • Persistence Interval Counts (H0 and H1)
   │     • Integrated Persistence Landscape Area
   └─► Geometric Spatial Phase Charge:
         • Q_spatial (Delaunay triangulation on 3D sensor montage coordinates)
         • Computed ONLY when valid montage coordinates exist; explicit NULL otherwise
         • STRICTLY SEPARATED from graph beta-1
           │
           ▼
[ Descriptive Aggregator & Reporter ]
   • Per-condition descriptive statistics (mean, std, min, max)
   • Paired Persistence Distance: |mean_area(B) - mean_area(A)|
   • Paired Delta Landscape Area: mean_area(B) - mean_area(A)
   • Bounded Memory Telemetry (tracemalloc peak and current memory)
   • Segregated synthetic demo fixtures vs. empirical tracking
   • Canonicalized deterministic output with SHA-256 output_checksum
```

---

## Explicit Execution States

The runner emits one of seven explicit lifecycle states:

| Execution State | Trigger / Semantics |
|-----------------|---------------------|
| `DESCRIPTIVE_READY` | Empirical cohort processed successfully ($\ge \text{min\_pairs}$), descriptive metrics produced. |
| `INSUFFICIENT_PAIRED_SUBJECTS` | Fewer empirical pairs available than `min_pairs` (unless overridden by `--allow-insufficient`). |
| `INCOMPLETE_PROVENANCE` | Manifest declares or recordings contain missing provenance tracking metadata. |
| `MISSING_OPTIONAL_DEPENDENCY` | Required topology dependency (e.g. `ripser`) is unavailable in the environment. |
| `INVALID_INPUT` | Manifest file missing, JSON malformed, or corrupt recording structure. |
| `SYNTHETIC_DEMO_ONLY` | Only synthetic fixture recordings were processed; no empirical subjects present. |
| `NO_DATA` | Manifest contains zero recordings or zero discovered paired subjects. |

---

## Mathematical Separation: Graph Persistence vs. Spatial Charge

To ensure mathematical and physical rigor, the runner maintains strict separation between topological spaces:

* **Graph Persistent Homology ($\beta_0$, $\beta_1$, Landscape Area)**:
  Measures 0-dimensional connected component mergers and 1-dimensional homological cycle loops over a distance filtration sweep $D_{ij} = 1 - \text{PLV}_{ij}$. Computed via `ripser` and `topo_monitor.graph_persistence`.
* **Spatial Topological Charge ($Q_{\text{spatial}}$)**:
  Measures geometric phase-vortex winding defects over physical electrode positions in 3-dimensional space using Delaunay triangulation on scalp sensor coordinates (`topo_monitor.spatial_phase.sensor_spatial_charge`).
* **Strict Montage Guardrail**:
  $Q_{\text{spatial}}$ is **only** evaluated when valid 3D montage coordinates exist for the recording channels. When coordinates are missing, $Q_{\text{spatial}}$ is explicitly set to `null` (`spatial_charge_available=false`). It is **never** conflated with or labeled as graph loop count $\beta_1$.

---

## Bounded Streaming and Configuration

The runner processes one pair at a time using sliding windows, bounded by configurable parameters:

- `--window-samples` / `--window-duration-s`: Window duration in samples or seconds (default: 1024 samples).
- `--step-samples` / `--step-duration-s`: Step duration between sliding windows (default: window size).
- `--channel-limit`: Upper bound on channels processed per window.
- `--sample-limit`: Upper bound on total samples read per recording.
- `--filtration-thresholds`: Thresholds in $[0, 1]$ for filtration sweep.
- `--max-points-per-window`: Maximum samples per TDA window.
- `--max-windows`: Maximum windows streamed per recording.
- `--seed`: Deterministic random seed for reproducible analysis.

---

## Output Contract & Determinism

All outputs are written atomically using temporary files and safe replacement:

1. **`cohort_topology_execution_summary.json`**:
   - `schema`: `"NeuroTopologySim.CohortTopologyExecutionSummary.v2"`
   - `execution_status`: One of the 7 explicit states above.
   - `formal_bayes_factor`: `null` (strictly never calculated).
   - `scientific_pass`: `false` (strictly never emitted).
   - `evidence_class`: `"descriptive_topology_only"`.
   - `provenance_checksum`: SHA-256 of the input manifest.
   - `output_checksum`: SHA-256 computed over the canonicalized deterministic topological results.
   - `descriptive_aggregate`: Condition-level aggregates and persistence distances.
   - `memory_telemetry`: Tracked peak memory in MB.
2. **`cohort_topology_pairs.csv`**:
   Per-pair summary table recording pairing keys, synthetic labels, condition-A/B mean landscape areas, $\Delta \text{landscape\_area}$, and persistence distance.
3. **`cohort_topology_windows.csv`**:
   Window-level detailed table recording per-window $H_0/H_1$ intervals, $\beta_0$, $\beta_1$, landscape area, and $Q_{\text{spatial}}$.

---

## Guardrails and Scientific Limitations

* **No Clinical Claims**: Output metrics are exploratory and descriptive only. They cannot be used for clinical diagnosis, anesthesia depth monitoring, or therapeutic decisions.
* **No Theoretical Proof Claims**: No claim to validate, falsify, or complete any theory of consciousness or Theory of Everything (TOE).
* **No Formal Bayes Factor**: Descriptive metrics do not compute Bayes factors and do not bypass the project's Bayesian falsification engine.
* **Synthetic Segregation**: Fixtures are explicitly tagged `is_synthetic: True`, classified under `SYNTHETIC_DEMO_ONLY`, and excluded from empirical evidence pools.
* **No Scientific PASS**: The runner outputs descriptive statuses and never issues a scientific PASS verdict.
