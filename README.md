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
```bash
pip install -r requirements.txt
python main.py --mode synthetic
python main.py --mode qzt --input data/checkpoints
python main.py --mode eeg --dataset ds002094 --input data/raw/ds002094 --output results/ds002094.csv --compute-pci
python main.py --mode physics --input /path/to/sample.npy --output results/the_well.csv
python main.py --mode cross-domain --results-root results --output results/cross_domain.csv
python main.py --mode external --config config/defaults.yaml --output results/live_sensors.csv --db data/runs.sqlite --max-records 100
python paper/generate_figures.py --results-root results --output-dir paper/figures
```

`--mode qzt` writes `results/qzt.csv`, `results/events.csv`, and `results/worldlines.json`.

## External systems and live sensors
- Configure connectors in `config/defaults.yaml` under `external.connectors`.
- Supported connector types:
  - `file` for newline-delimited JSON sensor streams (works out of the box)
  - `rest` for HTTP JSON polling
  - `mqtt` for topic ingestion (requires `paho-mqtt`)
  - `websocket` for socket streams (requires `websocket-client`)
- External ingestion logs records and metrics into SQLite (`sensor_data`, `metrics`, `runs`) for traceability and reproducibility.
