# ScienceR-Dsim

Integrated topological field simulation + EEG validation system.

## Included
- 3D topology core: Q, Qabs, Q(z,t)
- Defect extraction and worldline tracking
- Reconnection/event detection
- Synthetic validation
- EEG analytic-phase proxies + null-control scaffold (exploratory; see "Scientific status" below)
- Physics hooks (The Well)
- External ecosystem connectors (file/REST/MQTT/WebSocket)
- SQLite registry
- Paper figure generation

## Scientific status (EEG)

EEG metrics emitted by `pipelines/run_eeg.py` are **exploratory analytic-phase
proxies**, not validated consciousness biomarkers and not clinical observables.
The pipeline currently emits two kinds of rows per window:

- `metric_kind = "analytic_phase_proxy"` — Hilbert analytic phase per band
  (delta/theta/alpha/beta/gamma_low), gradient over channel order. The channel
  axis is **not** a true spatial coordinate; this is a coarse proxy.
- `metric_kind = "temporal_phase_proxy"` — legacy direct `np.angle` path,
  retained only as a documented baseline for backward comparison.

When `compute_nulls=True`, `run_eeg` also emits matched null-control rows per
analytic band and window:

- `metric_kind = "null_channel_shuffle"` — channel order permuted (destroys
  inter-channel coupling, preserves per-channel spectra).
- `metric_kind = "null_time_reverse"` — samples reversed (destroys causal
  structure, preserves spectral amplitude).
- `metric_kind = "null_phase_randomized"` — spectrum-preserving phase
  randomization (preserves power spectrum, randomizes phase).

Null rows carry `null_method`, `null_seed` (the base seed argument passed to
`run()`), and `window_null_seed` (a sha256-derived per-window seed, stable
across processes, that was actually used for the null transform) for
traceability. They are deterministic: the same `null_seed` + file + window
always produces identical null rows. These are controls for artifact
sensitivity, not proof of validity. Observed metrics must separate from null
distributions before any structural claim can be made.

**Memory note:** `compute_nulls=True` increases output row count by
approximately 4× (one observed row + three null rows per band per window).
Long recordings should be chunked externally or processed per subject/session.

A montage-aware 2D phase grid is supported by
`validation.analytic_phase.phase_grid_topology_metrics`, but the EEG runner
does not yet build such a grid from real sensor positions; that is future work.

The PCIst-style complexity column has been renamed `pcist_proxy` to make
clear it is **not** the canonical PCIst measure. The legacy `pcist_surrogate`
function is retained as a deprecated alias.

Promotion of any EEG-derived Q / Qabs / f_dress to a validated structural
finding requires (a) montage-aware phase-grid topology, (b) null-control
comparison, and (c) labeled state-change validation (e.g. LOC/ROC).

## Note
Datasets are not embedded. Place them under `data/raw/` using the paths in `data/README.md`.

## Quick start

### Core quick start
```bash
pip install -r requirements.txt
make smoke-core
make test-core
```

Direct equivalents if `make` is unavailable:

```bash
python main.py --mode synthetic
python -m pytest tests/ -v --tb=short
```

### Awareness Studio setup
```bash
cd apps/awareness_studio
pip install -e '.[dev]'
python -m pytest tests/ -v --tb=short
```

### Full-stack contributors
Install root requirements and Awareness Studio dev extras before running:

```bash
make test-all
```

## Contributor Setup Matrix

| Workstream | Required install commands | Verification command |
| --- | --- | --- |
| Core pipelines | `pip install -r requirements.txt` | `pytest -q tests` |
| Awareness Studio | `pip install -e apps/awareness_studio`<br>`pip install -e "apps/awareness_studio[dev]"` | `pytest -q apps/awareness_studio/tests` |
| Full-stack contributor | `pip install -r requirements.txt`<br>`pip install -e apps/awareness_studio`<br>`pip install -e "apps/awareness_studio[dev]"` | `pytest -q tests && pytest -q apps/awareness_studio/tests` |

For setup details and isolation recommendations, see [docs/contributing.md](docs/contributing.md). If you are working in the UI surface, also review [apps/awareness_studio/README.md](apps/awareness_studio/README.md).

## External systems and live sensors
- Configure connectors in `config/defaults.yaml` under `external.connectors`.
- Supported connector types:
  - `file` for newline-delimited JSON sensor streams (works out of the box)
  - `rest` for HTTP JSON polling
  - `mqtt` for topic ingestion (requires `paho-mqtt`)
  - `websocket` for socket streams (requires `websocket-client`)
- External ingestion logs records and metrics into SQLite (`sensor_data`, `metrics`, `runs`) for traceability and reproducibility.

## Montage-aware phase-grid topology
- Enable with `compute_phase_grid_topology=True` in EEG runner.
- Uses sensor coordinates/montage geometry and Delaunay triangle winding on sensor space.
- `analytic_phase_proxy` remains channel-order proxy; `phase_grid_topology` is geometry-aware sensor-space topology.
- Still exploratory; requires null-control and state-label validation before scientific promotion.
- Future work: source-space topology and LOC/ROC benchmark.

