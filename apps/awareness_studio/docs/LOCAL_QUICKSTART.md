# Local Quick Start — Awareness Studio

Get from clone to a running Control Panel in < 10 minutes. No keys required for smoke testing.

---

## Prerequisites

| Tool | Min version | Install |
|------|-------------|---------|
| Python | 3.11+ | python.org or `brew install python@3.11` |
| git | any | system or brew |

No Docker, no Node, no database required.

---

## macOS / Linux

```bash
# 1. Clone (skip if already done)
git clone https://github.com/ChristianV997/ScienceR-Dsim.git
cd ScienceR-Dsim/apps/awareness_studio

# 2. Bootstrap (creates .venv, installs deps, runs smoke gates)
bash scripts/bootstrap.sh

# 3. Activate the venv
source .venv/bin/activate

# 4. Start the Control Panel
make web
# → open http://localhost:8000
```

The bootstrap step runs all offline gates automatically:
- `pytest -q` — 200+ unit tests
- `awareness-eval --no-llm` — golden retrieval eval (no key needed)
- `awareness-index --force` — builds the BM25 index from sample exports

---

## Windows (PowerShell)

```powershell
# 1. Clone
git clone https://github.com/ChristianV997/ScienceR-Dsim.git
cd ScienceR-Dsim\apps\awareness_studio

# 2. Bootstrap
.\scripts\bootstrap.ps1

# 3. Activate
.venv\Scripts\Activate.ps1

# 4. Start Control Panel
uvicorn awareness_studio.web.app:app --port 8000
# → open http://localhost:8000
```

---

## Makefile targets

Run these from `apps/awareness_studio/`:

```bash
make setup    # create .venv + install deps
make test     # pytest -q
make eval     # golden eval --no-llm
make index    # rebuild BM25 index
make web      # start FastAPI on port 8000 (PORT=N to override)
make smoke    # test + eval + index (full offline gate)
```

---

## Enable LLM features

Edit `apps/awareness_studio/.env`:

```bash
# Anthropic (default)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (no SDK required)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Then restart the server (`make web`).

---

## Drop in your own Notion exports

```bash
# Default location (already has sample exports)
apps/awareness_studio/inputs/notion_export/

# Or set env var
export NOTION_EXPORT_DIR=/path/to/your/exports

# Rebuild index
make index
```

---

## Run an orchestrator dry run

Once the server is running:

```bash
# via curl
curl -s -X POST http://localhost:8000/cmd/orchestrate?dry_run=true | python3 -m json.tool

# or via the Control Panel UI
# → click "Orchestrate Dry Run" button in the sidebar
```

Outputs land in `outputs/orchestrator/<run_id>/`.

---

## VS Code tasks

Open the repo in VS Code — tasks appear in **Terminal → Run Task**:

| Task | Action |
|------|--------|
| Awareness: Setup | Run bootstrap |
| Awareness: Smoke | Offline gates |
| Awareness: Start Web UI | Start server |
| Awareness: Test | pytest |
| Awareness: Orchestrate Dry Run | POST /cmd/orchestrate |

---

## Troubleshooting

**`No module named 'awareness_studio'`**
```bash
pip install -e ".[dev,web]"
# or: PYTHONPATH=src pytest
```

**`Index is empty`**
```bash
make index
```

**`PORT already in use`**
```bash
PORT=8001 make web
```

**`AUTH_API_KEY not set` (401 on sync endpoints)**  
Set `AUTH_ENABLED=false` in `.env`, or add `AUTH_API_KEY=your-key` and pass `X-Awareness-Key: your-key` header.
