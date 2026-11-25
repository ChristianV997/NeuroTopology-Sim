# Integration State Lock

Branch: `claude/integration-state-lock`, based on latest `origin/main`.
Owns exclusively: `tools/integration_state/**`,
`scripts/verify_integration_state.py`, `tests/integration_state/**`,
`docs/release/integration_state_lock.md`. Touches nothing in
`tools/integration_reconciliation/**`, PR #236's implementation files,
`governance/merge_gate.py`, any CI workflow, Bayesian/streaming/adapter
code, dashboard routes, datasets, or generated artifacts.

## What this is

A read-only verifier that answers, with evidence: "which commit is
*actually* the head of this integration effort, right now, and does
every previously-reported handoff commit fit consistently into that
picture?" It never trusts a handoff's own prose — every commit hash is
resolved against real git objects (local fixture repos in tests, or a
real checkout in the live CLI) or a pre-fetched GitHub PR snapshot
this package only ever reads, never fetches itself.

## A real bug this branch's own development caught

`git rev-parse --verify --quiet <hash>` treats a well-formed 40-character
hex string as syntactically valid and reports it "verified" **even when
no object with that hash exists in the repository at all** — only a
short/abbreviated hash actually triggers git's object-database lookup.
An early version of `git_source.ref_exists`/`resolve_commit` used the
bare form and consequently misclassified a fabricated 40-character hash
sharing a real commit's 8-character prefix as `"stale"` (a real,
resolvable, off-lineage commit) instead of `"unknown"` (does not exist at
all) — exactly the blind spot this tool exists to close, since it is
exactly what a hallucinated or truncated-then-padded handoff hash looks
like. Fixed by appending `^{commit}` to every `rev-parse --verify`
call, which forces git to actually dereference and confirm the object
exists and is a commit. Caught by
`test_unknown_classification_for_unresolvable_commit` and
`test_pr_body_final_commit_claim_that_does_not_exist_is_unknown_and_contradictory`,
both of which failed before the fix and pass after.

## The four commit classifications (requirement 9)

| Classification | Meaning |
|---|---|
| `current_head` | The claimed commit IS the authoritative head, exactly. |
| `ancestor` | Resolves to a real object and is a git ancestor of the head — a genuine, earlier point in the SAME line of history (the normal shape of an old-but-honest handoff). |
| `stale` | Resolves to a real object, but is NEITHER the head NOR an ancestor of it — it exists somewhere (a diverged branch, an abandoned line) but off the authoritative line entirely. |
| `unknown` | Does not resolve to any real git object at all — cannot be verified, whether mistyped, truncated, fabricated, or never pushed anywhere this checkout can see. |

## The six check states (requirement 13)

`passing`, `failing`, `pending`, `skipped`, `infrastructure_blocked`,
`unavailable` (no status/conclusion data supplied at all, or the
conclusion is unrecognized — never silently treated as passing). A bare
`"failure"` conclusion with no supporting `failure_signature` is reported
as `failing`, never quietly downgraded to `infrastructure_blocked`
without matching evidence — the same non-negotiable rule this
reconciliation effort has applied throughout.

## "Never infer merge completion from a local merge commit alone"

`merge_verification.verify_integrated_pr_history` explicitly labels a
found merge commit as evidence the PR's *code* landed on the branch —
**not** evidence that GitHub's own `merged` field for that PR is true.
`merge_verification.check_merged_into_main` treats the PR snapshot's own
`merged` field as authoritative when supplied, reports local git ancestry
only as *supporting* evidence, and explicitly flags (never silently
resolves) a disagreement between the two — e.g. a branch that IS a git
ancestor of `main` while its PR is not marked merged, or vice versa. With
no PR snapshot at all, `pr_merged` is `None`, never a guess derived from
ancestry alone.

## Manual dry-run against the real PR #236 (2026-09-07)

Live head fetched via `mcp__github__pull_request_read`:
`af3ac584419148ddcfc57cb565c416eba6328725`. Three previously-reported
handoff commits were checked against it, plus the PR's own body text:

```bash
python scripts/verify_integration_state.py \
  --repo-path . --integration-branch origin/codex/integration-all-open-prs --main-ref origin/main \
  --pr-snapshot tests/integration_state/fixtures/real_pr236_snapshot_2026-09-07.json \
  --handoff-claim "round1=3b36cb5fb15cd1b5a8fc2ea1ceb9319e3cbe3d44" \
  --handoff-claim "round2=be277ecdac301d49dca27ef9612ebe6c560245ad" \
  --handoff-claim "round3_latest_handoff=af3ac584419148ddcfc57cb565c416eba6328725"
```

| Handoff | Classification |
|---|---|
| `3b36cb5fb15cd1b5a8fc2ea1ceb9319e3cbe3d44` | `ancestor` (real, superseded) |
| `be277ecdac301d49dca27ef9612ebe6c560245ad` | `ancestor` (real, superseded) |
| `af3ac584419148ddcfc57cb565c416eba6328725` | `current_head` (matches live `head_sha`) |
| PR body's own `"Final commit: `af3ac584277747ae29882d3f5a39af5c4a436f22`"` | **`unknown`** |

**The PR's own body text names a commit that does not exist anywhere in
this repository.** `af3ac584277747ae29882d3f5a39af5c4a436f22` shares only
the real head's 8-character prefix `af3ac584`; `git cat-file -t` on the
full hash returns "could not get object info." All three of `3b36cb5`,
`be277ecd`, and `af3ac584419148...` form a clean, non-contradictory
progression (each a real ancestor of the next) — the mission's premise
that "the state must always be verified from live GitHub metadata" is
borne out exactly: two are genuinely stale-but-honest, one is current,
and a fourth, never-flagged claim (the PR's own prose) turns out to be
unverifiable.

**Integrated-PR history check, an honest limitation:** of the 27 PR
numbers this PR's own body claims were integrated, this checkout's
`find_merge_commit_for_pr_number` (a literal search for `"#NNN "` /
`"(#NNN)"` / `"pull request #NNN"` in commit subjects) found a match for
only about a third of them (#209-#214, #217-#219, #221, #225, #227). This
is not evidence the rest were NOT integrated — many were very likely
squash-merged with a commit message that doesn't match this literal
pattern — it is only evidence of what this specific, conservative search
could and could not confirm. The tool reports exactly that distinction
rather than assuming the branch's own claim is correct for the PRs it
could not independently verify.

**Merged into main:** `False`, from the PR snapshot's own `merged` field
— consistent with local ancestry (`is_head_ancestor_of_main=False`) and
with PR #236's own body ("It is intentionally open; no merge to `main`
is claimed").

**Check classification:** the single `required-checks` entry classifies
as `infrastructure_blocked`, using the PR body's own description of the
failure ("GitHub Actions checks currently fail before usable steps/logs")
as the `failure_signature` evidence — not a bare `"failure"` conclusion
accepted at face value.

## Test commands

```bash
PYTHONPATH=. python -m pytest tests/integration_state -q   # 57 passed
python -m governance.validate                               # 4/4 specs pass (baseline, unaffected)
python -m compileall -q tools/integration_state scripts/verify_integration_state.py tests/integration_state
```

No test opens a socket or fetches anything: `tests/integration_state/conftest.py`
builds a real, local-only git fixture repo per test via subprocess `git`,
and every GitHub-side fact in a test is a literal in-memory `PRSnapshot`
or a small JSON fixture file.

## Required test scenarios (all covered)

current head · stale head · intermediate commit · branch missing · PR
missing · integrated-only branch · merged into main · contradictory
handoffs · failed CI · unavailable logs · deterministic repeat (15
repeat calls, byte-identical `to_dict()` output) — see
`tests/integration_state/test_state.py`.
