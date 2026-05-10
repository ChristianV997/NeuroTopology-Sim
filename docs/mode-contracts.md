# Mode Contracts

| Mode | Command | Required inputs | Output artifacts | Failure behavior | Scientific status |
|---|---|---|---|---|---|
| synthetic | `python main.py --mode synthetic` | none | `results/synthetic/synthetic_summary.csv` | exits non-zero on runtime error | baseline synthetic validation |
| qzt | `python main.py --mode qzt --input data/checkpoints` | checkpoint directory | QZT/events outputs under `results/` | exits non-zero when checkpoints invalid/missing | pipeline utility |
| eeg | `python main.py --mode eeg --input <dir> --dataset <id>` | EEG input root, dataset id | EEG metrics CSV under `results/<dataset>/` | exits non-zero on read/compute failures | exploratory metrics |
| physionet | `python main.py --mode physionet --input <dir>` | PhysioNet-compatible input root | `results/physionet_gaba/metrics_physionet_gaba.csv` | exits non-zero on input/compute failures | exploratory metrics |
| physics | `python main.py --mode physics --input <file.npy>` | existing `.npy` file | output CSV (default `results/out.csv`) | argument error for missing/non-`.npy` input, non-zero on runtime error | utility validation |
| cross-domain | `python main.py --mode cross-domain --results-root results` | results root directory | consolidated cross-domain CSV | exits non-zero on aggregation errors | reporting utility |
| external | `python main.py --mode external --config config/defaults.yaml` | config file; optional db path and max-records | external metrics CSV + optional db updates | exits non-zero on config/source failures | integration utility |
| db | `python main.py --mode db --db data/runs.sqlite` | writable sqlite path | DB run row + metric + artifact records | exits non-zero on DB errors | ops/traceability utility |
