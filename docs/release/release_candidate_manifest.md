# Release Candidate Manifest

This document describes the read-only release-candidate manifest builder in
`tools/release_manifest`. The builder uses local Git facts and an optional
pre-fetched JSON snapshot for GitHub-side facts; it does not contact GitHub or
any other network service.

## What this is

A read-only, deterministic builder for `ReleaseCandidateManifest.v1`: a
single artifact that answers, per release candidate, "is this actually
merged into `main`, only present on an integration branch, open but
unintegrated, stale/off-lineage, superseded, a duplicate of someone
else's changed files, or blocked — and by what, specifically?" Every
field is an `Evidence(value, source)` pair (never a bare value), commit
identity is verified with real git object resolution (never a
well-formed-but-fake hash), and GitHub-side facts come only from an
optional pre-fetched JSON snapshot this package reads, never fetches.

## `ReleaseCandidateManifest.v1` schema

See `tools/release_manifest/models.py` for the full dataclass. Top-level
shape (`to_dict()`):

```
schema, repository, target_branch, integration_branch, source_commit,
verified_head_commit: Evidence, pr_number: Evidence, pr_status: Evidence,
draft_status: Evidence, branch_ancestry: dict, changed_file_ownership: dict,
duplicate_file_findings: list, ci_classifications: dict,
test_summary: dict|null, governance_status: Evidence,
scientific_gate_status: Evidence, dashboard_isolation_status: Evidence,
memory_timeout_status: Evidence, merge_state: str, merge_eligibility: bool,
release_state: str, release_eligibility: bool,
blockers: list[str], github_state: "available"|"unavailable",
provenance: dict, generated_at: str|null   # only populated when explicitly requested
```

`governance_status`, `dashboard_isolation_status`, and
`memory_timeout_status` are schema fields this tool always populates as
`Evidence("not evaluated by this tool", "out of scope for release_manifest")`
— this package does not import `governance/merge_gate.py` or any
dashboard/timeout code (owned by sibling branches), so it never fabricates
a verdict for them; a caller that has that data can overwrite those fields
before serializing.

## Integration State Is Not Release Readiness

`merge_state` and the legacy `merge_eligibility` field describe technical
target-branch reachability only. They answer whether git ancestry or a
GitHub snapshot shows that a commit landed; they are not a scientific or
operational approval.

`release_state` and `release_eligibility` are independent fields. A commit
that is technically `merged_into_main` remains `blocked_by_scientific_review`,
`blocked_by_ci`, `blocked_by_infrastructure`, `blocked_by_dependency`, or
`inconclusive` until its independent gates are admissible. The current
metadata-only scientific gate intentionally cannot emit `ready_for_release`.
Release readiness also requires classified CI to be `passing`; `pending`,
`skipped`, and `unavailable` CI states remain `inconclusive` rather than being
treated as a release pass.

## The 11 merge states, and their priority order

Full rationale lives as a module docstring in
`tools/release_manifest/merge_state.py`; summary:

| Priority | State | Meaning |
|---|---|---|
| 1 | `unknown` (commit unresolvable) | The claimed commit is not a real git object — includes the fabricated-hash case. Nothing else is evaluated once identity itself is unverifiable. |
| 2 | `merged_into_main` | Real ancestry places the commit on `target_branch`, **or** the PR snapshot's own `merged` field is `True`. A disagreement between the two is recorded as a blocker note, never silently resolved, but the release is still reported merged when it plainly landed. |
| 3 | `duplicate` | This work's changed-file set overlaps another concurrent owner's above the Jaccard/shared-file threshold (and isn't already merged). |
| 4 | `blocked_by_scientific_review` | The scientific gate reports a genuinely evidenced negative verdict (not merely missing data). |
| 5 | `blocked_by_ci` | Worst classified CI check is `failing`. |
| 6 | `blocked_by_infrastructure` | Worst classified CI check is `infrastructure_blocked` — strictly below a real `failing`, so an evidenced failure never gets hidden behind an infrastructure excuse. |
| 7 | `blocked_by_dependency` | Caller-supplied unmet-dependency list is non-empty. |
| 8 | `superseded` | PR closed without merging, and a later reference is named as covering the same ground. |
| 9 | `integration_only` | Real ancestry places the commit on `integration_branch` but not `target_branch`. |
| 10 | `ancestor_stale` | Commit is a real object but off every known lineage. |
| 11 | `open_unintegrated` | A PR snapshot exists and is open, but ancestry places it nowhere specific. |
| 12 | `unknown` (fallback) | Absence of data, not evidence of a problem — most often `github_state=unavailable` plus no local ancestry signal. |

## The six CI check states and four commit classifications

Reused conceptually (not imported) from the same conventions established
by `tools/integration_state` and `tools/release_scientific_audit` earlier
in this effort:

- CI: `passing`, `failing`, `pending`, `skipped`, `infrastructure_blocked`,
  `unavailable`. A bare `"failure"` conclusion with no
  `failure_signature` evidence is `failing`, never silently downgraded.
- Unknown CI-state values are rejected with `ValueError`; they are never
  coerced into a passing or otherwise recognized state.
- Commit: `current_head`, `ancestor`, `stale`, `unknown` — surfaced here
  via `branch_ancestry`'s `is_current_head_of_*` / `is_ancestor_of_*`
  booleans plus `verified_head_commit`'s null-on-unresolvable behavior,
  rather than a single enum field, since a commit can simultaneously be
  "not on target" and "an ancestor of integration."

## "Never infer merge completion from a local merge commit or PR description alone"

`merge_state.classify_merge_state` treats a direct `git merge-base
--is-ancestor` check against the real `target_branch` ref as a hard fact
(not a heuristic), which is the one case where local git evidence alone
is sufficient to call `merged_into_main`. A commit-message *search* for
`"#NNN"` (`git_source.find_merge_commit_for_pr_number`) is explicitly
documented as evidence code landed, never evidence a PR's own `merged`
field is `True`, and this function is not wired into the merge-state
decision for exactly that reason — only `is_ancestor` and the PR
snapshot's own `merged` field feed the classifier.

## The `^{commit}` fix, applied from the first draft

`git rev-parse --verify --quiet <hash>` accepts any well-formed
40-character hex string as syntactically valid, even when no such object
exists — this bug was discovered and fixed in an earlier round of this
session (`tools/integration_state`) and is applied here from
`git_source.py`'s very first version by appending `^{commit}` to every
`rev-parse --verify` call, forcing git to actually dereference and
confirm a real commit object. `tests/release_manifest/test_git_source.py::test_fabricated_hash_sharing_real_prefix_is_not_verified`
and `tests/release_manifest/test_manifest_builder.py::test_fabricated_hash_is_unknown_never_stale_or_merged`
both exercise a fabricated hash sharing a real commit's 8-character
prefix and confirm it resolves to `unknown`, never `stale` or merged.

## Duplicate-ownership detection

`ownership.find_duplicate_ownership` is a freshly, independently
implemented Jaccard-similarity-over-changed-files check (conceptually
similar to `tools/integration_reconciliation/duplicate_detection.py`, but
not imported from it). A pair is flagged if it shares at least one
literal file, or its Jaccard similarity meets `DUPLICATE_JACCARD_THRESHOLD`
(0.3 by default).

## Scientific gate: insufficient data vs. a genuine block

`scientific_gate.evaluate_scientific_gate` distinguishes an absent/
inconclusive result (`"insufficient_data"`, never blocking) from a
genuinely evidenced negative verdict (`"blocked"`, blocking). A
`claims_exceeding_evidence` mismatch — e.g. a `PASS` verdict on synthetic
data with no formal `evidence_kind` — is reported as a warning-only
finding in `blockers`, never as a blocking category itself: this is the
same lesson (a label-mismatch check must never override a more specific,
evidenced category) that was learned the hard way in two earlier rounds
of this session (`tools/integration_reconciliation`,
`tools/release_scientific_audit`), where giving that kind of check
"blocking" severity let it reclassify unrelated CI failures into the
wrong top-level bucket.

## Strict finite JSON

`reporting.to_finite_json` walks the manifest and raises
`NonFiniteValueError` on any `NaN`/`Infinity` float before calling
`json.dumps(..., allow_nan=False)` — `json.dumps` alone would otherwise
silently emit non-standard `NaN`/`Infinity` tokens into the output.

## CLI usage

The optional snapshot is a pre-fetched JSON file supplied by the caller; it is not obtained by this CLI.

```bash
python scripts/build_release_manifest.py --repo-path . --repository OWNER/REPOSITORY --target-branch origin/main --integration-branch origin/integration --source-commit COMMIT_SHA --pr-snapshot path/to/pr-snapshot.json --json-out outputs/release_candidate.json --markdown-out outputs/release_candidate.md
```



## Test commands

```bash
PYTHONPATH=. python -m pytest tests/release_manifest -q
python -m compileall -q tools/release_manifest scripts/build_release_manifest.py tests/release_manifest
```

No test in `tests/release_manifest/` opens a socket: `conftest.py` builds
real, local-only git fixture repos via subprocess `git`, every GitHub-side
fact is a literal in-memory `PRSnapshot` or a small JSON fixture file, and
`test_manifest_builder.py::test_no_network_operation_no_socket_calls`
patches `socket.socket` to raise and confirms a full `build_manifest` call
still succeeds without touching it.

## Required test scenarios (all covered)

verified merge · integration-only · fabricated hash · stale handoff ·
superseded PR (unit-level, via `MergeStateContext.superseded_by`) ·
infrastructure-blocked CI · synthetic scientific result (non-blocking) ·
missing GitHub snapshot · duplicate changed files · no-network operation
— see `tests/release_manifest/test_manifest_builder.py` and
`tests/release_manifest/test_merge_state.py`.

## Known limitations

- `superseded` at the `manifest_builder` (integration) level requires a
  caller-supplied `superseded_by` reference (this package does not itself
  discover "which other PR/branch supersedes this one" — that is squarely
  `tools/integration_reconciliation`'s job, and importing it was explicitly
  out of scope). The classifier branch itself is fully covered at the unit
  level in `test_merge_state.py`.
- `find_merge_commit_for_pr_number` (kept for parity with the sibling
  tools' conventions, not wired into `merge_state`) is a literal
  `"#NNN"`/`"(#NNN)"`/`"pull request #NNN"` commit-subject search and will
  miss a squash-merge with a differently formatted subject — it is
  documented, and used, only as weak "code landed" evidence, never as
  proof of a PR's `merged` field.
- `governance_status`, `dashboard_isolation_status`, and
  `memory_timeout_status` are always the fixed "not evaluated by this
  tool" `Evidence` — wiring real governance/dashboard/memory-timeout
  evidence in requires importing sibling-owned modules this branch must
  not touch this round.
