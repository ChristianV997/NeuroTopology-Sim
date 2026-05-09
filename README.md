# ScienceR-Dsim

Integrated topological field simulation + EEG validation system.

## Included
- 3D topology core: Q, Qabs, Q(z,t)
- Defect extraction and worldline tracking
- Reconnection/event detection
- Synthetic validation
- EEG / PCI validation hooks
- Physics hooks (The Well)
- External ecosystem connectors (file/REST/MQTT/WebSocket)
- SQLite registry
- Paper figure generation

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
