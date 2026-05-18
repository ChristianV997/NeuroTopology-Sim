# Run 41 — Theravāda Canon + SuttaCentral Connector Integration v0.1

## Purpose

Integrate the Theravāda digestion into Awareness Studio as a source-grounded doctrine layer, and prepare SuttaCentral/Bilara as a reproducible source connector.

## Core update

The Theravāda stack is now treated as a liberation-engineering layer for ToL / Awareness Research:

- Early suttas are the kernel: causal suffering, non-ownership, release, and nibbāna.
- Vimuttimagga and Visuddhimagga are the practice/compiler layer: virtue → concentration → wisdom.
- Paṭisambhidāmagga is the insight-analysis compiler.
- Nettippakaraṇa / Peṭakopadesa are interpretation compilers.
- Paṭṭhāna is the conditional-causality engine.

## Bondage sequence

contact → feeling → misreading → craving → clinging → becoming → identity lock → dukkha

ToL translation:

input → affective tagging → model error → control attempt → ownership → attractor deepening → high exit-cost

## Liberation sequence

dukkha → confidence → gladness → pīti → tranquility → ease → samādhi → clear seeing → disenchantment → dispassion → release

ToL translation:

stress signal → safe reorientation → positive affect → nervous-system coherence → stable attention → high-resolution insight → de-appropriation → fuel collapse → cheap exit

## High-leverage text map

| Text | Stack function | ToL variable | Research / writing use |
|---|---|---|---|
| SN 12.23 Upanisā | Positive dependent arising | affective stabilization → insight readiness | anti-nihilism protocol; path sequencing |
| AN 2.30 Vimutti | Two-axis release | passion-release + ignorance-release | ceto-vimutti / paññā-vimutti model |
| AN 5.26 Vimuttāyatana | Five liberation gates | hearing / teaching / reciting / reflecting / stillness | content pipeline + practice modalities |
| SN 22.59 Anattalakkhaṇa | Control-theory no-self | ownership mismatch / failed sovereignty | no-self as controllability falsifier |
| SN 22.14 Anattā | Minimal de-ownership | appropriation ↓ / exit-cost ↓ | aggregates are not ownable |
| Ud 8.1 / Ud 8.3 / Iti 44 | Nibbāna endpoint firewall | end of support / unconditioned cooling | prevent annihilationism and eternalism |
| Vimuttimagga | Practice engineering | protocol fit | sīla/samādhi/paññā implementation |
| Visuddhimagga | Technical instrumentation | stage markers / concentration diagnostics | advanced appendix, not source-kernel |
| Paṭisambhidāmagga | Analytical discernment | discriminative precision | insight as process-factorization |
| Netti / Peṭakopadesa | Hermeneutic compiler | text → function extraction | doctrine → mechanism → protocol cards |
| Paṭṭhāna | Conditional graph engine | paccaya / causal dependency | systems-science bridge |

## Canonical model statements

1. Suffering is the cost of defending a self-model against impermanence.
2. Liberation is the collapse of unnecessary ownership and control effort.
3. Nibbāna is not a metaphysical object but the cooling/unbinding that remains when greed, aversion, and delusion stop feeding the system.
4. The manuals are implementation layers; the early suttas remain the doctrinal kernel.
5. All doctrine cards must include source URI, translation, interpretation layer, ToL mapping, claim type, and ontology guardrail.

## SuttaCentral source hierarchy

1. SuttaCentral public text URLs for readable citation and user-facing references.
2. SuttaCentral JSON API / docs for programmatic lookup when stable.
3. Bilara data for segment-level root/translation alignment and offline reproducibility.
4. Notion doctrine cards for project-specific synthesis and ToL mapping.
5. Awareness Studio index for local RAG retrieval and book generation.

## Seed doctrine-card schema

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

## Initial seed set

- SN 12.2 — dependent origination core loop
- SN 12.23 — Upanisā positive liberation chain
- SN 22.12 — anicca aggregate algorithm
- SN 22.13 — dukkha aggregate algorithm
- SN 22.14 — anattā aggregate algorithm
- SN 22.59 — Anattalakkhaṇa control/no-self scaffold
- SN 22.89 — Khemaka subtle I-am residue
- SN 36.6 — Sallatha / second arrow
- AN 2.30 — Vimutti, greed/ignorance blockers
- AN 5.26 — Vimuttāyatana, five liberation opportunities
- MN 10 / DN 22 — Satipaṭṭhāna telemetry layer
- MN 118 — Ānāpānasati end-to-end training loop
- MN 106 — anti-state-clinging safeguard
- MN 111 — jhāna/arūpa factor decomposition
- Ud 1.10 — Bāhiya pre-ownership protocol
- Ud 8.1 / Ud 8.3 / Iti 44 — nibbāna endpoint firewall

## Acceptance gates

1. Connector runs offline tests without network by using small fixtures.
2. Live mode is opt-in only.
3. Every card has source_url, uid, text_role, tol_function, claim_type, and ontology_guardrail.
4. Generated Notion exports index through Awareness Studio without breaking existing BM25 / embedding index.
5. No claim is promoted beyond doctrine_scaffold unless paired with evidence artifacts.

## Book-ready thesis

The Buddha’s path is a causal technology of release.

The suttas identify the loop: experience becomes suffering when feeling is misread, craving moves toward control, clinging turns experience into “mine,” and becoming stabilizes the trapped identity.

The manuals explain how to train the system: ethics reduces turbulence, concentration lowers noise, wisdom deconstructs ownership, and repeated practice changes the conditional structure of the mind.

The analytical texts explain how to preserve precision: know the meaning, know the dhamma, know the conditions, know the interpretive frame, know what supports bondage and what supports release.

ToL translation:

> Suffering is the cost of defending a self-model against impermanence.
> Liberation is the collapse of that unnecessary control effort.
> Nibbāna is the cooling that remains when experience no longer has to become “me” or “mine.”
