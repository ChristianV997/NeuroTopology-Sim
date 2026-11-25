# Merge-Gate Policy

Branch: `claude/merge-gate-policy`. Owns exclusively: `governance/merge_gate.py`,
`tests/governance/test_merge_gate.py`, `docs/governance/merge_gate_policy.md`.
Touches nothing in `tools/integration_reconciliation/**`,
`scripts/verify_integration_reconciliation.py`, any CI workflow, any PR
implementation file, scientific model code, signal adapters, streaming
tools, or dashboard routes.

## What this is

A pure, deterministic function — `governance.merge_gate.evaluate(MergeGateInput) -> MergeGateDecision`
— that turns a typed snapshot of a PR's reconciliation/CI/scientific/
governance state into exactly one of eight decisions, each with
machine-readable reason codes. It has **zero dependency** on
`tools/integration_reconciliation` (PR #218) or any GitHub client: a
caller builds the `MergeGateInput` from whatever data it already has (a
`ReconciliationEntry`, a hand-built dict, a CI webhook payload) and calls
`evaluate()`. This keeps the policy testable with plain in-memory
dataclasses and free of any coupling to an unmerged branch's internal
types.

## Decision states

| State | Meaning |
|---|---|
| `READY_FOR_REVIEW` | Nothing disqualifies the PR, but it is not yet mergeable (draft, no PR opened yet, or checks not all finished). |
| `READY_FOR_MERGE` | Every gate passed: not draft, no conflict, every required check (including governance/secret-scan) is `passing`, no scientific review pending, no dependency/duplicate/safety issue. |
| `BLOCKED_BY_DEPENDENCY` | The branch itself is missing, or the PR is stacked on an unresolved/unvalidated base. |
| `BLOCKED_BY_CI` | A required check (or the governance/secret-scan pseudo-checks) actually **failed** — a real code-level problem, or a real merge conflict. |
| `BLOCKED_BY_INFRASTRUCTURE` | A required check is `infrastructure_blocked` or `billing_blocked` — not a code defect. |
| `BLOCKED_BY_SCIENTIFIC_REVIEW` | The PR touches a scientific claim/path that needs a human scientist's sign-off, independent of CI status. |
| `BLOCKED_BY_DUPLICATE_OR_SUPERSEDED_WORK` | Reconciliation flagged this PR as a likely duplicate of, or superseded by, another branch, and no human has picked a winner yet. |
| `REJECTED_UNSAFE` | A hard, non-negotiable safety violation (see Tier 0 below) — never "needs review," definitively rejected as written. |

## Priority order (why a PR gets exactly one decision)

Rules are evaluated in a fixed tier order, most severe first, and the
function returns at the first tier that fires:

1. **Tier 0 — hard safety rejections** (`REJECTED_UNSAFE`): dashboard
   imports a solver; synthetic data claims an empirical `PASS`; a proxy
   Bayes factor is offered to satisfy a formal-evidence gate. These are
   checked before anything else — a PR this unsafe is rejected even if
   every other gate is green.
2. **Tier 1 — duplicate/superseded work** (`BLOCKED_BY_DUPLICATE_OR_SUPERSEDED_WORK`):
   checked ahead of dependency/CI state, since merging duplicate or
   already-superseded work is wasted regardless of its own CI status.
3. **Tier 2 — stacked dependency** (`BLOCKED_BY_DEPENDENCY`).
4. **Tier 3 — branch/PR existence**: a missing branch is
   `BLOCKED_BY_DEPENDENCY` (`BRANCH_NOT_PRESENT`); a missing PR (branch
   exists, no PR yet) is `READY_FOR_REVIEW` (`NO_PR_YET`) — there's
   nothing to gate yet, and this isn't a failure state.
5. **Tier 4 — scientific review**: checked *before* the CI-check
   aggregation, deliberately, per "scientific claims require stricter
   gates than ordinary code changes" — a PR needing scientific review is
   reported as such even when a plain check also happens to be failing,
   so it's never mistaken for "just a CI problem."
6. **Tier 5 — required-check aggregation**: `governance_validated` and
   `secret_scan_clean` are folded into the same check-state vocabulary as
   `required_checks` (as pseudo-checks named `"governance"`/
   `"secret_scan"`), so rules 1, 2, and 7 are all implemented by one pass
   over one dict:
   - any `infrastructure_blocked` check → `BLOCKED_BY_INFRASTRUCTURE`
     (`INFRASTRUCTURE_BLOCKED`)
   - any `billing_blocked` check → `BLOCKED_BY_INFRASTRUCTURE`
     (`BILLING_BLOCKED` — a **distinct** reason code in the **same**
     decision bucket, so a caller can tell "disk full" from "spending
     limit hit" without needing a ninth decision state)
   - any `failing` check → `BLOCKED_BY_CI` (`CHECK_FAILING`)
   - anything else non-`passing` (`pending`/`not_run`/`mixed`/an
     unrecognized string) → not yet `READY_FOR_MERGE` (falls through to
     tier 6)
7. **Tier 6 — draft / conflict / completeness**: `draft=True` →
   `READY_FOR_REVIEW` (`DRAFT`); `mergeable=False` → `BLOCKED_BY_CI`
   (`MERGE_CONFLICT` — there is no dedicated "merge conflict" decision
   state in the required eight, so a real git conflict is reported under
   `BLOCKED_BY_CI` with that specific reason code); any check still
   incomplete → `READY_FOR_REVIEW` (`CHECKS_INCOMPLETE`, naming which
   checks); otherwise → `READY_FOR_MERGE` (`ALL_GATES_PASSED`).

## Rule-by-rule mapping

| # | Rule (as given) | Implementation |
|---|---|---|
| 1 | A PR with unstarted checks is not passing. | Any check state other than `"passing"` is excluded from the passing set; `not_run`/`pending`/`mixed`/unrecognized all fall through to "not yet ready," never silently treated as passing. |
| 2 | Billing-blocked checks are not test failures and are not passes. | `billing_blocked` is checked and returned **before** the `failing` check, under `BLOCKED_BY_INFRASTRUCTURE` with its own `BILLING_BLOCKED` reason code — never `BLOCKED_BY_CI`, never `READY_FOR_MERGE`. |
| 3 | A scientific PR with synthetic PASS claims is rejected. | `synthetic_data_claims and claims_empirical_pass` → `REJECTED_UNSAFE` (`SYNTHETIC_EMPIRICAL_PASS_CLAIM`), Tier 0. |
| 4 | A proxy Bayes factor cannot satisfy a formal evidence gate. | `requires_formal_bayes_factor and bayes_factor_evidence_kind == "proxy"` → `REJECTED_UNSAFE` (`PROXY_BAYES_FACTOR_FOR_FORMAL_GATE`), Tier 0. |
| 5 | A stacked PR cannot be merge-ready until its dependency is resolved or its effective diff is independently validated. | `is_stacked and not (stack_dependency_resolved or effective_diff_independently_validated)` → `BLOCKED_BY_DEPENDENCY`, Tier 2 (either escape hatch clears it). |
| 6 | A dashboard route importing a solver is rejected. | `dashboard_imports_solver` → `REJECTED_UNSAFE` (`DASHBOARD_IMPORTS_SOLVER`), Tier 0. |
| 7 | Missing governance or secret validation blocks merge. | `governance_validated`/`secret_scan_clean` folded into the required-check aggregation (Tier 5) as pseudo-checks; `None` (not run) keeps the PR out of `READY_FOR_MERGE` via rule 1; an explicit `False` is a real failure → `BLOCKED_BY_CI`. |
| 8 | Duplicate work requires an explicit replacement decision. | `(duplicate or superseded) and not explicit_replacement_decision` → `BLOCKED_BY_DUPLICATE_OR_SUPERSEDED_WORK`, Tier 1; setting `explicit_replacement_decision=True` is the only way past it. |
| 9 | The policy must be pure and network-free. | `governance/merge_gate.py` imports only `dataclasses`/`typing`; `evaluate()` takes a value and returns a value, no I/O, no clock, no randomness — verified by `test_no_network_or_filesystem_imports_in_merge_gate_module` (an AST scan of the module's own imports) and `test_evaluate_is_deterministic_across_many_repeats`/`test_evaluate_is_deterministic_for_every_decision_branch` (200 and 20×16 repeat calls respectively, asserting identical output). |
| 10 | Output must include machine-readable reason codes. | Every `MergeGateDecision.reason_codes` is a non-empty tuple of plain strings (never an empty tuple, never a translated/localized message) — verified by `test_every_decision_has_at_least_one_reason_code` across all thirteen input scenarios. |

## Deliberate design choices worth flagging

- **No dedicated "merge conflict" or "billing-blocked" decision state
  exists** in the required eight-state enum. Both are folded into an
  existing bucket (`BLOCKED_BY_CI`/`BLOCKED_BY_INFRASTRUCTURE`
  respectively) with a distinguishing reason code instead. A future
  revision could add dedicated states if the fixed eight ever needs
  extending; this module does not do so on its own initiative.
- **`bayes_factor_evidence_kind=None` with `requires_formal_bayes_factor=True`
  is NOT rejected by rule 4.** The rule fires only on an explicit
  proxy-for-formal substitution, not on the mere absence of a
  Bayes-factor claim — a PR that makes no Bayes-factor claim at all isn't
  lying about one.
- **Scientific review is checked before CI completeness (Tier 4 before
  Tier 5)**, reflecting "scientific claims require stricter gates than
  ordinary code changes" — a scientific PR is never reported as merely
  CI-blocked when it also needs a human scientist's sign-off.
- **A missing PR (`pr_present=False`) is `READY_FOR_REVIEW`, not a
  blocked state.** There is nothing yet to gate — this mirrors PR #218's
  own reconciliation finding that a branch existing with no PR
  (`codex/scientific-falsification-contract`) is a distinct, non-failure
  state from a PR that exists and is failing its checks.

## Test commands

```bash
PYTHONPATH=. python -m pytest tests/governance/test_merge_gate.py -q   # 52 passed
python -m governance.validate                                          # 4/4 specs pass (baseline, unaffected)
python -m compileall -q governance/merge_gate.py tests/governance
```

No test in `tests/governance/test_merge_gate.py` touches the filesystem,
a socket, or a subprocess — every input is an in-memory `MergeGateInput`
constructed directly in the test file.

## Policy examples

```python
from governance.merge_gate import MergeGateInput, evaluate

# A stacked PR whose base hasn't merged yet.
evaluate(MergeGateInput(
    branch_present=True, pr_present=True, is_stacked=True,
    stack_dependency_resolved=False, required_checks={"tests": "passing"},
    governance_validated=True, secret_scan_clean=True,
))
# -> MergeGateDecision(decision='BLOCKED_BY_DEPENDENCY', reason_codes=('STACKED_DEPENDENCY_UNRESOLVED',), ...)

# A CI failure caused by disk exhaustion, not a code defect (PR #218's
# real finding for PRs #210-#222).
evaluate(MergeGateInput(
    branch_present=True, pr_present=True, draft=True,
    required_checks={"core-tests": "infrastructure_blocked", "awareness-tests": "passing"},
    governance_validated=True, secret_scan_clean=True,
))
# -> MergeGateDecision(decision='BLOCKED_BY_INFRASTRUCTURE',
#                       reason_codes=('INFRASTRUCTURE_BLOCKED', 'core-tests'), ...)

# A synthetic-data PR that claims an empirical PASS.
evaluate(MergeGateInput(
    branch_present=True, pr_present=True,
    synthetic_data_claims=True, claims_empirical_pass=True,
))
# -> MergeGateDecision(decision='REJECTED_UNSAFE', reason_codes=('SYNTHETIC_EMPIRICAL_PASS_CLAIM',), ...)

# Everything green.
evaluate(MergeGateInput(
    branch_present=True, pr_present=True, draft=False, mergeable=True,
    required_checks={"tests": "passing"},
    governance_validated=True, secret_scan_clean=True,
))
# -> MergeGateDecision(decision='READY_FOR_MERGE', reason_codes=('ALL_GATES_PASSED',), ...)
```
