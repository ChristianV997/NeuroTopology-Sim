# SuttaCentral + Theravāda Canon Integration

This document defines the Awareness Research contract for integrating SuttaCentral/Bilara sources into ScienceR-Dsim and Awareness Studio.

## Purpose

The goal is not to scrape random Buddhist text. The goal is to make Theravāda doctrine cards reproducible, cited, and claim-governed inside the Awareness Research stack.

The SuttaCentral integration should support:

- canonical sutta lookup by UID, e.g. `sn12.23`, `sn22.59`, `mn118`, `ud8.3`;
- stable source URLs for user-facing citation;
- optional Bilara segment alignment for root text + translation;
- doctrine-card export to Markdown and JSONL;
- Awareness Studio indexing through `inputs/notion_export/*.md` or a future source adapter;
- ontology guardrails so doctrine scaffolds are not promoted into empirical claims.

## Source hierarchy

1. **SuttaCentral public text URLs** for readable citation and user-facing references.
2. **SuttaCentral JSON API / docs** for programmatic lookup when available/stable.
3. **Bilara data** for segment-level root/translation alignment and offline reproducibility.
4. **Notion doctrine cards** for project-specific synthesis and ToL mapping.
5. **Awareness Studio index** for local RAG retrieval and book generation.

## Why SuttaCentral/Bilara fits this repo

ScienceR-Dsim already treats EEG-derived topology as exploratory and requires careful claim promotion. The same governance should apply to doctrine:

- Early suttas are **doctrine scaffolds**, not empirical proof.
- Commentarial manuals are **implementation layers**, not the source kernel.
- ToL/BTC-EFT mappings are **interpretive bridges**, not canonical claims.
- Scientific promotion requires evidence artifacts, nulls, and acceptance gates.

## Initial sutta seed set

| UID | Text | Project role | ToL function |
|---|---|---|---|
| `sn12.2` | Dependent Origination | causal loop | lock-in production pipeline |
| `sn12.23` | Upanisā | positive liberation chain | affective stabilization → insight → release |
| `sn22.12` | Anicca | aggregate algorithm | metastability / impermanence |
| `sn22.13` | Dukkha | aggregate algorithm | structural stress under grasping |
| `sn22.14` | Anattā | aggregate algorithm | de-ownership of aggregates |
| `sn22.59` | Anattalakkhaṇa | control-theory no-self | failed ownership/control mismatch |
| `sn22.89` | Khemaka | subtle self residue | residual "I am" gravity |
| `sn36.6` | Sallatha / Arrow | affective reactivity | second-arrow amplification |
| `an2.30` | Vimutti | two-axis release | passion-release + ignorance-release |
| `an5.26` | Vimuttāyatana | liberation opportunities | hearing/teaching/reciting/reflecting/stillness |
| `mn10` / `dn22` | Satipaṭṭhāna | live telemetry | body/feeling/mind/dhamma dashboard |
| `mn118` | Ānāpānasati | training backbone | breath → mindfulness → awakening factors → release |
| `mn106` | Āneñjasappāya | anti-state-clinging | do not relish/welcome/fasten to refined states |
| `mn111` | Anupada | state decomposition | jhāna/arūpa factor analysis |
| `ud1.10` | Bāhiya | ownership cutoff | in the seen only the seen |
| `ud8.1` / `ud8.3` / `iti44` | Nibbāna texts | endpoint firewall | unconditioned/cooling without reification |

## Doctrine card schema

Each ingested card should emit at least:

```json
{
  "uid": "sn12.23",
  "title": "Upanisā Sutta",
  "collection": "SN",
  "source_url": "https://suttacentral.net/sn12.23",
  "source_kind": "suttacentral",
  "translation_lang": "en",
  "translator": "configured_or_unknown",
  "root_lang": "pli",
  "canonical_weight": "EBT_high",
  "text_role": "positive_causal_chain",
  "tol_function": "affective_stabilization_to_release",
  "variables": ["dukkha", "saddha", "piti", "samadhi", "nibbida", "viraga", "vimutti"],
  "claim_type": "doctrine_scaffold",
  "ontology_guardrail": "do not reify path variables as substances",
  "summary": "Positive dependent arising from suffering through joy, calm, concentration, clear seeing, disenchantment, dispassion, and liberation."
}
```

## Claim typing

Use the same Awareness Research governance pattern:

- `doctrine_scaffold`: canonical or commentarial doctrine used as conceptual scaffolding.
- `interpretive_bridge`: ToL/BTC-EFT mapping from doctrine to systems language.
- `practice_protocol`: actionable training interpretation.
- `empirical_hypothesis`: testable claim requiring data.
- `quarantined_speculation`: metaphysical or substrate claim that must not be promoted.

## Acceptance gates

1. Connector must run offline tests using small fixtures.
2. Live network mode must be opt-in.
3. Every card must include `uid`, `title`, `collection`, `source_url`, `source_kind`, `translation_lang`, `text_role`, `tol_function`, `claim_type`, `ontology_guardrail`, and `summary`.
4. Markdown exports must index through Awareness Studio without breaking BM25 or embedding backends; rebuild with `cd apps/awareness_studio && python -m awareness_studio.index_build --force` after adding or editing Theravāda doctrine cards.
5. No doctrine card may be promoted to empirical evidence without linked artifacts in the Evidence Ledger.

## Implementation phases

### Phase 1 — Seed export

Add static JSONL + Markdown seed cards for the high-leverage suttas so Awareness Studio can index them immediately.

### Phase 2 — Client scaffold

Add a small stdlib-only client or adapter that can resolve `uid → source_url → doctrine card` and optionally parse cached fixture data.

### Phase 3 — Bilara alignment

Add local fixture support for Bilara-style segment dictionaries: root, translation, html, comment, variant.

### Phase 4 — Notion sync

Emit doctrine cards that can be exported to Notion or indexed locally. Notion remains the synthesis layer; Git remains the reproducible source contract.

## Ontology firewall

The connector must not encode metaphysical claims as facts. It should support language like:

- "SN 22.59 functions as a control-theory no-self scaffold."
- "AN 2.30 supports a two-axis release model: passion-release and ignorance-release."
- "Ud 8.3 acts as an endpoint firewall against annihilationism and eternalism."

It must avoid any wording that:

- promotes suttas into evidence for consciousness-topology claims;
- equates Nibbāna with project telemetry such as Q, Qabs, or fdress;
- treats Q, Qabs, or fdress as Buddhist canonical doctrine items.

## Book/RAG use

Awareness Studio answer modes should treat these cards as high-priority sources for:

- Q2 Theravāda advanced book voice;
- Monk+Scientist RAG answers;
- sutta doctrine cards;
- source-grounded chapter generation;
- ToL matrix outputs.
