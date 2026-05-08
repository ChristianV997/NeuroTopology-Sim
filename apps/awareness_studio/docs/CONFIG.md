# Configuration Reference — Awareness Studio

All configuration is via environment variables, loaded from `.env` at startup.
Every variable has a safe default so the system runs offline with zero keys.

Copy the template: `cp .env.example .env`

---

## LLM Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | _(empty)_ | Required for Anthropic. `sk-ant-...` |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Anthropic model ID |
| `OPENAI_API_KEY` | _(empty)_ | Required for OpenAI. `sk-...` |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model ID |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Override for proxies |
| `LLM_MAX_TOKENS` | `4096` | Max tokens per completion |
| `LLM_TEMPERATURE` | `0.7` | Sampling temperature |

**Offline behavior:** If no key is set, LLM calls will fail gracefully. All tests and the eval harness run without any key.

---

## Index Backend

| Variable | Default | Description |
|----------|---------|-------------|
| `INDEX_BACKEND` | `bm25` | `bm25` (offline) or `embedding` |
| `EMBEDDING_PROVIDER` | `local_stub` | `local_stub` (offline) or `openai` |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `EMBEDDING_DIM` | `64` | Stub dim; 1536 for OpenAI ada |
| `NOTION_EXPORT_DIR` | `inputs/notion_export` | Path to Notion `.md` exports |

Rebuild the index after changing inputs or backend:
```bash
make index
# or: awareness-index --force
```

---

## Tools (External Search)

| Variable | Default | Description |
|----------|---------|-------------|
| `TOOLS_ENABLED` | `false` | Enable PubMed / bioRxiv / Linear tool routing |
| `TOOLS_ALLOWLIST` | _(empty = all)_ | Comma-separated tool names to allow |
| `TOOLS_MAX_CALLS_PER_REQUEST` | `1` | Max tool calls per chat request |
| `LINEAR_API_KEY` | _(empty)_ | Linear GraphQL API key |
| `PUBMED_API_KEY` | _(empty)_ | PubMed API key (optional, improves rate limits) |

---

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_ENABLED` | `false` | Enable `X-Awareness-Key` auth on write endpoints |
| `AUTH_API_KEY` | _(empty)_ | The secret key clients must send |

Protected endpoints (when `AUTH_ENABLED=true`):
- `POST /airtable/sync/runs`
- `POST /cmd/orchestrate`

Pass the key via HTTP header: `X-Awareness-Key: <your-key>`

---

## Airtable Ops Mirror

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRTABLE_ENABLED` | `false` | Enable Airtable writes |
| `AIRTABLE_API_KEY` | _(empty)_ | Personal Access Token from airtable.com/account |
| `AIRTABLE_BASE_ID` | _(empty)_ | Base ID from Airtable URL |

Airtable is write-gated at three levels:
1. `AIRTABLE_ENABLED=true` (env)
2. `--allow-write` CLI flag or `?allow_write=true` query param
3. `enabled=True` on `AirtableClient`

Any missing gate → dry-run only. Reads (`/airtable/status`) always safe.

---

## Orchestrator

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCHESTRATION_ENABLED` | _(not yet gated)_ | Future: gate subprocess sim runner |

Orchestrator outputs: `outputs/orchestrator/<run_id>/`
- `events.jsonl` — append-only event log
- `EvidenceLogDraft.md` — draft evidence entries
- `Report.md` — summary report
- `GraphUpdate.json` — knowledge graph delta
- `OpsQueueItem.json` — Airtable ops sync payload

Run card ingestion from ScienceR-Dsim:
```bash
RUN_CARDS_DIR=/path/to/ScienceR-Dsim/outputs/run_cards
# Pass via: POST /cmd/orchestrate (config.run_cards_dir)
# or: awareness-airtable sync-runs (looks in .data/run_cards/)
```

---

## Web Server

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server port (used by Replit / main()) |
| `CORS_ALLOW_ORIGINS` | _(empty)_ | `*` or comma-separated origins for CORS |
| `PROMPT_OPTIMIZER` | `none` | `none` or `dspy_stub` |

---

## File Paths (advanced)

| Variable | Default |
|----------|---------|
| `NOTION_EXPORT_DIR` | `apps/awareness_studio/inputs/notion_export` |
| Index files | `apps/awareness_studio/.index/chunks.json` |
| Embedding cache | `apps/awareness_studio/.data/embeddings.json` |
| Orchestrator output | `apps/awareness_studio/outputs/orchestrator/` |
| Run cards (for Airtable) | `apps/awareness_studio/.data/run_cards/` |

---

## Precedence

Environment variables set directly in the shell override `.env` values.
`.replit` `[env]` section overrides both for Replit deployments.
