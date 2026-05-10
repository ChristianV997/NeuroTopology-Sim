# Mode contracts (`main.py`)

This document defines runtime contracts for each `--mode` in `main.py` so callers and integrators know required inputs, produced artifacts, runtime dependencies, and the exact entrypoints used.

## Shared CLI defaults and behavior

- `--mode` is required and selects one dispatch branch.
- `--input` defaults to `data/checkpoints`, but several modes reinterpret it differently (directory vs file).
- `--output` defaults to `results/out.csv`; multiple modes treat this sentinel default as “auto-derive mode-specific path”.
- `--dataset` defaults to `ds002094` and only impacts `eeg` mode.
- `--results-root` defaults to `results` and only impacts `cross-domain` mode.
- `--compute-pci` is only consumed by `eeg` mode.
- `--db` defaults to `data/runs.sqlite`; used by `external` and `db`.
- `--config` defaults to `config/defaults.yaml`; used by `external`.
- `--max-records` is optional and only used by `external`.

---

## `synthetic`
- **Required inputs**: none beyond `--mode synthetic`.
- **Output artifact paths/formats**: `results/synthetic/synthetic_summary.csv` (CSV) and stdout dataframe.
- **External dependencies/datasets**: generated synthetic fields from `validation.synthetic`.
- **Offline-safe**: yes.
- **Primary entrypoints**: `main.main()` -> `main.run_synthetic()` -> `core.topology.compute_Qz()`.

## `qzt`
- **Required inputs**: `--input` checkpoint directory expected by `pipelines.run_qzt.run`.
- **Output artifact paths/formats**: writes outputs under `results/` (pipeline-managed); prints counts.
- **External dependencies/datasets**: local checkpoint artifacts.
- **Offline-safe**: generally yes if checkpoints are local.
- **Primary entrypoints**: `main.main()` -> `main.run_qzt()` -> `pipelines.run_qzt.run()`.

## `eeg`
- **Required inputs**: `--input` source path; optional `--dataset`, `--compute-pci`.
- **Output artifact paths/formats**: CSV metrics. If `--output` stays at default sentinel `results/out.csv`, output auto-resolves to `results/<dataset>/metrics_<dataset>.csv`.
- **External dependencies/datasets**: dataset layout expected by `pipelines.run_eeg.run`.
- **Offline-safe**: depends on whether data is already local.
- **Primary entrypoints**: `main.main()` -> `pipelines.run_eeg.run()`.

## `physionet`
- **Required inputs**: `--input` source path expected by PhysioNet pipeline.
- **Output artifact paths/formats**: CSV metrics. If `--output` remains sentinel default, output auto-resolves to `results/physionet_gaba/metrics_physionet_gaba.csv`.
- **External dependencies/datasets**: PhysioNet GABA-related input expected by `pipelines.run_physionet.run`.
- **Offline-safe**: depends on local availability of dataset.
- **Primary entrypoints**: `main.main()` -> `pipelines.run_physionet.run()`.

## `physics`
- **Required inputs**: `--input` must be an existing `.npy` file; `--output` destination path.
- **Output artifact paths/formats**: pipeline-defined tabular output written to caller-supplied output path.
- **External dependencies/datasets**: local `.npy` physics data file.
- **Offline-safe**: yes.
- **Primary entrypoints**: `main.main()` -> `pipelines.run_physics.run_from_npy()`.

## `cross-domain`
- **Required inputs**: `--results-root` directory of prior outputs; `--output` destination.
- **Output artifact paths/formats**: pipeline-defined output at `--output`.
- **External dependencies/datasets**: prior result artifacts under `--results-root`.
- **Offline-safe**: yes, if artifacts are local.
- **Primary entrypoints**: `main.main()` -> `pipelines.run_cross_domain.run()`.

## `external`
- **Required inputs**: `--config`, `--db`, `--output`; optional `--max-records`.
- **Output artifact paths/formats**: pipeline-defined output at `--output`.
- **External dependencies/datasets**: config-defined sources and sqlite DB target.
- **Offline-safe**: not guaranteed (depends on configured sources).
- **Primary entrypoints**: `main.main()` -> `pipelines.run_external.run()`.

## `db`
- **Required inputs**: `--db` sqlite path, `--output` artifact path to record in metadata.
- **Output artifact paths/formats**: DB rows are written; no direct file write in this branch.
- **External dependencies/datasets**: local sqlite DB via `database.database`.
- **Offline-safe**: yes.
- **Primary entrypoints**: `main.main()` -> DB helper functions in `database.database`.
