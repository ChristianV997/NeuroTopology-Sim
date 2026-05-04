# RAG Chatbot — Development Plan v0.1 (Scaffold + Patch Plan for Claude execution)

## Purpose

Plan and specify the implementation of the **Monk+Scientist RAG chatbot** so it can be executed later via **Claude Code** with minimal ambiguity.

## Scope (Phase 1)

- Build a **baseline RAG chatbot** (no scrapers, no simulations).
- Backend knowledge = **Awareness Research** pages.
- Persona = **Monk+Scientist**.
- Frontend control = operator prompts (Teach/Explain/Matrix/Card/CANONICAL).

## Architecture (minimal)

### Components

1. **Notion loader / markdown loader**
   - Loads pages from local markdown exports
   - Emits normalized documents: `{source_path, title, headings, text}`

2. **Chunker**
   - Heading-aware chunking
   - Attaches metadata: `{source_kind, heading_path, chunk_id}`

3. **Retrieval index**
   - Local: BM25 (offline, deterministic) or vector index (optional)
   - Stores chunks + metadata

4. **Retriever**
   - Top-k similarity
   - Metadata filtering by source_kind

5. **Answer synthesizer**
   - Uses Monk+Scientist system prompt
   - Supports control verbs: TEACH / EXPLAIN / ELABORATE / MATRIX / CARD / CANONICAL

6. **Evaluation (lightweight)**
   - Golden set (20–30 questions)
   - Metrics: faithfulness + relevancy

## Source kind taxonomy

- `book_system`: main book generation seed (El arte de soltar)
- `book_seed_q1`: Q1 autoayuda práctica
- `book_seed_q2`: Q2 Theravāda avanzado EBT
- `book_seed_q3`: Q3 escépticos ciencia-pop
- `book_seed_q4`: Q4 Liberation Engineering PhD
- `answer_templates`: Monk+Scientist answer templates
- `rag_plan`: this development plan
- `other`: any other document

## Chunk metadata schema

```
{
  "chunk_id": "<sha256[:16] of source_path|heading_path|sub_index>",
  "source_title": "<page title>",
  "source_path": "<local file path>",
  "source_kind": "<taxonomy value>",
  "heading_path": "<Section > Subsection>",
  "text": "<chunk text>",
  "index": <sequential integer>
}
```

## Golden test prompts (seed list)

Stress-test prompts for the chatbot:

1. `MATRIX: Explain taṇhā (craving) as gain and upādāna as latch.`
2. `TEACH: First vs second arrow (SN 36:6) for a modern audience.`
3. `EXPLAIN: Not-self via controllability — what does it rule out?`
4. `CARD: Convert DN 15 mutual dependency into an Evidence Card.`
5. `CANONICAL: Write a 100-word canonical paragraph about the cut-point strategy.`
6. `ELABORATE: What is consciousness in the context of Awareness Research?`
7. `EXPLAIN: Samsara — doctrine vs hypothesis vs metaphor.`

## Definition of Done (Phase 1)

- Local CLI answers questions with:
  - Role labels (direct teaching / method-synthesis / hypothesis)
  - Matrix compliance on request
  - Citations linking back to source files and chunk IDs used as context
- Tests pass for chunking and book generator structure.
- `pip install -e apps/awareness_studio` works.
- Deterministic output for same inputs (except LLM text).

## Patch plan

### Patch 1 — Scaffold + config
- Create folder structure, pyproject.toml, .env.example

### Patch 2 — Markdown ingestion
- Load .md files from inputs/notion_export/
- Infer source_kind from filename patterns

### Patch 3 — Chunking + metadata
- Heading-aware chunker with stable chunk IDs

### Patch 4 — BM25 index
- Build and persist BM25 index as JSON

### Patch 5 — Chat CLI + modes
- Implement TEACH/EXPLAIN/ELABORATE/MATRIX/CARD/CANONICAL outputs

### Patch 6 — Book generator
- Implement quadrant-aware chapter generation CLI
