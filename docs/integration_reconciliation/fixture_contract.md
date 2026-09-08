# Integration reconciliation fixture contract

The reconciliation tests use local Git repositories built under pytest's
temporary directory. They do not clone, fetch, push, create GitHub branches,
or contact a network remote. `origin/*` names are local remote-tracking refs
created with `git update-ref` solely to exercise the read-only reconciliation
code with realistic names.

## Required fixture topology

The deterministic fixture contains:

- a `main` base commit;
- `parent-feature` and `stacked-child`, where the child is genuinely based on
  the parent;
- an unrelated branch;
- `superseded` and its `replacement` descendant;
- a `conflicting` branch that changes the same base file as the parent;
- explicit missing-reference and fabricated-hash cases.

The fixture is not production history. It is test evidence and must never be
used to create a branch in the repository under test.

## Reference and ancestry rules

`fixture_audit.audit_reference` accepts a branch only when the required branch
ref resolves to a real commit object. A random forty-character hexadecimal
string is not evidence of a commit; it is classified as `missing_reference`.
Missing required branches are blockers, not PASS results.

`audit_ancestry` reports Git ancestry separately from a textual PR claim. A
local merge commit or an ancestor relationship can show that commit history is
contained in a target, but it cannot prove that a GitHub pull request was
merged. Provider metadata is required for that claim, so
`pr_merge_verified` remains false in local-only fixture evidence.

## Stale fixture handling

The historical PR #263 failure referenced `origin/stacked-on-feature-a` while
its older fixture setup did not create that ref. On the current `origin/main`,
the broader reconciliation conftest contains the corresponding local fixture.
This contract adds an independent fixture package so tests do not depend on
that incidental setup. If a required ref is absent in any future fixture, the
audit output must say `missing_reference`; it must not synthesize the branch or
silently downgrade the failure to PASS.

The historical closure-head replay reproduced exactly four failures: two
stacked effective/raw-diff assertions and two low-level stacked-diff assertions,
all caused by `git diff` receiving the absent ref and returning `None`. The
current-base replay shows those assertions passing with the real local fixture;
the remaining 120-second timeout is the slow reconciliation test process, not
a missing branch.
