# First Day Checklist — Awareness Studio

Complete these steps in order. Checkboxes are yours to tick.

---

## Step 1 — Setup (5 min)

```bash
cd apps/awareness_studio
bash scripts/bootstrap.sh
```

This creates `.venv`, installs deps, builds the BM25 index, and runs all offline gates.

Expected output:
```
✓ Bootstrap complete!
```

- [ ] Bootstrap completed without errors

---

## Step 2 — Run smoke gates

```bash
source .venv/bin/activate
make smoke
```

Expected:
```
[smoke] all gates passed
```

- [ ] `pytest -q` passes (200+ tests)
- [ ] `awareness-eval --no-llm` passes (10/10 or 30/30 questions)
- [ ] `awareness-index --force` builds index

---

## Step 3 — Start the Control Panel

```bash
make web
# → open http://localhost:8000
```

- [ ] Server starts on port 8000 (or `PORT=N make web`)
- [ ] Browser shows "Awareness Studio — Control Panel"
- [ ] Health check button shows green dot

---

## Step 4 — Run the orchestrator dry run

**In the UI:**
Click "Orchestrate Dry Run" in the sidebar.

**Or via curl:**
```bash
curl -s -X POST http://localhost:8000/cmd/orchestrate?dry_run=true | python3 -m json.tool
```

Expected: JSON with `run_id`, `stages_completed` (8 stages), `dry_run: true`.

Artifacts appear in: `outputs/orchestrator/<run_id>/`

- [ ] Orchestrator ran all 8 stages
- [ ] `Report.md` exists in the output dir
- [ ] Orchestrator panel in UI shows stage results

---

## Step 5 — Enable LLM features (optional)

Add your key to `.env`:

```bash
# For Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# For OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Restart the server: `make web`

Test with:
```bash
python -m awareness_studio.chat_cli --mode EXPLAIN --question "What is vedanā?"
```

- [ ] LLM responds coherently
- [ ] Chat UI returns answer with sources

---

## Step 6 — Enable Airtable ops sync (optional)

1. Get a Personal Access Token from airtable.com/account
2. Create a base with tables: `Runs`, `Claims`, `Work Queue` (see `CONFIG.md` for columns)
3. Set in `.env`:
   ```bash
   AIRTABLE_ENABLED=true
   AIRTABLE_API_KEY=patXXXX
   AIRTABLE_BASE_ID=appXXXX
   ```
4. Dry-run first:
   ```bash
   awareness-airtable sync-runs
   ```
5. Live write:
   ```bash
   awareness-airtable sync-runs --allow-write
   ```

- [ ] `awareness-airtable status` shows `enabled: true`
- [ ] Dry-run shows planned upserts
- [ ] (Optional) live sync confirmed in Airtable

---

## Done! Quick reference

| Action | Command |
|--------|---------|
| Run tests | `make test` |
| Run eval | `make eval` |
| Rebuild index | `make index` |
| Start server | `make web` |
| Full smoke | `make smoke` |
| Orchestrate (curl) | `curl -X POST http://localhost:8000/cmd/orchestrate?dry_run=true` |
| Airtable status | `awareness-airtable status` |

See also:
- `docs/LOCAL_QUICKSTART.md` — setup details
- `docs/CONFIG.md` — all environment variables
- `README.md` — full feature reference
