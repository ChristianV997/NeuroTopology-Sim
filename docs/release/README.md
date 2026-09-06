# Release evidence pack (Lead inventory + Research classification)

This directory is the **Lead inventory** plus **Research claim
classification** for assembling a repository evidence bundle. It records
what exists on GitHub and how each row is classified. It does **not**
compile evidence and does **not** invent a schema.

Research classification landed on
[`agent_contribution_matrix.yaml`](agent_contribution_matrix.yaml)
(2026-09-06; classifier `research_and_tooling`; base Lead commit
`be80bdd5db85b417dd5f15a5445d6c6a6bfd3368`). QA is next.

Inventory is not evidence. A listed PR, branch, or file set is not a
scientific `PASS`. Synthetic data cannot establish a scientific `PASS`.
The on-main Bayes factor path is a **proxy** and needs formal likelihood
validation before strong empirical interpretation.

This pack still does **not** contain `configs/release/evidence_schema.yaml`,
`scripts/compile_repository_evidence.py`, or
`tests/release/test_evidence_compiler.py`.

## Owned now (Lead + Research)

| Path | Role |
| --- | --- |
| [agent_contribution_matrix.yaml](agent_contribution_matrix.yaml) | Structured contribution records (Lead GitHub fields) plus `research_phase` and per-row `research_classification` |
| [current_state.md](current_state.md) | Human-readable snapshot, sectioned status, Lead warnings, Research classification table |

## Later phases (do not invent here)

| Later path | Owner | Role |
| --- | --- | --- |
| `configs/release/evidence_schema.yaml` | QA | Field/contract schema for compiled evidence |
| `scripts/compile_repository_evidence.py` | Release | Deterministic compiler over schema + inventory |
| `tests/release/test_evidence_compiler.py` | QA | Offline compiler tests |

Those files are **out of Research scope**. This index only names them so
QA / Release can attach without rewriting the inventory.

## Assembly order

1. **Lead** — inventory contributions (landed): repository, commits, PRs,
   merge status, file summaries, verification limits.
2. **Research** — **landed on this pack.** Classify each record
   (engineering vs scientific claim surface, data mode, missing reports,
   Bayesian-method caveats). Do not promote inventory rows to evidence.
3. **QA** — **next.** Write `evidence_schema.yaml` and compiler tests.
   Schema must refuse scientific `PASS` from synthetic data and refuse
   unverified author-claimed test counts as compiled evidence.
4. **Release** — implement `compile_repository_evidence.py` against the QA
   schema. Compiler output is a generated report. Not started.
5. **Integration** — recommendation only: what can be assembled, what is
   blocked, what must stay `NOT_SUPPORTED` / `INCONCLUSIVE`. Merger: do
   not merge.

## Generated reports

Compiler/eval/report artifacts must **not** be committed unless the caller
explicitly asks. Keep generated output under gitignored `artifacts/` (or
equivalent) and treat it as disposable.

## Guardrails

- No clinical claims, ontology promotion, proof claims, or theory-final
  language.
- No live APIs or credentials in tests.
- Synthetic fixtures cannot establish scientific `PASS`.
- The on-main Bayes factor path is a **proxy** (RSS/Gaussian likelihood
  ratio). It needs correction / formal likelihood validation before any
  strong empirical interpretation.
- PRs #210, #211, #212 remain unmerged unless independently verified as
  merged.
- `scientific-falsification` branch has no confirmed PR unless one is
  found.
- Missing Antigravity / Grok implementation reports are unverified.

Merger: **do not merge.**
