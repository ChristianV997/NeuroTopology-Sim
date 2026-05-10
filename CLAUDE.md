# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Repository Overview

**ScienceR-Dsim** is a dual-system repository:

1. **Core sim engine** (repo root) — 3D topological field simulation, EEG/PCI validation, and multi-mode pipelines using numpy/scipy/sklearn.
2. **Awareness Studio** (`apps/awareness_studio/`) — an independently installable FastAPI + RAG chatbot app that consumes sim artifacts as knowledge-base inputs.

These two systems share a single artifact contract (`runs/run_record.py`) but have separate Python environments, test suites, and entry points.

---

## Commands

### Core sim engine (run from repo root)

```bash
pip install -r requirements.txt

# Run a mode
python main.py --mode synthetic
python main.py --mode qzt --input data/checkpoints
python main.py --mode eeg --dataset ds002094 --input data/raw/ds002094 --output results/ds002094.csv --compute-pci
python main.py --mode physics --input /path/to/sample.npy --output results/the_well.csv
python main.py --mode cross-domain --results-root results --output results/cross_domain.csv
python main.py --mode external --config config/defaults.yaml --output results/live_sensors.csv --db data/runs.sqlite

# Run a hypothesis spec (writes summary.json + RunRecord.json to artifacts/)
python -m pipelines.hypothesis --spec governance/specs/HYP-20260506-002.yaml --output artifacts/run1

# Export sim artifacts to Awareness Studio RAG inputs
python -m apps.awareness_studio.tools.export_sim_artifacts \
    --artifacts-root artifacts \
    --out-dir apps/awareness_studio/inputs/sim_artifacts

# Root-level tests (skip scipy-dependent tests if scipy not installed)
pytest tests/ --ignore=tests/test_pci.py --ignore=tests/test_stats.py --ignore=tests/test_worldlines.py -q

# Run a single root test file
pytest tests/test_run_record.py -q
pytest tests/test_run_records.py -q
```

### Awareness Studio (run from `apps/awareness_studio/`)

```bash
cd apps/awareness_studio

# First-time setup
bash scripts/bootstrap.sh        # macOS/Linux: creates .venv, installs deps, runs smoke gates
# OR
make setup                       # equivalent, manual

# All offline smoke gates
make smoke                       # test + eval + index

# Individual targets
make test                        # pytest -q  (offline, no LLM)
make eval                        # golden retrieval eval (no LLM)
make index                       # (re)build BM25 index
make web                         # start FastAPI on :8000

# Run a single test file
.venv/bin/pytest tests/test_orchestrator_dry_run.py -q
.venv/bin/pytest tests/test_cmd_orchestrate.py -q

# CLI entry points (after activating .venv)
awareness-chat                   # RAG chatbot REPL
awareness-book                   # book generator
awareness-index --force          # rebuild retrieval index
awareness-eval --no-llm          # offline golden eval
awareness-airtable               # Airtable sync CLI
```

---

## Architecture

### Two Python Environments

| Scope | Root | `apps/awareness_studio/` |
|---|---|---|
| Install | `pip install -r requirements.txt` | `pip install -e ".[dev,web]"` |
| Tests | `pytest tests/` | `pytest` (reads `pyproject.toml`) |
| Entry point | `main.py` | `uvicorn awareness_studio.web.app:app` |
| Core deps | numpy, scipy, sklearn, mne | anthropic, fastapi, uvicorn |

`sys.path` at the repo root is extended by `conftest.py` so all `from core.X`, `from runs.X`, `from sim.X` imports resolve without installation.

### Shared Artifact Contract: `runs/run_record.py`

`RunRecordV1` is the **single canonical run artifact schema** used by both systems. Every pipeline writes a `RunRecord.json`; Awareness Studio reads them via `export_sim_artifacts.py` to produce RAG-ingestible Markdown.

Key facts:
- `run_kind` (general) maps to `mode` (sim legacy) — both fields exist; `run_kind` is canonical.
- `run_id = sha256[:16]` of `{spec_id, sim_params}` — deterministic across reruns with same inputs.
- `to_dict()` → general format (`schema_version: "0.1"`); `to_sim_dict()` → legacy format (`schema_version: "1"`) used by Airtable sync validation.
- `sim/run_record_schema.py` is a **compat shim** that re-exports from `runs.run_record`. Do not add logic there.

### Core Sim Engine (repo root)

```
core/topology.py       — compute_Qz, compute_Qabs_slice, compute_f_dress, plaquette_charge
core/defects.py        — vortex defect extraction
tracking/worldlines.py — worldline tracking (requires scipy)
analysis/             — qzt.py, events.py, stats.py
validation/           — synthetic.py, pci_validation.py, benchmarks.py
pipelines/            — one module per mode (qzt, eeg, physics, hypothesis, external, …)
sim/                  — run_psi_os(), run_meditation_sim(), build_run_record()
runs/run_record.py    — canonical artifact contract (see above)
governance/specs/     — YAML hypothesis specs consumed by pipelines/hypothesis.py
```

`core/topology.py` is the innermost dependency — everything else builds on `compute_Qz` / `plaquette_charge`. The topology charge `Qz` (signed), `Qabs` (unsigned), and `f_dress` (excess winding) are the primary scientific metrics throughout.

### Awareness Studio Internal Architecture

```
src/awareness_studio/
  config.py            — all env-var config (single source of truth)
  io_markdown.py       — recursive Markdown loader from inputs/
  chunking.py          — text chunker for RAG
  index_build.py       — BM25 index builder; get_or_build_index()
  retrieval.py         — BM25 retriever
  embeddings.py        — optional embedding backend (stub or OpenAI)
  llm_client.py        — LLM wrapper (Anthropic / OpenAI)
  answer_modes.py      — TEACH / EXPLAIN / MATRIX / CARD / CANONICAL prompt modes
  prompts.py           — system/user prompt templates
  orchestrator/        — 8-stage deterministic pipeline (dry_run=True by default)
    event_model.py     — EventEnvelope (stable event_id = sha256[:16] of stage+run_id+payload)
    event_log.py       — append-only JSONL event log
    orchestrator.py    — Orchestrator.run() → 8 stages, outputs in outputs/orchestrator/<run_id>/
  integrations/
    airtable_client.py — low-level Airtable HTTP client
    airtable_sync.py   — RunCard sync engine (3-layer write gate)
  web/app.py           — FastAPI app with all routes
  tools/
    export_sim_artifacts.py — converts RunRecord.json → RAG Markdown
```

**RAG pipeline flow:** `inputs/` Markdown files → `io_markdown.py` loader → `chunking.py` → BM25/embedding index → `retrieval.py` → `llm_client.py` → response.

**Inputs directory structure:**
```
inputs/
  notion_export/      — Notion page exports (default knowledge base)
  sim_artifacts/      — RunRecord.json → Markdown (generated by export_sim_artifacts.py)
  lit_review/         — PubMed / ClinicalTrials literature (manually added or pipeline-generated)
```

### Orchestrator Pipeline (8 stages)

`PIPELINE_STAGES` in `event_model.py`:
`ingest_inputs → propose_hypotheses → plan_experiments → execute → validate → digest → draft_report → ops_update`

Each stage emits `EventEnvelope` records to an append-only JSONL log at `outputs/orchestrator/<run_id>/events.jsonl`. Stage outputs: `EvidenceLogDraft.md`, `Report.md`, `GraphUpdate.json`, `OpsQueueItem.json`.

In `dry_run=True` mode (default) no network or LLM calls are made — all outputs are deterministic stubs seeded from `OrchestratorConfig.seed`.

### Airtable Sync Write Gate

Three conditions must all be true for a live write:
1. `AIRTABLE_ENABLED=true` in environment
2. `allow_write=True` passed to `sync_runs()`
3. Airtable client initialized with a valid API key

Any other combination → dry-run (returns planned payloads, no HTTP calls).

### Authentication Gate

`AUTH_ENABLED=true` + `AUTH_API_KEY=<secret>` enables `X-Awareness-Key: <secret>` header requirement on write endpoints (`POST /airtable/sync/runs`). All read/chat endpoints are always public.

---

## Hypothesis Spec Format

Specs live in `governance/specs/HYP-<date>-<seq>.yaml`. Required fields:

```yaml
spec_id: HYP-YYYYMMDD-NNN
claim_type: topology_gain_control   # or other claim types
layer: biophysical
data_mode: synthetic
hypothesis: >
  Free-text description.
threshold:
  I_mean_min: 0.1
  Qabs_max: 10.0
sim_params:
  N: 32          # grid size
  n_steps: 20    # diffusion steps
  seed: 42
```

Run via: `python -m pipelines.hypothesis --spec governance/specs/HYP-YYYYMMDD-NNN.yaml --output artifacts/runN`

Verdict is `PASS` if `I_mean >= I_mean_min AND Qabs <= Qabs_max`.

---

## Key Environment Variables

Set in `apps/awareness_studio/.env` (copy from `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | — | Required for live LLM calls |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Model for chat/book generation |
| `INDEX_BACKEND` | `bm25` | `bm25` (offline) or `embedding` |
| `TOOLS_ENABLED` | `false` | Enable PubMed/Linear tool routing |
| `AUTH_ENABLED` | `false` | Require `X-Awareness-Key` on write endpoints |
| `AIRTABLE_ENABLED` | `false` | Enable Airtable sync |

All variables are documented in `apps/awareness_studio/docs/CONFIG.md`.

---

## Test Layout

| Location | What it covers | Notes |
|---|---|---|
| `tests/test_run_record.py` | `RunRecordV1` general schema (19 tests) | Always passes |
| `tests/test_run_records.py` | Sim-specific schema + writers + runners (44 tests) | Requires numpy |
| `tests/test_pipelines.py` | Hypothesis pipeline + legacy pipelines | 6 tests require scipy/sklearn |
| `tests/test_topology.py` | `core/topology.py` | Requires numpy |
| `apps/awareness_studio/tests/` | All Awareness Studio tests (~200) | Run from `apps/awareness_studio/` |
| `apps/awareness_studio/tests/test_orchestrator_dry_run.py` | 36 tests, no network | Fully offline |
| `apps/awareness_studio/tests/test_export_sim_artifacts.py` | 15 tests, export pipeline | Fully offline |

Pre-existing failures in `tests/test_pci.py`, `test_stats.py`, `test_worldlines.py` require `scipy`/`sklearn` not in the default environment — skip them unless those packages are installed.
