# Phase 1 — Empirical Falsification Subsystem

Implemented components:

- `sim/pitnn/empirical_pipeline.py`: deterministic Butterworth filtering,
  channel normalization, Hilbert phase, coherence matrices, topology proxies,
  and labelled offline fixtures.
- `sim/pitnn/ingest_empirical.py`: local two-condition ingestion from NPZ or
  time-split CSV/NPY recordings.
- `scripts/run_empirical_falsification.py`: offline CLI that writes
  `empirical_falsification_report.json` with RSS, AICc, Bayes factor, verdict,
  and condition-level topology summaries.
- `tests/test_empirical_falsification.py`: preprocessing, fixture, report, and
  local-ingestion coverage.

Run the demonstration without network access:

```powershell
.venv\Scripts\python.exe scripts\run_empirical_falsification.py --fast-tda
```

The generated fixture is labelled `synthetic_demo`; it cannot be treated as
empirical evidence and must remain `NOT_SUPPORTED`. For local NPZ input, store
two arrays named `state_a` and `state_b`, each with shape `(samples, channels)`:

```powershell
.venv\Scripts\python.exe scripts\run_empirical_falsification.py `
  --input-file data\conditions.npz `
  --condition-a-label awake `
  --condition-b-label sedated `
  --sample-rate-hz 250 `
  --output-dir artifacts\pitnn\empirical
```

`PASS` is emitted only when the ordinary Bayesian comparison computes
`K > 100` from the supplied local recording. No parameter forcing or synthetic
scaling is performed.
