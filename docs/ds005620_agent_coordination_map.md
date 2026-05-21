# DS005620 Agent Coordination Map

## 1. Purpose

This document defines the active work lanes for each agent (Claude, Codex, Copilot)
operating on the DS005620 repository, conflict-avoidance rules, PR cleanup protocol,
branch recovery protocol, and the required final report format.

This document does not change runtime behavior. It is a coordination reference only.

---

## 2. Current Active Lanes

| Agent | Current assignment | PR / branch |
|---|---|---|
| Claude | P20: DS005620 real artifact build operator | `claude/p20-*` |
| Codex | PR #114 ontology review governance merge; PR #122 obsolete branch cleanup | `codex/*` |
| Copilot | Navigation and operator-index layer (docs only) | `copilot/docs-operator-index-layer` |

---

## 3. Claude Lane

**Scope:** Deep implementation work, runtime operator modules, real/local gate planning,
complex pipeline logic.

**Current assignment:** P20 — DS005620 real artifact build operator.

**Active file surfaces:**
- `sciencer_d/btc_icft/p18/` (P18 operator modules)
- `sciencer_d/btc_icft/pipelines/` (new P20 pipeline entries)
- Any new real-data operator tools in `tools/`

**Do not touch:**
- Ontology governance templates and docs owned by Codex/PR #114
- Copilot-authored navigation docs in this PR
- Makefile (require separate PR for any Makefile changes)

---

## 4. Codex Lane

**Scope:** Validators, contract hardening, CI gates, stale PR cleanup, branch recovery,
strict generated-output checks.

**Current assignments:**
- Merge PR #114 (ontology review governance templates/checklists/docs/tests)
- Close PR #122 (obsolete conflict-resolution branch; contains no unique work beyond PR #121)
- Any unsubmitted branch recovery

**Active file surfaces:**
- `docs/` governance and ontology review docs (PR #114 surfaces)
- `tests/btc_icft/test_ontology_review_governance_docs.py` (PR #114 surface)
- `.github/ISSUE_TEMPLATE/` governance templates (PR #114 surface)
- `tools/validate_ontology_claim_language.py`
- `tools/validate_ds005620_generated_language.py`

**Do not touch while Codex is active:**
- P18/P20 implementation files (Claude owns)
- Copilot navigation docs added in this PR
- Makefile (require separate PR)

---

## 5. Copilot Lane

**Scope:** Docs, issue/PR templates, governance checklists, navigation maps,
reviewer/operator usability.

**Current assignment:** This PR — navigation and operator-index layer for DS005620.

**Active file surfaces (this PR only):**
- `docs/ds005620_system_index.md`
- `docs/ds005620_command_surface.md`
- `docs/ds005620_artifact_lifecycle.md`
- `docs/ds005620_agent_coordination_map.md`
- `tests/btc_icft/test_ds005620_system_index_docs.py`

**Do not touch in this PR:**
- Makefile
- `.github/pull_request_template.md`
- `.github/ISSUE_TEMPLATE/`
- `sciencer_d/btc_icft/p18/`
- `sciencer_d/btc_icft/runtime/`
- `sciencer_d/btc_icft/ontology/`
- `tools/validate_ontology_claim_language.py`
- `tools/validate_ds005620_generated_language.py`
- `contracts/btc_icft/ontology_claims/`
- `configs/btc_icft/`
- Any DS005620 executor/runtime/scientific code
- Any PR #114 surfaces until that PR is merged

---

## 6. Conflict-Avoidance Rules

1. **One agent owns runtime modules at a time.** Claude owns `sciencer_d/btc_icft/p18/`
   and `sciencer_d/btc_icft/pipelines/` implementation. Codex and Copilot must not edit
   these while Claude's P20 branch is open.

2. **One agent owns Makefile conflict merges at a time.** Makefile changes require a
   dedicated PR; never merge Makefile edits from a docs-only or test-only PR.

3. **Avoid editing same docs as PR #114 until merged.** PR #114 owns ontology governance
   docs and review templates. Do not edit those files until PR #114 is merged and closed.

4. **Do not create duplicate PRs.** Before opening a new PR, check whether an open PR
   already covers the same files or feature.

5. **Close superseded conflict PRs.** PR #122 should be closed as superseded by PR #121.
   It contains no unique work that is not already in main. Codex is assigned to close it.

6. **Rebase stale branches before adding new work.** Any branch that has diverged from
   main by more than a few commits must be rebased before adding new commits.

7. **Do not merge into another agent's open branch.** Coordinate via PR comments or the
   coordination map before touching another agent's active surface.

---

## 7. Files to Avoid During Active Work

The following files are under active development by other agents or PRs.
Do not edit these in a new PR until the owning PR is merged:

| File / directory | Owning lane | Owning PR |
|---|---|---|
| `docs/ds005620_review_governance.md` | Codex | PR #114 |
| `docs/ontology_review_governance.md` | Codex | PR #114 |
| `docs/ontology_claim_review_checklist.md` | Codex | PR #114 |
| `tests/btc_icft/test_ontology_review_governance_docs.py` | Codex | PR #114 |
| `.github/ISSUE_TEMPLATE/` | Codex | PR #114 |
| `sciencer_d/btc_icft/p18/` (new P20 modules) | Claude | P20 branch |
| `sciencer_d/btc_icft/pipelines/` (new P20 entries) | Claude | P20 branch |
| `Makefile` | Separate dedicated PR | N/A |

---

## 8. PR Cleanup Protocol

When a PR is superseded or made redundant by a merged PR:

1. Verify the superseded PR contains no unique commits not in main.
2. Add a comment to the PR explaining it is superseded and naming the PR that replaced it.
3. Close the PR (do not merge it).
4. Delete the branch if it is safe to do so (no other branch depends on it).
5. Update this coordination map if the PR was listed as active.

**Current known cleanup:**
- PR #122 should be closed as superseded. It contains only conflict-resolution commits
  for PR #121, which is already merged into main. Codex is assigned to close PR #122.
- PR #114 should be updated and merged by Codex after resolving any remaining conflicts.

---

## 9. Branch Recovery Protocol

If a branch has unsubmitted work or cannot be merged due to conflicts:

1. Fetch origin main: `git fetch origin main`.
2. Rebase the branch onto main: `git rebase origin/main`.
3. Resolve any conflicts by referring to the coordination map to determine the canonical owner.
4. Run the full test suite to verify no regressions.
5. Push the rebased branch and update the PR.
6. If the branch cannot be rebased cleanly (e.g., destructive conflicts), open a new branch
   from main and cherry-pick only the unique commits.
7. Document the recovery in a PR comment.

---

## 10. Required Final Report Format

Every agent PR must include a PR body with the following sections:

```
## Summary
[One paragraph describing what this PR does.]

## Why this is parallel-safe
[Explain which files are touched and why they do not conflict with other open PRs.]

## Files changed
[List of files added or modified.]

## What this documents / implements
[Describe the scope of the change.]

## What it does not change
[Explicitly list what is NOT changed: runtime code, Makefile, scientific semantics, etc.]

## Tests run
[List commands run and their outcomes.]

## Tests not run
[List any tests skipped and why (e.g., scipy/sklearn unavailable).]

## Guardrails preserved
[Confirm language gate, ontology gate, and contract gates still pass.]

## Open PRs intentionally not touched
[List open PRs and confirm no file overlap.]

## Next recommended PR
[Suggest the next logical step after this PR.]
```
