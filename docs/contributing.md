# Contributing Setup Guide

This project has multiple contributor surfaces with different dependency footprints. To keep environments reproducible and avoid dependency collisions, use isolated virtual environments per surface.

## Recommended environment isolation

### 1) Core pipelines environment
Use this environment when working on simulation, validation, ingestion, and tests under `tests/`.

```bash
python -m venv .venv-core
source .venv-core/bin/activate
pip install -r requirements.txt
pytest -q tests
```

### 2) Awareness Studio environment
Use this environment when working on the application under `apps/awareness_studio`.

```bash
python -m venv .venv-awareness
source .venv-awareness/bin/activate
pip install -e apps/awareness_studio
pip install -e "apps/awareness_studio[dev]"
pytest -q apps/awareness_studio/tests
```

### 3) Full-stack environment (optional)
If you need to touch both surfaces in one session, create a dedicated environment for all dependencies.

```bash
python -m venv .venv-fullstack
source .venv-fullstack/bin/activate
pip install -r requirements.txt
pip install -e apps/awareness_studio
pip install -e "apps/awareness_studio[dev]"
pytest -q tests && pytest -q apps/awareness_studio/tests
```

## Why separate environments?
- Keeps dependency resolution predictable across surfaces.
- Reduces cross-project package conflicts.
- Speeds up troubleshooting by limiting moving parts.

## Related documentation
- Root project overview and setup matrix: [../README.md](../README.md)
- Awareness Studio details: [../apps/awareness_studio/README.md](../apps/awareness_studio/README.md)
