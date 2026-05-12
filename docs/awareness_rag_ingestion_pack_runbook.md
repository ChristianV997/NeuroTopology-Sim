# Awareness Research RAG Ingestion Pack — Runbook

**Pipeline:** P20.1  
**Module:** `sciencer_d/btc_icft/rag/ingestion_pack.py`  
**CLI:** `tools/build_awareness_rag_ingestion_pack.py`  
**Config:** `configs/btc_icft/awareness_rag_ingestion_pack.yaml`

## Purpose

P20.1 consumes the P20.0 `rag_artifact_manifest.jsonl` and deterministically builds
local, claim-safe chunk/index metadata for future retrieval systems.

This is packaging only.
No embeddings, no vector DB setup, no API calls, and no contract activation.

## CLI

```bash
python tools/build_awareness_rag_ingestion_pack.py \
  --manifest outputs/btc_icft/rag_manifest/rag_artifact_manifest.jsonl \
  --artifact-root outputs/btc_icft \
  --docs docs \
  --out outputs/btc_icft/rag_ingestion_pack
```

### Flags

- `--manifest` (default `outputs/btc_icft/rag_manifest/rag_artifact_manifest.jsonl`)
- `--artifact-root` (default `outputs/btc_icft`)
- `--docs` (default `docs`)
- `--out` (default `outputs/btc_icft/rag_ingestion_pack`)
- `--max-chars-per-chunk` (default `1800`)
- `--overlap-chars` (default `200`)
- `--max-artifacts` (optional)
- `--include-priority-max` (default `3`)
- `--include-quarantined` (default `false`)
- `--mock-fixture` (deterministic local fixture)

If the manifest is missing (and `--mock-fixture` is not used), P20.1 writes empty-valid
outputs with blocker `rag_manifest_missing` and exits `0`.

## Output files

- `rag_ingestion_chunks.jsonl` — all generated chunks with guardrails/context fields
- `rag_ingestion_pack.json` — pack summary, counts, params, blockers
- `rag_ingestion_index.csv` — index metadata rows per chunk
- `withheld_or_quarantined_chunks.json` — withheld reasons + quarantined chunks
- `omega_event.json` — deterministic event record
- `report.md` — human-readable summary

## Required chunk model fields

Each chunk includes:

- `chunk_id`
- `artifact_id`
- `source_path`
- `relative_path`
- `file_type`
- `stage`
- `dataset_id`
- `evidence_state`
- `claim_safety_status`
- `index_priority`
- `recommended_rag_mode`
- `chunk_role`
- `chunk_text`
- `source_summary`
- `safe_claim`
- `required_context`
- `forbidden_claims_found`
- `retrieval_tags`
- `guardrails`
- `next_action`

## Claim safety constraints

P20.1 keeps claim-safe framing and must not assert that EEG/topology/Q/Q_abs/f_dress,
datasets, interventions, meditation, or BTC/ICFT prove consciousness/self/soul/liberation.

Quarantined artifacts are withheld unless `--include-quarantined true` is explicitly set.
Human review is required before any promotion.
