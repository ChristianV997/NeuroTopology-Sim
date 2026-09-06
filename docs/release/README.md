# Release evidence pack (Lead index)

This directory is the **Lead inventory** for assembling a repository evidence
bundle. It records what exists on GitHub. It does **not** compile evidence,
does **not** classify scientific status, and does **not** invent a schema.

Inventory is not evidence. A listed PR, branch, or file set is not a
scientific `PASS`.

## Owned now (Lead)

| Path | Role |
| --- | --- |
| [agent_contribution_matrix.yaml](agent_contribution_matrix.yaml) | Structured contribution records (verifiable GitHub fields only) |
| [current_state.md](current_state.md) | Human-readable snapshot, sectioned status, governance warnings |

## Later phases (do not invent here)

| Later path | Owner | Role |
| --- | --- | --- |
| `configs/release/evidence_schema.yaml` | QA | Field/contract schema for compiled evidence |
| `scripts/compile_repository_evidence.py` | Release | Deterministic compiler over schema + inventory |
| `tests/release/test_evidence_compiler.py` | QA | Offline compiler tests |

Those files are **out of Lead scope**. This index only names them so later
phases can attach without rewriting the inventory.

## Assembly order

1. **Lead** — inventory contributions (this pack): repository, commits, PRs,
   merge status, file summaries, verification limits.
2. **Research** — classify each record (engineering vs scientific claim
   surface, data mode, missing reports, Bayesian-method caveats). Do not
   promote inventory rows to evidence.
3. **QA** — write `evidence_schema.yaml` and compiler tests. Schema must
   refuse scientific `PASS` from synthetic data and refuse unverified
   author-claimed test counts as compiled evidence.
4. **Release** — implement `compile_repository_evidence.py` against the QA
   schema. Compiler output is a generated report.
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
