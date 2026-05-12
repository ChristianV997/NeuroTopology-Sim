# Awareness Research RAG Artifact Manifest — Runbook

**Pipeline:** P20.0  
**Module:** `sciencer_d/btc_icft/rag/artifact_manifest.py`  
**CLI:** `tools/build_awareness_rag_manifest.py`  
**Config:** `configs/btc_icft/awareness_rag_manifest.yaml`

---

## Purpose

P20.0 scans BTC/ICFT local output artifacts and documentation, then produces a
**claim-safe RAG ingestion manifest** for use with Notion exports, RAG chatbot
indexing pipelines, and paper-preparation workflows.

The outputs are structured for human review before any live chatbot ingestion.
No external APIs are called. No embeddings are created. No labels are inferred.
No contracts are activated.

**Safe claim:**

> BTC/ICFT artifacts were converted into a claim-safe RAG ingestion manifest
> for retrieval, review, and paper-preparation workflows.

---

## What P20.0 Does

- Recursively scans a local artifact root (default: `outputs/btc_icft`) and
  optional docs directory.
- Infers pipeline stage, dataset ID, evidence state, index priority, and
  recommended RAG mode from file paths and content.
- Runs a claim-safety scan on all text/JSON/YAML content and quarantines any
  file containing a banned phrase.
- Writes 7 structured output files (see below).
- Supports a `--mock-fixture` mode that creates deterministic test fixtures
  without touching any real data.

---

## What P20.0 Does NOT Do

- Does **not** call OpenAI, Anthropic, Notion, Airtable, or any external API.
- Does **not** create vector embeddings.
- Does **not** infer or assign dataset labels.
- Does **not** fabricate intervention targets.
- Does **not** activate any contract or gate (P11/P12/P13 are not touched).
- Does **not** modify any P16, P19.0, P11, P12, P13, or legacy `mt_real` files.
- Does **not** claim that EEG signals, topology metrics, Q, Q_abs, f_dress,
  or any other measurement proves consciousness, soul, liberation, afterlife,
  enlightenment, or any ontological conclusion.
- Does **not** promote any metric to empirical status.

---

## Running — Mock Fixture (Recommended First Step)

Use this to validate the output shape without touching any real artifact data:

```bash
python tools/build_awareness_rag_manifest.py \
  --mock-fixture \
  --out outputs/btc_icft/rag_manifest
```

Expected output:

```
[P20.0] mock-fixture manifest written to outputs/btc_icft/rag_manifest (N artifacts)
```

---

## Running — Real / Local Artifacts

After validating mock output shape, run against real local artifacts:

```bash
python tools/build_awareness_rag_manifest.py \
  --root outputs/btc_icft \
  --docs docs \
  --out outputs/btc_icft/rag_manifest
```

If `--root` does not exist, the tool writes empty-but-valid outputs with a
`artifact_root_missing` blocker and exits 0.

### Optional flags

| Flag | Default | Description |
|---|---|---|
| `--root` | `outputs/btc_icft` | Artifact root directory |
| `--docs` | `docs` | Docs directory (set `--include-docs false` to skip) |
| `--out` | `outputs/btc_icft/rag_manifest` | Output directory |
| `--dataset-id` | _(auto-inferred)_ | Override dataset ID for all records |
| `--include-docs` | `true` | Include docs directory |
| `--mock-fixture` | _(flag)_ | Use deterministic mock fixtures |
| `--max-artifacts` | _(unlimited)_ | Cap the number of artifacts scanned |

---

## Output Artifacts

All 7 files are written to `--out`:

| File | Format | Purpose |
|---|---|---|
| `rag_artifact_manifest.jsonl` | JSONL | One record per artifact; suitable for bulk RAG ingestion |
| `rag_artifact_manifest.json` | JSON | Full manifest with counts, priorities, stages, datasets |
| `rag_index_priority.csv` | CSV | Priority-sorted index for first-batch selection |
| `rag_ingestion_plan.md` | Markdown | Human-readable ingestion plan with first-batch list |
| `quarantined_artifacts.json` | JSON | Artifacts with banned phrases; must not be indexed |
| `omega_event.json` | JSON | Pipeline event record (no_external_api, no_embeddings, etc.) |
| `report.md` | Markdown | Summary report with counts, safe claim, guardrails |

### ArtifactRecord fields

Each JSONL row / JSON artifact entry contains:

```
artifact_id          — stable sha256[:16] ID based on relative path
path                 — absolute path
relative_path        — path relative to scan root
file_type            — extension without dot
size_bytes           — file size
stage                — inferred pipeline stage
dataset_id           — inferred or overridden dataset ID
evidence_state       — mock_fixture | synthetic | operational_artifact | empirical_pending | ...
claim_safety_status  — safe | quarantined_banned_phrase
index_priority       — 1 (highest) … 5 (lowest/quarantined)
title                — extracted from first line / filename
summary              — extracted snippet (≤500 chars)
safe_claim           — always the canonical SAFE_CLAIM string
forbidden_claims_found — list of banned phrases found (empty if safe)
recommended_rag_mode — artifact_explainer | claim_card_generator | topology_metric_explainer | ...
required_context     — context note for indexing pipeline
next_action          — recommended next action
```

---

## Index Priority Reference

| Priority | Stages / Conditions |
|---|---|
| 1 | `target_aware_activation`, `ds005620_contract_activation`, `eeg_signal_mt`, `docs`, high-priority filenames |
| 2 | `eeg_labels`, `eeg_targets`, `eeg_level_t`, `eeg_level_m`, `label_adapter_readiness`, `label_contract_drafts`, `eeg_reader_preflight` |
| 3 | `signal_blocks`, `eeg_studies`, `configs` |
| 4 | CSV/TSV files in lower-priority stages |
| 5 | Unknown stage, quarantined |

---

## RAG Modes

| Mode | Used for |
|---|---|
| `artifact_explainer` | Runbooks, docs, general reports |
| `claim_card_generator` | Activation summaries |
| `topology_metric_explainer` | MT / Level-M / Level-T metric outputs |
| `dataset_status_assistant` | Label / adapter readiness artifacts |
| `intervention_safety_review` | Target injection artifacts |
| `paper_outline_generator` | Plan and report documents |
| `ontology_safe_mode` | Quarantined artifacts — **do not promote** |

---

## How to Index the First Batch

1. Run mock fixture to verify output shape.
2. Run against real artifacts.
3. Open `rag_index_priority.csv` and filter `index_priority == 1` and `claim_safety_status == safe`.
4. Load the corresponding records from `rag_artifact_manifest.jsonl`.
5. Feed to your RAG chunking pipeline using `recommended_rag_mode` as the prompt template selector.
6. Tag each chunk with `evidence_state` and `safe_claim` for provenance.

**Never index a quarantined artifact** until banned phrases are removed and a
human reviewer confirms safe framing.

---

## How to Handle Quarantined Artifacts

1. Open `quarantined_artifacts.json`.
2. For each entry, note `forbidden_claims_found`.
3. Edit the source file to remove or reframe the banned language.
4. Re-run P20.0 to verify the artifact is no longer quarantined.
5. A human reviewer must approve before adding to any chatbot knowledge base.

---

## How to Use with Notion

Export the `rag_ingestion_plan.md` and `report.md` to Notion pages manually, or
pipe `rag_artifact_manifest.jsonl` through the Awareness Studio
`export_sim_artifacts.py` tool (see `apps/awareness_studio/`).

P20.0 itself does **not** write to Notion.

---

## How to Use with Future Chatbot

Feed `rag_artifact_manifest.jsonl` to the Awareness Studio BM25 index builder:

```bash
cd apps/awareness_studio
awareness-index --force
```

The index builder will pick up new Markdown files from `inputs/sim_artifacts/`.
Use `export_sim_artifacts.py` to convert `RunRecord.json` artifacts first.

P20.0 outputs are designed to be compatible with that pipeline's input format.

---

## Guardrails

The following constraints are enforced by design:

- **no_external_api** — stdlib only, no HTTP calls
- **no_embeddings_created** — no vector generation
- **no_label_inference** — labels are not inferred from signal data
- **no_target_fabrication** — intervention targets are not generated
- **no_claim_promotion** — no metric is elevated to empirical status
- **no_contract_activation** — P11/P12/P13 gates are not touched
- **no_p11_gate_modification** — target-aware activation gate not modified
- **no_legacy_mt_real_change** — legacy mt_real files not modified
- **no_level_o** — Level-O is not implemented here
- **no_ontology_claims** — no consciousness/soul/liberation/afterlife claims
- **no_soul_afterlife_claims** — see above
- **no_liberation_claims** — see above

Any file containing a banned phrase is automatically quarantined (priority 5,
`ontology_safe_mode`) and excluded from the first-batch recommendation.

---

## Dependency Requirements

**Stdlib only.** No `pip install` required beyond what is already in
`requirements.txt`. P20.0 uses only:

- `argparse`, `datetime`, `hashlib`, `importlib`, `json`, `csv`, `pathlib`,
  `dataclasses`, `tempfile`, `sys`

---

## Tests

```bash
pytest tests/tools/test_build_awareness_rag_manifest.py -q
pytest tests/btc_icft/test_rag_artifact_manifest.py -q
```

All 32+ tests are offline and stdlib-only. No network access required.
