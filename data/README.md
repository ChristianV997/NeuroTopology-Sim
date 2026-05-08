Place data here:

- `data/raw/ds002094`
- `data/raw/ds005620`
- `data/raw/ds001787`
- `data/raw/ds003969`
- `data/raw/ds003816`
- `data/raw/physionet_gaba`
- `data/raw/the_well`
- `data/checkpoints` for VHPT / ICFT checkpoints

## EEG metrics: scientific status

The EEG pipeline (`pipelines/run_eeg.py`) emits **exploratory analytic-phase
proxies**, not validated consciousness biomarkers. Each window-row carries a
`metric_kind` column:

- `analytic_phase_proxy` — band-specific Hilbert analytic phase, gradient over
  channel order. Channel index is not a true spatial coordinate.
- `temporal_phase_proxy` — legacy `np.angle` direct path; retained as a
  documented baseline for backward comparison only. Not a valid neural
  phase field.
- `null_channel_shuffle` / `null_time_reverse` / `null_phase_randomized` —
  deterministic null-control rows emitted when `compute_nulls=True`. Each null
  row carries `null_method` and `null_seed` for traceability. Null rows are
  controls for artifact sensitivity; observed metrics must separate from null
  distributions before any structural claim can be made.

Q / Qabs / f_dress reported on those rows are proxy summaries. They are not
validated consciousness observables and require null-control comparison
(`validation/nulls.py`) plus state-labelled experiments before any
structural claim can be made.

The PCIst-style column is now named `pcist_proxy` to make clear it is **not**
the canonical PCIst implementation. The deprecated `pcist_surrogate` function
remains as an alias for backward compatibility.

Future work:
- Montage-aware 2D phase-grid interpolation feeding
  `phase_grid_topology_metrics`.
- Wire deterministic null surrogates into per-window CSV output.
- LOC/ROC and seizure-state validation against `state_label`.
