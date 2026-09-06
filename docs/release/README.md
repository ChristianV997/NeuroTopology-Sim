# Release evidence pack — Lead inventory + Research classification

This directory is the **Lead inventory** (superseding #216 inventory
docs) plus **Research claim classification** for assembling a
repository evidence bundle. It records what exists on GitHub and how
Research classifies each row. It does **not** compile evidence and does
**not** invent a schema, compiler, validator, or evidence queue.

## Supersede of PR #216 (inventory docs only)

This compilation PR ([#225](https://github.com/ChristianV997/NeuroTopology-Sim/pull/225))
is a **delta / supersede of draft PR #216**
(`grok-bot/evidence-bundle-release`, FINAL `078412848d99a1cb7fa31666d24fdcca96d5ac4a`).
#216 is `SUPERSEDED` for inventory docs by #225.

- **This pack refreshes only** [`agent_contribution_matrix.yaml`](agent_contribution_matrix.yaml)
  and [`current_state.md`](current_state.md).
- **Do not open a second evidence authority.** QA schema
  (`configs/release/evidence_schema.yaml`), Release compiler
  (`scripts/compile_repository_evidence.py`), and `tests/release/**`
  remain on **#216**. They are not copied, forked, or rewritten here.
- #216 remains the **schema / compiler / validator** pack. This branch
  supersedes **#216 inventory docs only**.

## Owned now (Lead + Research)

| Path | Role |
| --- | --- |
| [agent_contribution_matrix.yaml](agent_contribution_matrix.yaml) | Structured contribution records (live GitHub fields + allowed status categories + Research classifications for #215–#222) |
| [current_state.md](current_state.md) | Human-readable snapshot, stacked PRs, CI billing vs disk, scientific warnings, Research claim classification table |

## Assembly order (unchanged)

Phases are still **Lead → Research → QA → Release → Integration**.

1. **Lead** — this pack. Inventory contributions: repository, commits,
   PRs, merge status, file summaries, verification limits. Inventory is
   not evidence.
2. **Research** — **landed on this #225 inventory** (2026-09-06).
   Classified new/refreshed rows #215–#222 (claim surface, data mode,
   stacked parents, Bayesian caveats, RSS vs tracemalloc, adapters).
   Do not promote inventory rows to evidence. Do not invent scientific
   `PASS`. Carried-forward #216 Research blocks on older rows still
   apply.
3. **QA** — **next (delta only)** on the existing #216
   `evidence_schema.yaml` and compiler tests. Do not invent a second
   schema on this branch.
4. **Release** — owns `compile_repository_evidence.py` **on #216**.
   Compiler output is a generated report, not scientific `PASS`.
5. **Integration** — recommendation only: what can be assembled, what is
   blocked, what must stay `NOT_SUPPORTED` / `INCONCLUSIVE`. Merger: do
   not merge.

Schema / compiler / `tests/release/**` remain **#216** authority.
#225 supersedes #216 inventory docs only. QA consumes this classified
inventory as a **delta**, not a second evidence pack.

## Status categories (Lead; use only where verifiable)

`VERIFIED_MERGED` | `OPEN_REVIEW` | `DRAFT_REVIEW` | `BRANCH_ONLY` |
`CI_BLOCKED` | `BILLING_BLOCKED` | `SUPERSEDED` | `DUPLICATE` |
`SCIENTIFIC_REVIEW_REQUIRED` | `UNVERIFIED`

## Guardrails

- Inventory ≠ evidence. A listed PR, branch, or file set is not a
  scientific `PASS`.
- PRs are not merged unless GitHub says `merged`.
- CI billing failure ≠ passing tests. Disk-full install failure ≠
  passing tests.
- Proxy Bayes ≠ formal Bayes factors.
- Synthetic ≠ biological evidence.
- Process-memory numbers must say RSS vs tracemalloc when known;
  otherwise unavailable.
- Missing adapters ≠ supported.
- No clinical claims, ontology promotion, proof claims, or theory-final
  language.
- No live APIs or credentials in tests.
- `codex/scientific-falsification-contract` is **branch-only** (no PR).
- #215 is **STACKED** on #211.

Merger: **do not merge.**
