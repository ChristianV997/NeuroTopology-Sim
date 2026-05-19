# ToL Knowledge Digest Pipeline (P27)

## Purpose
Deterministic stdlib-only ToL knowledge digestion for safe book/research planning.
## Input folder
`inputs/tol/` recursively (`.txt/.md/.tex/.json`, `.pdf` listed unsupported).
## Claim tiers
A `book_safe_core`, B `research_hypothesis`, C `speculative_quarantined`, D `unsafe_or_requires_rewrite`.
## Book-safe core
Uses high exit-cost / cheap exits framing as model language.
## Research hypotheses
Q/Qabs/fdress and related observables are candidate telemetry only.
## Quarantine policy
Speculative ontology, validated/proven claims, and unsafe therapeutic claims are quarantined.
## Doctrine-to-construct mapping
Produced in `doctrine_to_construct_map.json`.
## Observables map
Produced in `observables_map.json`.
## Obsidian outputs
Written under `obsidian/07_ToL/`.
## Validation
`python -m tools.tol_digest.validator` checks required outputs and language leakage.
## Guardrails
No real data, no network, no LLM calls, no ontology promotion.
## What this pipeline does not claim
No empirical proof, no clinical guarantees, no metaphysical validation.
## How to use for books
Run `make tol-digest` then use `book_insights.md` and chapter seeds.
## How to use for research
Use `research_hypotheses.md` + observables map + falsifiers sections.

## P28 synthesis stage
Run synthesis only from validated digest outputs, not raw ToL files.

Targets: `tol-book-spine`, `tol-research-roadmap`, `tol-public-language-guide`, `validate-tol-synthesis`, `tol-synthesis-cycle`.
