# Validation Entrypoints

Primary CLI entrypoint: `main.py`.

## Modes

- `synthetic`: Runs synthetic vortex validations and writes `results/synthetic/synthetic_summary.csv`.
- `qzt`: Runs checkpoint-based QZT processing through `pipelines/run_qzt.py`.
- `eeg`: Runs dataset EEG metrics through `pipelines/run_eeg.py`.
- `physionet`: Runs PhysioNet-specific EEG processing through `pipelines/run_physionet.py`.
- `physics`: Runs `.npy` input physics validation through `pipelines/run_physics.py`.
- `cross-domain`: Aggregates results with `pipelines/run_cross_domain.py`.
- `external`: Runs configured external ingestion pipeline via `pipelines/run_external.py`.
- `db`: Exercises run logging in `database/database.py`.
