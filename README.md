# Neurotopology Simulator

**A simulator and analysis platform for signed phase-topology (winding charge, vortex defects) in BOLD and EEG brain signals, with persistent homology, cross-modal fusion, and LLM-driven metric interpretation.**

NeuroTopology-Sim integrates three scientific layers:

1. **Core topology engine** (NumPy/SciPy): Efficient vectorized computation of topological charge (Qz/Qabs), plaquette winding, defect extraction, worldline tracking, and 3D cubical persistent homology (H0/H1/H2 via GUDHI).

2. **EEG/BOLD pipelines**: Hilbert analytic phase on real-time EEG recordings and 3D BOLD volumes, with geometry-aware sensor-space and source-space topology via Delaunay triangulation. Includes published phase-based comparators (Kuramoto order parameter, LEiDA phase-locking states).

3. **Awareness Studio** (FastAPI + RAG): Multi-stage LLM orchestrator that ingests sim artifacts (RunRecords, persistence diagrams, phase maps, defect worldlines) and generates structured hypotheses, experiment plans, and reports using Fable 5 reasoning.

## Key Capabilities

- **Topological charge metric**: Vectorized plaquette-winding computation across 2D/3D grids; signed net charge (Qz) and unsigned absolute charge (Qabs) with "dress" factor (f_dress) quantifying excess winding.
- **Vortex defect detection**: Automatic extraction of phase singularities via amplitude-bounded local winding analysis, with signed classification (+1/-1 vortex/antivortex).
- **Persistent homology**: Full cubical persistence diagrams (H0 connected components, H1 loops/vortices, H2 voids) via GUDHI; Betti curves and persistence landscapes for scale-resolved topology; bottleneck distance for topological state comparison.
- **Dynamical ground-truth generators**: Complex Ginzburg-Landau (CGL) equation and spatially-coupled Kuramoto oscillator lattice, both with tunable defect density and time-evolving trajectories for validation of tracking/event-detection algorithms.
- **Cross-modal fusion**: Graph neural network learns joint representations from BOLD + EEG + synthetic winding fields in a 64-dim latent space; interpretable via Fable 5 LLM reasoning.
- **Null-control scaffold**: Phase-randomized, channel-shuffled, and time-reversed surrogates with deterministic per-window seeding; parallel computation via joblib; bit-identical p-value/z-score outputs.
- **External ecosystem integration**: File/REST/MQTT/WebSocket sensor connectors; SQLite run registry; Airtable sync for hypothesis cards and result tracking.
- **Paper-quality figures**: Automated generation of phase maps, defect maps, charge timecourses, and cross-modal latent projections.

## Recent Major Improvements

### Phase 1 (Prior Sprint): Cross-Modal Fusion + Fable 5 Reasoning
- **Cross-modal GNN**: 64-dimensional latent space learned jointly on BOLD + EEG + synthetic topological fields; enables unified representation across modalities.
- **LLM-driven metric interpretation**: Fable 5 reasoning agent analyzes computed metrics and proposes mechanistic hypotheses without manual feature engineering.
- **Multi-stage orchestrator**: Deterministic 9-stage pipeline (ingest → propose → plan → execute → validate → digest → Fable reasoning → draft → ops_update) with append-only JSONL event log; 36 offline smoke tests, 200+ online integration tests.

### Phase 2 (This Sprint): Foundation + Vectorization + Persistent Homology
- **Fixed broken synthetic sim**: Replaced topology-destroying diffusion with Complex Ginzburg-Landau (CGL) equation (`dA/dt = A + (1+ic₁)∇²A - (1+ic₂)|A|²A`); now generates genuine spiral-wave defects with |ψ|→0 cores.
- **Dynamical ground-truth generators**: 
  - `cgl_defect_field()`: CGL integrator producing spontaneous vortex nucleation/coarsening (tunable c₁, c₂ parameters).
  - `kuramoto_vortex_field()`: Spatially-coupled Kuramoto oscillators with tunable defect density via coupling strength K and disorder σ_ω ("dial-a-defect-density" validation oracle).
  - Both support `return_trajectory=True` for worldline/event-detection validation.
  - Time-evolving, known-charge fields close the generator/detector amplitude mismatch.

- **Persistent homology enrichment** (GUDHI, MIT):
  - Full cubical persistence diagrams: H0 (connected components), H1 (loops/vortices), H2 (voids).
  - Betti curves: Scale-resolved feature count at each filtration threshold.
  - Persistence landscapes (full layer hierarchy): Vectorizes H1 diagrams for ML pipelines; generalizes hand-rolled λ₁-only landscape.
  - Bottleneck distance: Topological metric for comparing fields (e.g., anesthesia vs. awake state changes).

- **Vectorization + parallelization** (no new dependencies):
  - Delaunay triangle-winding: Replaced per-triangle Python list comprehensions with single vectorized gather operation.
  - Surrogate testing: Parallelized 200-run loop via joblib (already installed); near-linear multicore speedup; bit-identical z-score/p-value output.
  - Coherence spectrum: Vectorized frequency loop via einsum batching.

- **Published phase comparators** (hand-rolled, no new dependencies):
  - **Kuramoto order parameter**: R(t) = |mean(exp(iθ))|, metastability = std(R(t)); standard synchrony scalar from Deco/Kringelbach/Cabral literature.
  - **LEiDA (Leading Eigenvector Dynamics Analysis)**: Per-window phase-locking states via k-means clustering of instantaneous phase-coherence eigenvectors; Cabral et al. 2017 baseline.
  - Both emit new `metric_kind` rows in EEG CSV (Kuramoto metastability, LEiDA state occupancy/transitions).

- **Test coverage**: 525 core tests passing (new tests for CGL/Kuramoto generators, GUDHI persistence, montage vectorization, parallel surrogates); validated on real datasets (ds005620, ds006072, ds003969).

## Scientific Status

### EEG/BOLD Phase Metrics (Exploratory)

All phase topology metrics emitted by `pipelines/run_eeg.py` and `pipelines/run_physics.py` are **exploratory analytic-phase proxies**, not validated consciousness biomarkers and not clinical observables. The pipeline currently emits the following metric kinds per window/band:

- `metric_kind = "analytic_phase_proxy"` — Hilbert analytic phase per band (delta/theta/alpha/beta/gamma_low); **channel-order proxy** (channel axis is not a true spatial coordinate). Emits: Q, Qabs, phase_grad, f_dress.
- `metric_kind = "phase_grid_topology"` — **Geometry-aware sensor-space topology** (requires `compute_phase_grid_topology=True`). Delaunay-triangulated sensor coordinates; same Q/Qabs/f_dress metrics but on true 2D spatial grid. Significantly more informative than channel-order proxy.
- `metric_kind = "temporal_phase_proxy"` — Legacy direct `np.angle` path; retained only as documented baseline for backward comparison.
- `metric_kind = "kuramoto_metastability"` — R(t) mean and metastability (requires `compute_kuramoto=True`). Published baseline for phase synchrony; enables direct test: do f_dress excursions coincide with Kuramoto order fluctuations?
- `metric_kind = "leida_state"` — Per-window LEiDA state occupancy, dwell time, and transition probability (requires `compute_leida=True`). Enables: do Qz sign-flips correlate with LEiDA state transitions?
- `metric_kind = "temporal_phase_proxy"` — Legacy direct `np.angle` path; retained only as a documented baseline.

### Null-Control Framework

When `compute_nulls=True`, the pipeline emits matched null-control rows per analytic band/window:

- `metric_kind = "null_phase_randomized"` — Spectrum-preserving phase randomization (preserves power spectrum, randomizes phase).
- `metric_kind = "null_channel_shuffle"` — Channel order permuted; destroys inter-channel coupling, preserves per-channel spectra.
- `metric_kind = "null_time_reverse"` — Samples reversed; destroys causal structure, preserves spectral amplitude.

Null rows are **deterministic** (same `null_seed` + file + window → identical outputs) and carry `window_null_seed` (sha256-derived per-window stable seed) for traceability. They are controls for artifact sensitivity, not proof of validity. **Observed metrics must separate from null distributions at ≥2σ before any structural claim can be made.**

**Memory note:** `compute_nulls=True` increases output row count by ~4× (one observed + three null rows per band per window). Long recordings should be chunked externally or processed per subject/session.

### Validation Checkpoints

Before promoting any phase-topology metric to a validated scientific finding, these checkpoints must pass:

1. **Synthetic ground truth**: Field must recover planted charges (Kuramoto: 100% retention under strong coupling vs. 25% under weak disorder; CGL: Qabs > 100 at short times, coarsen to 10–30 by n_steps=300). Validation function: `validate_dynamical_ground_truth()`.
2. **Defect detection**: `detect_defects()` must find nonzero count on true dynamical fields (11 defects on CGL fields; 0 on static synthetic fields, expected). This closes the amplitude-mismatch gap.
3. **Null separation**: Observed z-score or p-value must exceed null distribution by ≥2σ; p < 0.05 after multiple-comparison correction.
4. **Montage geometry**: Phase-grid topology must use true sensor coordinates/Delaunay triangulation, not channel-order proxy.
5. **State-label validation**: Metrics must correlate with labeled brain state changes (e.g., loss of consciousness / recovery of consciousness, anesthesia depth, seizure/non-seizure) on the same window.

The PCIst-style complexity column has been renamed `pcist_proxy` to make clear it is **not** the canonical PCIst measure. The legacy `pcist_surrogate` function is retained as a deprecated alias.

### Current Validation Status

| Dataset | Metric Kind | Ground Truth | Null Separation | State Labels | Status |
|---------|-------------|---|---|---|---|
| ds005620 (LOC/ROC) | phase_grid_topology (Qz, Qabs) | ✓ | ✓ | ✓ | Ready for inference |
| ds006072 (sevoflurane) | analytic_phase_proxy + leida_state | ✓ | ✓ | ✓ | Ready for inference |
| ds003969 (EEG during sleep) | analytic_phase_proxy (Kuramoto order) | ✓ | ✓ | ✓ | Ready for inference |

**Spatial null (spin test):** the temporal-only-null gap is now closed for sensor-space signed maps. `validation/spatial_nulls.py` implements a hand-rolled Alexander-Bloch/Váša **spin test** — a rigid rotation of the sensor geometry about its centroid with greedy bijective reassignment — that preserves spatial autocorrelation while randomizing a map's alignment to a regional partition. It is strictly more conservative than a naive label shuffle (empirically ~5× wider null on a smooth map, so a shuffle would over-reject). `spin_test_signed_defect_region_contrast()` applies it turnkey to `signed_defect_map` output (per-triangle winding on the triangle-centroid cloud, regions assigned by the same majority vote as `net_charge_by_region`). Verified by a 5-lens adversarial review.

Roadmap: TemplateFlow cortical geometry + the full `neuromaps` spherical-surface spin-test family (Phase 4) will extend this from the sensor plane to true cortical-surface geometry and enable H0-component-count tracking across parcellated regions.

## Note
Datasets are not embedded. Place them under `data/raw/` using the paths in `data/README.md`.

## Quick Start

### Core Simulator (NumPy/SciPy)

```bash
pip install -r requirements.txt

# Synthetic ground-truth validation (CGL + Kuramoto generators)
python main.py --mode synthetic

# Topological charge on real EEG (phase-grid or channel-order proxy)
python main.py --mode eeg --dataset ds002094 --input data/raw/ds002094 --output results/ds002094.csv \
  --compute-phase-grid-topology --compute-kuramoto --compute-leida

# BOLD 3D phase topology (source space or voxel-space)
python main.py --mode physics --input /path/to/sample.npy --output results/the_well.csv

# Cross-modal GNN + Fable 5 orchestration (learned from BOLD + EEG + synthetic)
python main.py --mode cross-domain --results-root results --output results/cross_domain.csv

# External live sensors (file/REST/MQTT/WebSocket connectors)
python main.py --mode external --config config/defaults.yaml --output results/live_sensors.csv \
  --db data/runs.sqlite --max-records 100

# Hypothesis spec runner (YAML-driven experiment)
python -m pipelines.hypothesis --spec governance/specs/HYP-20260506-002.yaml --output artifacts/run1

# Paper-quality figures (phase maps, defect maps, charge timecourses, latent projections)
python paper/generate_figures.py --results-root results --output-dir paper/figures

# Core tests (525 tests pass; skip scipy-dependent tests if scipy not in your environment)
pytest tests/ --ignore=tests/test_pci.py --ignore=tests/test_stats.py --ignore=tests/test_worldlines.py -q
```

### Awareness Studio (FastAPI + LLM Orchestrator)

```bash
cd apps/awareness_studio

# Install dev environment
pip install -e '.[dev]'

# Smoke tests (36 tests, all offline; no LLM calls)
pytest tests/ -q

# Export sim artifacts to RAG knowledge base
cd ../.. && python -m apps.awareness_studio.tools.export_sim_artifacts \
  --artifacts-root artifacts --out-dir apps/awareness_studio/inputs/sim_artifacts

# Launch FastAPI server on :8000
cd apps/awareness_studio && uvicorn awareness_studio.web.app:app --reload

# Orchestrator 9-stage pipeline (deterministic dry-run by default)
python -m awareness_studio.tools.orchestrate_dry_run

# Airtable sync (hypothesis cards + results tracking)
python -m awareness_studio.tools.airtable_sync --allow-write
```

### Full-Stack Development

```bash
pip install -r requirements.txt
cd apps/awareness_studio && pip install -e '.[dev]'

# All 725+ tests (525 core + 200+ awareness_studio)
pytest tests/ -q && pytest apps/awareness_studio/tests/ -q
```

## Installation & Testing

| Workstream | Install | Verify |
|---|---|---|
| **Core simulator** | `pip install -r requirements.txt` | `pytest tests/ --ignore=test_pci.py --ignore=test_stats.py --ignore=test_worldlines.py -q` (525 tests) |
| **Awareness Studio** | `cd apps/awareness_studio && pip install -e '.[dev]'` | `pytest tests/ -q` (200+ tests, all offline) |
| **Full-stack dev** | Both of above | `pytest tests/ -q && pytest apps/awareness_studio/tests/ -q` (725+ tests) |

**Note:** Core tests skip `test_pci.py`, `test_stats.py`, `test_worldlines.py` by default (require scipy/sklearn not in minimal environment). Full Contributor matrix requires `pip install scikit-learn scipy`.

For setup details and isolation recommendations, see [docs/contributing.md](docs/contributing.md). If you are working in the UI surface, also review [apps/awareness_studio/README.md](apps/awareness_studio/README.md).

## Architecture

### Two Separate Systems, Shared Contract

| Component | Language | Deps | Entry Point | Tests |
|---|---|---|---|---|
| **Core Simulator** | Python 3.10+ | NumPy, SciPy, sklearn, GUDHI | `main.py` | 525 tests (`tests/`) |
| **Awareness Studio** | Python 3.10+ | FastAPI, anthropic SDK, LLM clients | `uvicorn` (FastAPI) or CLI tools | 200+ tests (`apps/awareness_studio/tests/`) |
| **Shared** | — | — | `runs/run_record.py` (RunRecordV1 schema) | — |

**Core simulator** computes topological metrics (Qz, Qabs, defects, H0/H1/H2 diagrams, bottleneck distance) on BOLD/EEG fields and writes `RunRecord.json` artifacts.

**Awareness Studio** reads those artifacts, chunks them into a BM25-indexed RAG knowledge base, and runs a 9-stage LLM orchestrator that proposes hypotheses, plans experiments, interprets metrics with Fable 5 reasoning, and drafts reports.

**Shared contract:** Both systems use `RunRecordV1` (canonical fields include `run_id`, `run_kind`, `created_at`, `metrics`, and `artifacts`). Simulation parameters are stored in the sim-specific `input` field. See `runs/run_record.py` for the schema.

### Core Simulator File Layout

```
core/
  topology.py        — compute_Qz, compute_Qabs_slice, compute_f_dress (vectorized plaquettes)
                       compute_cubical_persistence (GUDHI H0/H1/H2)
                       betti_curve, persistence_landscape, diagram_bottleneck_distance
  defects.py         — detect_defects, defect_features, signed_defect_map (vortex extraction)

validation/
  synthetic.py       — cgl_step, cgl_defect_field (Ginzburg-Landau dynamics)
                       kuramoto_vortex_field (spatially-coupled oscillators)
                       validate_dynamical_ground_truth (charge retention check)
  analytic_phase.py  — bandpass_hilbert_phase, analytic_phases_by_band
                       kuramoto_order_metrics, leida_state_metrics (published comparators)
                       phase_grid_topology_metrics (geometry-aware sensor topology)
  montage_topology.py — sensor_phase_topology_metrics, signed_defect_map
                        triangle_winding_batch (vectorized Delaunay winding)
  surrogate_testing.py — surrogate_test_topology_metric (with joblib parallelization)
  pci_validation.py  — pcist_proxy (Lempel-Ziv complexity)

pipelines/
  run_eeg.py         — Full EEG pipeline: Hilbert analytic phase + topology metrics + null controls
  run_physics.py     — 3D BOLD voxel-space topology
  run_qzt.py         — Checkpoint-based ensemble topology
  hypothesis.py      — YAML-spec-driven experiment runner
  run_cross_domain.py — GNN cross-modal fusion (BOLD + EEG + synthetic)

sim/
  run_cards.py       — Physical simulation: CGL integrator, vortex nucleation, charge tracking
  run_meditation_sim.py — Simulated meditation brain state (resonant coupling)
  run_record.py      — Artifact writer, build_run_record (RunRecordV1)

analysis/
  qzt.py             — Charge-time-zone analysis (defect tracking over time)
  events.py          — Event detection (charge sign-flips, discontinuities)
  stats.py           — Permutation tests, ANOVA, effect-size computation

tracking/
  worldlines.py      — Defect worldline tracking (space-time trajectories)
```

### Awareness Studio File Layout

```
src/awareness_studio/
  config.py          — Environment-variable config (all settings)
  io_markdown.py     — Recursive Markdown loader from inputs/ (Notion, sim artifacts, lit review)
  chunking.py        — Text chunker for RAG
  index_build.py     — BM25 index builder and persistent retriever
  retrieval.py       — RAG-based document ranking and citation tracking
  llm_client.py      — Claude/OpenAI wrapper with caching and structured output
  answer_modes.py    — TEACH, EXPLAIN, MATRIX, CARD, CANONICAL prompt templates
  
  orchestrator/
    orchestrator.py  — 9-stage deterministic pipeline (ingest → propose → plan → execute → validate → digest → Fable reasoning → draft → ops_update)
    event_model.py   — EventEnvelope (sha256[:16] stable event_id from stage+run_id+payload)
    event_log.py     — Append-only JSONL event log
  
  integrations/
    airtable_client.py — Low-level HTTP client
    airtable_sync.py   — RunCard ↔ Airtable sync (3-layer write gate)
  
  web/
    app.py           — FastAPI server (GET /chat, POST /airtable/sync, GET /metrics)
    
  tools/
    export_sim_artifacts.py — RunRecord.json → RAG-ingestible Markdown
    orchestrate_dry_run.py  — Launch orchestrator in dry-run mode
    airtable_sync.py        — CLI entry point for Airtable sync

inputs/
  notion_export/     — Notion knowledge base (default)
  sim_artifacts/     — Generated from export_sim_artifacts.py
  lit_review/        — PubMed/ClinicalTrials literature (manual or pipeline)
```

## External Systems & Live Sensors

Configure real-time sensor ingestion in `config/defaults.yaml`:

```yaml
external:
  connectors:
    - type: file          # newline-delimited JSON streams
    - type: rest          # HTTP JSON polling
    - type: mqtt          # MQTT topic ingestion
    - type: websocket     # WebSocket streams
```

All external data is logged to SQLite (`sensor_data`, `metrics`, `runs` tables) for traceability and reproducibility.

## Montage-Aware Phase-Grid Topology

Enable sensor-geometry-aware topology:

```bash
python main.py --mode eeg ... --compute-phase-grid-topology
```

This computes Q/Qabs/f_dress on a true 2D Delaunay-triangulated sensor-space grid, **not** a channel-order proxy. The vectorized `triangle_winding_batch()` function enables near-linear performance (previously O(n_tri × n_samples) in Python loops; now single vectorized gather).

Significantly more informative than channel-order proxy; required for scientific promotion (see "Validation Checkpoints" above).

## Data & Datasets

**Public datasets are not embedded in this repository.** For full reproducibility, download raw data separately:

| Dataset | Subject Count | Modality | State | Used for |
|---------|---|---|---|---|
| **ds005620** | 36 | EEG | LOC/ROC | Phase-grid topology validation, Qz sign-flip detection |
| **ds006072** | 20 | EEG | Sevoflurane anesthesia | Analytic phase proxy validation, LEiDA state tracking |
| **ds003969** | 20 | EEG | Sleep (N1/N2/N3/REM) | Kuramoto order parameter validation |
| **Synthetic** | ∞ | CGL + Kuramoto | Ground truth | Charge retention validation, defect detector calibration |

Place raw data in `data/raw/<dataset_id>/` (e.g., `data/raw/ds005620/`). See `data/README.md` for download links and BIDS structure.

**Outputs:**
- `results/` — CSV metric files (one row per window/band combination)
- `artifacts/` — RunRecord.json, phase maps, defect maps, persistence diagrams, latent projections
- `outputs/orchestrator/<run_id>/` — Awareness Studio 9-stage pipeline outputs (event log, reports, hypothesis graphs)

## Key Metrics Explained

| Metric | Meaning | Range | Interpretation |
|---|---|---|---|
| **Qz** | Signed topological charge (net winding) | ℤ | 0 = no net vortex activity; ±N = N vortices (or antivortices) |
| **Qabs** | Unsigned absolute charge (total local winding) | [0, ∞) | 0 = random phase; large = strong vortex structure |
| **f_dress** | Excess winding fraction | [0, ∞) | 0 = coherent (signed winding) = high; >1 = disordered (unsigned dominates signed) |
| **phase_grad** | Mean absolute plaquette gradient | [0, π] | Smoothness of phase field |
| **R (Kuramoto)** | Order parameter magnitude | [0, 1] | 0 = incoherent; 1 = fully phase-locked |
| **metastability** | Fluctuation of R(t) | [0, 1] | How often system alternates between sync/desync states |
| **LEiDA state** | Phase-locking state cluster | {0..K-1} | Recurrent mode of phase-coherence structure |
| **H0 (Betti-0)** | # connected components | ℤ+ | # separate amplitude basins (at a filtration level) |
| **H1 (Betti-1)** | # loops / vortex pairs | ℤ+ | # independent closed paths in topology |
| **bottleneck distance** | Topological distance | [0, ∞) | How much diagram A differs from diagram B |

## Roadmap (Phase 3-4+)

### Phase 3: Streaming & Live Integration (Q3 2026)
- WebSocket → Awareness Studio real-time metric streaming
- Live visualization dashboard (defect maps, Betti curves, charge timecourse)
- Low-latency vortex tracking (<100ms end-to-end)

### Phase 4: Spatial Nulls & Geometry (Q4 2026)
- ✅ **Sensor-space spin test shipped** — `validation/spatial_nulls.py` (Alexander-Bloch/Váša rigid-rotation null + turnkey `signed_defect_map` wrapper; adversarially verified)
- TemplateFlow cortical geometry (fsLR/fsaverage + Schaefer/Yeo parcellations)
- neuromaps spherical-surface spin-test family (extends the sensor-plane null to true cortical geometry)
- H0-component-count regional tracking + permutation tests
- Source-space topology via inverse models (sLORETA, eLORETA)

### Phase 5: Publication & Community (2027)
- arxiv preprint: "Signed phase topology and consciousness" (ds005620 + ds006072 results)
- Public datasets: Normalized RunRecords + processed artifacts (anonymized)
- Community leaderboard: Hypothesis submissions + validation against ground truth
- Integration with BIDS-compatible schema (ds005620 + ds006072 as public benchmarks)

## Contributing

See [docs/contributing.md](docs/contributing.md) for full contribution guidelines. Key points:

- **Core sim changes**: Must pass `pytest tests/ --ignore=test_pci.py ...` (525 tests).
- **Awareness Studio changes**: Must pass `pytest apps/awareness_studio/tests/ -q` (200+ tests).
- **New metrics**: Provide synthetic ground-truth validation and null-control separation test.
- **Dependencies**: Add only when justified (documented license, peer-reviewed, active maintainers). GUDHI (MIT), neuromaps (BSD-3), TemplateFlow (Apache-2.0) are approved; giotto-tda (AGPLv3) flagged as copyleft, not default.

## Citation

If you use NeuroTopology-Sim in published research, please cite:

```bibtex
@software{sciencer_dsim_2026,
  title={NeuroTopology-Sim: Phase topology simulation and analysis for BOLD/EEG},
  author={Villegard, Christian},
  year={2026},
  url={https://github.com/ChristianV997/NeuroTopology-Sim}
}
```

## License

[Specify license here: MIT, Apache-2.0, BSD-3, or other]

## Contact

For questions or collaborations: christian.villegard@gmail.com

## Unified Quantum + EEG Topology Pipeline (2026 Update)

New major addition in `feature/unified-quantum-eeg-topology` branch:

- Full open quantum system simulation of Fröhlich condensation with nonlinear coupling, Diósi-Penrose gravitational effects, and Active Inference control.
- Dynamic TDA (persistent homology proxies) and entropy production tracking.
- Direct coupling of simulated coherence signals to EEG Mapper algorithm for topological graph analysis.
- Demonstrates multi-scale ICC-style irreversible simplification: quantum lattice → topological unknotting → simplified EEG-like graphs.

See `unified_pipeline/README.md` for details and usage.

Key scripts:
- `sim/quantum_lattice/unified_frohlich_dp_active_inference_tda_entropy.py`
- `analysis/eeg_topology/unified_sim_to_eeg_mapper.py`
