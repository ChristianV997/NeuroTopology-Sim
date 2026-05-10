# Awareness Studio

Local app: **Book Generator CLI** + **Guidance Chatbot CLI** backed by Notion-exported knowledge.

## Setup

```bash
pip install -e apps/awareness_studio
cp apps/awareness_studio/.env.example apps/awareness_studio/.env
# Edit .env — add your ANTHROPIC_API_KEY (or OPENAI_API_KEY)
```

## Drop in your Notion exports

Place exported `.md` files in `inputs/notion_export/` (or set `NOTION_EXPORT_DIR`):

```bash
# Default path
apps/awareness_studio/inputs/notion_export/

# Or override via env var
export NOTION_EXPORT_DIR=/path/to/your/exports
```

Then rebuild the index:

```bash
python -m awareness_studio.index_build --force
# or via entry point:
awareness-index --force
```

The command prints:
```
INFO  Loaded 7 document(s) from .../inputs/notion_export
INFO  Chunked into 90 chunks (backend=bm25)
INFO  BM25 index saved → .index/chunks.json  (90 chunks)
[OK]  backend=bm25  chunks=90  inputs=...
```

If the folder is empty it prints an actionable warning and exits 1.

Sample exports for all 7 canonical Notion pages are already included.

---

## Chat CLI

```bash
python -m awareness_studio.chat_cli --mode EXPLAIN --question "What is not-self via controllability?"
python -m awareness_studio.chat_cli --mode TEACH   --question "What is consciousness?"
python -m awareness_studio.chat_cli --mode MATRIX  --question "Map tanha as gain and upadana as latch"
python -m awareness_studio.chat_cli --mode ELABORATE --question "What are we — soul, self, or process?"

# Stream tokens to stdout
python -m awareness_studio.chat_cli --mode EXPLAIN --question "Second arrow?" --stream
```

Available modes: `TEACH` `EXPLAIN` `ELABORATE` `MATRIX` `CARD` `CANONICAL`

---

## Book Generator CLI

```bash
python -m awareness_studio.book_generator --quadrant q1 --chapter "Soltar es aflojar" --words 1200
python -m awareness_studio.book_generator --quadrant q2 --chapter "Vedana precision" --words 1400
python -m awareness_studio.book_generator --quadrant q3 --chapter "Samsara as loops" --words 900
python -m awareness_studio.book_generator --quadrant q4 --chapter "Gain control" --words 1400

# Stream long chapters
python -m awareness_studio.book_generator --quadrant q3 --chapter "Samsara as loops" --words 900 --stream
```

Quadrant voices:
| Flag | Voice |
|------|-------|
| `q1` | Warm, story-first, autoayuda práctica |
| `q2` | Pali/EBT dense, Theravāda avanzado |
| `q3` | Skeptical science-pop, info-theory analogies |
| `q4` | PhD rigor, formal claims, falsifiers |

---

## Eval runner (golden test harness)

```bash
# No LLM required — validates retrieval coverage + prompt structure
python -m awareness_studio.eval_runner --no-llm
# or:
awareness-eval --no-llm

# With LLM key — validates full output content
python -m awareness_studio.eval_runner

# Run specific questions only
python -m awareness_studio.eval_runner --no-llm --ids q001 q003 q005
```

Output:
```
Results: 10/10 passed
All checks passed ✓
```

Edit `tests/golden_questions.json` to add your own questions.

---

## LLM providers

Set `LLM_PROVIDER` in `.env`:

```bash
# Anthropic (default)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6

# OpenAI (no SDK needed — pure urllib)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
# OPENAI_BASE_URL=https://api.openai.com/v1   # optional override for proxies
```

---

## Index backends

```bash
# BM25 (default — offline, no extra deps)
INDEX_BACKEND=bm25

# Vector embeddings
INDEX_BACKEND=embedding

# Embedding providers
EMBEDDING_PROVIDER=local_stub    # offline test (deterministic hash vectors)
EMBEDDING_PROVIDER=openai        # text-embedding-3-small via urllib

# Build embedding index
INDEX_BACKEND=embedding EMBEDDING_PROVIDER=openai \
  python -m awareness_studio.index_build --force --backend embedding
```

Embeddings persist to `.data/embeddings.json`. BM25 persists to `.index/chunks.json`.

---

## File naming for source kind inference

| File pattern | `source_kind` |
|---|---|
| `book_system*.md` | `book_system` |
| `*q1*.md`, `*autoayuda*.md` | `book_seed_q1` |
| `*q2*.md`, `*therav*.md` | `book_seed_q2` |
| `*q3*.md`, `*esceptic*.md` | `book_seed_q3` |
| `*q4*.md`, `*liberation*.md` | `book_seed_q4` |
| `*answer_template*.md`, `*monk*.md` | `answer_templates` |
| `*rag_plan*.md`, `*dev*plan*.md` | `rag_plan` |
| anything else | `other` |

---

## Run tests

```bash
cd apps/awareness_studio
pip install -e ".[dev]"
pytest                        # 50 tests, all offline (no LLM key needed)
```

---

## Architecture

```
inputs/notion_export/*.md
        ↓ io_markdown.py      (load + infer source_kind)
        ↓ chunking.py         (heading-aware, stable SHA-256 chunk IDs)
        ↓ index_build.py      (persist JSON + build index)
        ├─ BM25Index           ← INDEX_BACKEND=bm25  (default, offline)
        └─ EmbeddingIndex      ← INDEX_BACKEND=embedding (openai or stub)
        ↓ prompts.py + answer_modes.py  (Monk+Scientist templates)
        ↓ llm_client.py       (BaseLLMClient → AnthropicClient | OpenAIClient)
   chat_cli.py           --mode --stream --tools
   book_generator.py     --quadrant --chapter --words --stream
   eval_runner.py        --no-llm | full LLM
   web/app.py            FastAPI + SSE + Control Panel UI
        ├─ tool_router.py        pubmed_search | biorxiv_search | linear_list_issues
        └─ integrations/
              airtable_client.py  REST v0 client (stdlib urllib)
              airtable_sync.py    Ops Mirror: Runs / Claims / Work Queue
```

---

## Airtable Ops Mirror

Airtable is an **optional, write-gated** ops layer — not canonical knowledge.
Writes are disabled by default and require both the env flag and an explicit CLI/API flag.

```bash
# 1. Set env vars in .env
AIRTABLE_ENABLED=true
AIRTABLE_API_KEY=patXXXXXXXXXXXXXX   # Personal Access Token from airtable.com/account
AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX   # Base ID from Airtable API docs URL

# 2. Create tables in your base (column names must match exactly):
#    Runs:       run_id | mode | timestamp | input_hash | metrics_json | artifacts_json | run_card_path | summary | notes
#    Claims:     claim_id | claim_text | claim_type | status | confounds | discriminator | linked_runs
#    Work Queue: task | priority | repo | status | links

# 3. Check status (no API calls)
awareness-airtable status

# 4. Dry-run sync (safe — shows what would be written)
awareness-airtable sync-runs

# 5. Live write (requires AIRTABLE_ENABLED=true)
awareness-airtable sync-runs --allow-write
```

**Safety gates:**
- `AIRTABLE_ENABLED=false` (default) — all mutations blocked at client level
- `--allow-write` must be passed explicitly; web endpoint requires `?allow_write=true`
- Reads (`/airtable/status`) always safe — no API calls, config check only
- Claims and Work Queue are read-only stubs pending schema finalization

---

## Control Panel (Web UI)

```bash
# Start the server
uvicorn awareness_studio.web.app:app --reload --port 8000

# Open in browser
open http://localhost:8000
```

Features: chat with SSE streaming · mode selector · tools toggle · sources panel · tool_calls panel · sidebar buttons for tools/list, literature search, evidence card drafts, Linear issues, Airtable status/sync.

**Deploy on Replit:**
1. Fork the repo into Replit
2. Replit auto-reads `.replit` and runs `uvicorn` on `$PORT`
3. Set secrets: `ANTHROPIC_API_KEY`, optionally `AIRTABLE_API_KEY`, `LINEAR_API_KEY`
4. Click Run — the Control Panel opens on the Replit URL

**CORS (for Expo / mobile):**
```bash
CORS_ALLOW_ORIGINS=*   # or comma-separated origins
```

**Stable `/chat` schema (Expo-ready):**
```json
{
  "answer": "...",
  "sources_used": ["c1", "c2"],
  "tool_calls": [{"tool_name": "pubmed_search", "success": true, "result_summary": "returned 3 results"}],
  "mode": "EXPLAIN",
  "request_id": "req-abc123",
  "retrieved": 8
}
```
